from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.fine_payment import service
from app.fine_payment.gateway import InvalidGatewayResult
from app.fine_payment.models import GatewayResult, PaymentStatus
from app.fine_payment.store import (
    DEMO_MEMBER_ID,
    FINE_ITEMS,
    PAYMENT_RECORDS,
    PAYMENT_REQUESTS,
    PAYMENT_REVIEW_RECORDS,
    reset_store,
)
from app.main import app

client = TestClient(app)
BASE_TIME = datetime.fromisoformat("2026-11-16T12:00:00+07:00")


class FakePaymentGateway:
    def __init__(self) -> None:
        self.start_status: PaymentStatus | None = None
        self.status_result: GatewayResult | None = None
        self.started_requests = []
        self.status_checks = []

    def start_payment(self, request):
        self.started_requests.append(request)
        if self.start_status is None:
            return None
        return GatewayResult(
            payment_ref=request.payment_ref,
            amount=request.amount,
            status=self.start_status,
            transaction_number="TX-FAILED",
        )

    def check_status(self, payment_ref):
        self.status_checks.append(payment_ref)
        return self.status_result

    def verify_callback(self, payload):
        if payload.get("verified") is not True:
            raise InvalidGatewayResult("ผลตอบกลับจาก Gateway ไม่ผ่านการตรวจสอบ")
        status = PaymentStatus(payload["status"])
        return GatewayResult(
            payment_ref=payload["payment_ref"],
            amount=Decimal(payload["amount"]),
            status=status,
            transaction_number=payload.get("transaction_number"),
        )


@pytest.fixture(autouse=True)
def payment_store(monkeypatch):
    reset_store()
    gateway = FakePaymentGateway()
    monkeypatch.setattr(service, "GATEWAY", gateway)
    yield gateway
    reset_store()


def _create_pending_request(channel="channel-A", now=BASE_TIME):
    return service.start_payment(
        member_id=DEMO_MEMBER_ID,
        channel=channel,
        now=now,
    )["payment_request"]


def _callback(payment_ref, *, amount="25.00", status="succeeded", transaction="TX-001"):
    return client.post(
        "/api/payments/result",
        json={
            "verified": True,
            "payment_ref": payment_ref,
            "amount": amount,
            "status": status,
            "transaction_number": transaction,
        },
    )


def test_AC_ชำระค่าปรับออนไลน์_01(payment_store):
    response = client.get("/api/me/fines")

    assert response.status_code == 200
    assert response.json()["total_amount"] == "25.00"
    assert len(response.json()["fines"]) == 2

    started = client.post(
        "/api/payments",
        json={"member_id": DEMO_MEMBER_ID, "channel": "channel-A"},
    )

    assert started.status_code == 200
    pending = started.json()["payment_request"]
    assert pending["status"] == PaymentStatus.PENDING.value
    assert pending["amount"] == "25.00"
    assert pending["payment_ref"]
    assert payment_store.started_requests[0].fine_ids == ("FINE-001", "FINE-002")

    completed = _callback(pending["payment_ref"])

    assert completed.status_code == 200
    assert completed.json() == {"acknowledged": True, "status": "succeeded"}
    assert all(fine.status.value == "paid" for fine in FINE_ITEMS)
    assert PAYMENT_RECORDS[pending["payment_ref"]].transaction_number == "TX-001"
    assert client.get("/api/me/fines").json()["total_amount"] == "0.00"

    duplicate = _callback(pending["payment_ref"], transaction="TX-001")
    assert duplicate.status_code == 200
    assert duplicate.json() == {"acknowledged": True, "status": "succeeded"}
    assert len(PAYMENT_RECORDS) == 1

    mismatch = _callback(pending["payment_ref"], amount="24.99", transaction="TX-001")
    assert mismatch.status_code == 200
    assert mismatch.json()["status"] == "review"
    assert PAYMENT_REQUESTS[pending["payment_ref"]].status == PaymentStatus.SUCCEEDED
    assert all(fine.status.value == "paid" for fine in FINE_ITEMS)
    assert PAYMENT_REVIEW_RECORDS[-1].reason == "ยอดเงินจาก Gateway ไม่ตรงกับยอดคำขอ"


def test_AC_ชำระค่าปรับออนไลน์_02(payment_store):
    payment_store.start_status = PaymentStatus.FAILED

    response = client.post(
        "/api/payments",
        json={"member_id": DEMO_MEMBER_ID, "channel": "channel-A"},
    )

    assert response.status_code == 200
    failed_request = response.json()["payment_request"]
    assert failed_request["status"] == PaymentStatus.FAILED.value
    assert response.json()["message"] == "ชำระไม่สำเร็จ กรุณาลองใหม่"
    assert all(fine.status.value == "outstanding" for fine in FINE_ITEMS)

    payment_store.start_status = None
    retry = service.start_payment(
        member_id=DEMO_MEMBER_ID,
        channel="channel-A",
        now=BASE_TIME,
    )
    assert retry["payment_request"]["status"] == PaymentStatus.PENDING.value
    assert retry["payment_request"]["payment_ref"] != failed_request["payment_ref"]

    pending_request = retry["payment_request"]
    assert service.poll_pending_requests(BASE_TIME + timedelta(minutes=4)) == 0
    assert payment_store.status_checks == []
    assert service.poll_pending_requests(BASE_TIME + timedelta(minutes=5)) == 1
    assert payment_store.status_checks == [pending_request["payment_ref"]]
    assert PAYMENT_REQUESTS[pending_request["payment_ref"]].status == PaymentStatus.PENDING

    expired = service.check_payment_status(
        pending_request["payment_ref"],
        member_id=DEMO_MEMBER_ID,
        now=BASE_TIME + timedelta(minutes=30),
    )
    assert expired["payment_request"]["status"] == PaymentStatus.EXPIRED.value
    assert all(fine.status.value == "outstanding" for fine in FINE_ITEMS)

    late_success = _callback(pending_request["payment_ref"], transaction="TX-LATE")
    assert late_success.status_code == 200
    assert late_success.json()["status"] == PaymentStatus.SUCCEEDED.value
    assert PAYMENT_REQUESTS[pending_request["payment_ref"]].status == PaymentStatus.SUCCEEDED
    assert all(fine.status.value == "paid" for fine in FINE_ITEMS)

    late_failed = _callback(pending_request["payment_ref"], status="failed")
    assert late_failed.status_code == 200
    assert late_failed.json()["status"] == PaymentStatus.SUCCEEDED.value
    assert PAYMENT_REQUESTS[pending_request["payment_ref"]].status == PaymentStatus.SUCCEEDED


def test_AC_ชำระค่าปรับออนไลน์_03_ใช้ช่องทางที่สมาชิกเลือกก่อนยืนยัน(payment_store):
    preview = client.get("/api/me/fines")

    assert preview.status_code == 200
    preview_data = preview.json()
    assert preview_data["total_amount"] == "25.00"
    assert len(preview_data["fines"]) == 2
    for fine in preview_data["fines"]:
        assert {
            "book_title",
            "due_date",
            "returned_date",
            "overdue_days",
            "amount",
        } <= fine.keys()

    response = client.post(
        "/api/payments",
        json={"member_id": DEMO_MEMBER_ID, "channel": "channel-B"},
    )

    assert response.status_code == 200
    assert payment_store.started_requests[0].channel == "channel-B"
    assert response.json()["payment_request"]["channel"] == "channel-B"

    old_request = response.json()["payment_request"]
    payment_request = PAYMENT_REQUESTS[old_request["payment_ref"]]
    payment_request.created_at = BASE_TIME
    payment_request.last_checked_at = BASE_TIME
    payment_request.expires_at = BASE_TIME + timedelta(minutes=30)
    old_request_expired = service.check_payment_status(
        old_request["payment_ref"],
        member_id=DEMO_MEMBER_ID,
        now=BASE_TIME + timedelta(minutes=30),
    )
    assert old_request_expired["payment_request"]["status"] == PaymentStatus.EXPIRED.value

    new_request = service.start_payment(
        member_id=DEMO_MEMBER_ID,
        channel="channel-C",
        now=BASE_TIME + timedelta(minutes=31),
    )
    assert new_request["payment_request"]["channel"] == "channel-C"
    assert new_request["payment_request"]["payment_ref"] != old_request["payment_ref"]
    assert all(fine.status.value == "outstanding" for fine in FINE_ITEMS)


def test_FR02_ยอดจาก_gatewayไม่ตรงต้องคงสถานะและบันทึกตรวจสอบ():
    pending = _create_pending_request()

    response = _callback(pending["payment_ref"], amount="24.99")

    assert response.status_code == 200
    assert response.json()["status"] == "review"
    assert PAYMENT_REQUESTS[pending["payment_ref"]].status == PaymentStatus.PENDING
    assert all(fine.status.value == "outstanding" for fine in FINE_ITEMS)
    assert PAYMENT_REVIEW_RECORDS[0].reason == "ยอดเงินจาก Gateway ไม่ตรงกับยอดคำขอ"


def test_FR03_ผลสำเร็จซ้ำไม่สร้างรายการชำระซ้ำ():
    pending = _create_pending_request()
    for _ in range(2):
        response = _callback(pending["payment_ref"])
        assert response.status_code == 200
        assert response.json()["acknowledged"] is True

    assert len(PAYMENT_RECORDS) == 1
    assert len(PAYMENT_REQUESTS) == 1


def test_FR04_pendingบล็อกการชำระซ้ำและหมดอายุหลังสามสิบนาที(payment_store):
    pending = _create_pending_request()
    retry = client.post(
        "/api/payments",
        json={"member_id": DEMO_MEMBER_ID, "channel": "channel-B"},
    )
    assert retry.status_code == 409

    checked = service.check_payment_status(
        pending["payment_ref"],
        member_id=DEMO_MEMBER_ID,
        now=BASE_TIME + timedelta(minutes=5),
    )
    assert checked["payment_request"]["payment_ref"] == pending["payment_ref"]
    assert payment_store.status_checks == [pending["payment_ref"]]

    expired = service.check_payment_status(
        pending["payment_ref"],
        member_id=DEMO_MEMBER_ID,
        now=BASE_TIME + timedelta(minutes=30),
    )
    assert expired["payment_request"]["status"] == PaymentStatus.EXPIRED.value
    assert all(fine.status.value == "outstanding" for fine in FINE_ITEMS)

    new_request = service.start_payment(
        member_id=DEMO_MEMBER_ID,
        channel="channel-B",
        now=BASE_TIME + timedelta(minutes=31),
    )
    assert new_request["payment_request"]["payment_ref"] != pending["payment_ref"]


def test_FR03_ผลสำเร็จหลังหมดอายุยังชำระค่าปรับได้():
    pending = _create_pending_request()
    service.check_payment_status(
        pending["payment_ref"],
        member_id=DEMO_MEMBER_ID,
        now=BASE_TIME + timedelta(minutes=30),
    )

    response = _callback(pending["payment_ref"])

    assert response.status_code == 200
    assert response.json()["status"] == PaymentStatus.SUCCEEDED.value
    assert all(fine.status.value == "paid" for fine in FINE_ITEMS)


def test_FR04_pollingตรวจทุกห้านาทีและหมดอายุเมื่อครบสามสิบนาที(payment_store):
    pending = _create_pending_request()

    assert service.poll_pending_requests(BASE_TIME + timedelta(minutes=4)) == 0
    assert payment_store.status_checks == []

    assert service.poll_pending_requests(BASE_TIME + timedelta(minutes=5)) == 1
    assert payment_store.status_checks == [pending["payment_ref"]]

    service.poll_pending_requests(BASE_TIME + timedelta(minutes=30))
    assert PAYMENT_REQUESTS[pending["payment_ref"]].status == PaymentStatus.EXPIRED


def test_gatewayที่ยังไม่ตั้งค่าไม่สร้างคำขอชำระ(monkeypatch):
    monkeypatch.setattr(service, "GATEWAY", service.UnconfiguredPaymentGateway())

    response = client.post("/api/payments", json={"channel": "channel-A"})

    assert response.status_code == 503
    assert PAYMENT_REQUESTS == {}


def test_FR03_เลขธุรกรรมใหม่กับpayment_refเดิมเข้าสู่รายการตรวจสอบ():
    pending = _create_pending_request()
    first = _callback(pending["payment_ref"], transaction="TX-001")
    assert first.status_code == 200

    second = _callback(pending["payment_ref"], transaction="TX-002")

    assert second.status_code == 200
    assert second.json()["status"] == "review"
    assert len(PAYMENT_RECORDS) == 1
    assert PAYMENT_REQUESTS[pending["payment_ref"]].status == PaymentStatus.SUCCEEDED
    assert PAYMENT_REVIEW_RECORDS[-1].gateway_transaction_number == "TX-002"


def test_NFRSEC_callbackลายเซ็นไม่ผ่านตอบ401และบันทึก():
    pending = _create_pending_request()

    response = client.post(
        "/api/payments/result",
        json={
            "verified": False,
            "payment_ref": pending["payment_ref"],
            "amount": "25.00",
            "status": "succeeded",
            "transaction_number": "TX-BAD",
        },
    )

    assert response.status_code == 401


def test_AC03_คำขอเก่าสำเร็จก่อนคำขอใหม่ยกเลิกคำขอใหม่():
    old_request = _create_pending_request(channel="channel-A")
    service.check_payment_status(
        old_request["payment_ref"],
        member_id=DEMO_MEMBER_ID,
        now=BASE_TIME + timedelta(minutes=30),
    )
    new_request = service.start_payment(
        member_id=DEMO_MEMBER_ID,
        channel="channel-B",
        now=BASE_TIME + timedelta(minutes=31),
    )["payment_request"]

    old_success = _callback(old_request["payment_ref"], transaction="TX-OLD")

    assert old_success.status_code == 200
    assert PAYMENT_REQUESTS[old_request["payment_ref"]].status == PaymentStatus.SUCCEEDED
    assert PAYMENT_REQUESTS[new_request["payment_ref"]].status == PaymentStatus.CANCELLED
    assert all(fine.status.value == "paid" for fine in FINE_ITEMS)


def test_AC11_คำขอเก่าและคำขอใหม่สำเร็จซ้ำรอคืนเงิน():
    old_request = _create_pending_request(channel="channel-A")
    service.check_payment_status(
        old_request["payment_ref"],
        member_id=DEMO_MEMBER_ID,
        now=BASE_TIME + timedelta(minutes=30),
    )
    new_request = service.start_payment(
        member_id=DEMO_MEMBER_ID,
        channel="channel-B",
        now=BASE_TIME + timedelta(minutes=31),
    )["payment_request"]

    _callback(old_request["payment_ref"], transaction="TX-OLD")
    _callback(new_request["payment_ref"], transaction="TX-NEW")

    assert PAYMENT_REQUESTS[new_request["payment_ref"]].status == PaymentStatus.DUPLICATE_REFUND_PENDING
    assert PAYMENT_REQUESTS[old_request["payment_ref"]].status == PaymentStatus.SUCCEEDED
    assert len(PAYMENT_RECORDS) == 1


def test_ASM14_เจ้าหน้าที่การเงินตัดสินและบันทึกเหตุผล():
    pending = _create_pending_request()
    _callback(pending["payment_ref"], amount="24.99")
    review = PAYMENT_REVIEW_RECORDS[0]

    login = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert login.status_code == 200

    response = client.post(
        f"/api/admin/payment-reviews/{review.review_id}/decision",
        json={"decision": "ส่งคืนเงิน", "reason": "ยอดไม่ตรงกับคำขอ"},
    )

    assert response.status_code == 200
    resolved = response.json()
    assert resolved["status"] == "refund_requested"
    assert resolved["resolved_by"] == "admin"
    assert resolved["resolution_reason"] == "ยอดไม่ตรงกับคำขอ"
    assert resolved["resolved_at"]
