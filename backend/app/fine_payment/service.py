from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from dataclasses import replace
from typing import Any
from zoneinfo import ZoneInfo

from .gateway import (
    GatewayNotConfigured,
    GatewayTimeout,
    InvalidGatewayResult,
    PaymentGateway,
    UnconfiguredPaymentGateway,
)
from .models import (
    FineStatus,
    GatewayResult,
    PaymentRecord,
    PaymentRequest,
    PaymentReviewRecord,
    PaymentStatus,
)
from .store import (
    DEMO_MEMBER_ID,
    FINE_ITEMS,
    PAYMENT_RECORDS,
    PAYMENT_REQUESTS,
    PAYMENT_REVIEW_RECORDS,
    STORE_LOCK,
)

logger = logging.getLogger(__name__)
ASIA_BANGKOK = ZoneInfo("Asia/Bangkok")
PENDING_DURATION = timedelta(minutes=30)
STATUS_POLL_INTERVAL = timedelta(minutes=5)

GATEWAY: PaymentGateway = UnconfiguredPaymentGateway()


class PaymentDomainError(Exception):
    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


def _now(value: datetime | None = None) -> datetime:
    current = value or datetime.now(ASIA_BANGKOK)
    if current.tzinfo is None:
        return current.replace(tzinfo=ASIA_BANGKOK)
    return current.astimezone(ASIA_BANGKOK)


def _outstanding_fines(member_id: str) -> list[Any]:
    return [
        fine
        for fine in FINE_ITEMS
        if fine.member_id == member_id and fine.status == FineStatus.OUTSTANDING
    ]


def list_member_fines(member_id: str = DEMO_MEMBER_ID) -> dict[str, Any]:
    with STORE_LOCK:
        fines = _outstanding_fines(member_id)
        total = sum((fine.amount for fine in fines), Decimal("0.00"))
        pending_request = next(
            (
                request
                for request in reversed(list(PAYMENT_REQUESTS.values()))
                if request.member_id == member_id and request.status == PaymentStatus.PENDING
            ),
            None,
        )
        return {
            "member_id": member_id,
            "fines": [fine.to_dict() for fine in fines],
            "total_amount": format(total, ".2f"),
            "pending_payment_request": pending_request.to_dict() if pending_request else None,
        }


def _find_request(payment_ref: str) -> PaymentRequest | None:
    return PAYMENT_REQUESTS.get(payment_ref)


def _find_fines(fine_ids: tuple[str, ...]) -> list[Any]:
    fine_map = {fine.fine_id: fine for fine in FINE_ITEMS}
    return [fine_map[fine_id] for fine_id in fine_ids if fine_id in fine_map]


def _record_review(
    payment_ref: str,
    amount: Decimal | None,
    reason: str,
    received_at: datetime,
    *,
    transaction_number: str | None = None,
    expected_amount: Decimal | None = None,
    raw_gateway_data: dict[str, Any] | None = None,
) -> None:
    PAYMENT_REVIEW_RECORDS.append(
        PaymentReviewRecord(
            review_id=uuid.uuid4().hex,
            received_payment_ref=payment_ref,
            reported_amount=amount,
            gateway_transaction_number=transaction_number,
            expected_amount=expected_amount,
            raw_gateway_data=raw_gateway_data,
            reason=reason,
            created_at=received_at,
        )
    )
    logger.warning("Payment result requires review: ref=%s reason=%s", payment_ref, reason)


def _apply_result(result: GatewayResult, now: datetime) -> dict[str, Any]:
    with STORE_LOCK:
        request = _find_request(result.payment_ref)
        if request is None:
            _record_review(
                result.payment_ref,
                result.amount,
                "ไม่พบ payment_ref ที่ตรงกับคำขอ",
                now,
                transaction_number=result.transaction_number,
                raw_gateway_data={
                    "payment_ref": result.payment_ref,
                    "amount": format(result.amount, ".2f"),
                    "status": result.status.value,
                    "transaction_number": result.transaction_number,
                },
            )
            return {"acknowledged": False, "status": "review"}

        if result.amount != request.amount:
            _record_review(
                result.payment_ref,
                result.amount,
                "ยอดเงินจาก Gateway ไม่ตรงกับยอดคำขอ",
                now,
                transaction_number=result.transaction_number,
                expected_amount=request.amount,
                raw_gateway_data={
                    "payment_ref": result.payment_ref,
                    "amount": format(result.amount, ".2f"),
                    "status": result.status.value,
                    "transaction_number": result.transaction_number,
                },
            )
            return {"acknowledged": True, "status": "review"}

        if request.status == PaymentStatus.SUCCEEDED:
            if result.status == PaymentStatus.SUCCEEDED:
                if result.transaction_number == request.gateway_transaction_number:
                    logger.info(
                        "Duplicate successful payment callback received: ref=%s transaction=%s",
                        result.payment_ref,
                        result.transaction_number,
                    )
                    return {"acknowledged": True, "status": request.status.value}
                _record_review(
                    result.payment_ref,
                    result.amount,
                    "เลขธุรกรรมใหม่กับ payment_ref เดิม; ตรวจว่าตัดเงินซ้ำเพื่อคืนเงิน",
                    now,
                    transaction_number=result.transaction_number,
                    expected_amount=request.amount,
                )
                return {"acknowledged": True, "status": "review"}
            return {"acknowledged": True, "status": request.status.value}

        if result.status == PaymentStatus.SUCCEEDED:
            fines = _find_fines(request.fine_ids)
            already_paid = any(fine.status == FineStatus.PAID for fine in fines)
            if request.status == PaymentStatus.CANCELLED and already_paid:
                request.status = PaymentStatus.DUPLICATE_REFUND_PENDING
                request.gateway_transaction_number = result.transaction_number
                _record_review(
                    result.payment_ref,
                    result.amount,
                    "คำขอที่ถูกยกเลิกได้รับผลสำเร็จซ้ำหลังค่าปรับถูกชำระแล้ว; รอคืนเงิน",
                    now,
                    transaction_number=result.transaction_number,
                    expected_amount=request.amount,
                )
                return {"acknowledged": True, "status": request.status.value}

            if request.status not in {PaymentStatus.PENDING, PaymentStatus.EXPIRED}:
                _record_review(
                    result.payment_ref,
                    result.amount,
                    "ได้รับผลสำเร็จหลังคำขออยู่ในสถานะล้มเหลว",
                    now,
                )
                return {"acknowledged": True, "status": request.status.value}

            if not result.transaction_number:
                _record_review(
                    result.payment_ref,
                    result.amount,
                    "ผลสำเร็จจาก Gateway ไม่มีเลขธุรกรรม",
                    now,
                )
                return {"acknowledged": True, "status": "review"}

            if len(fines) != len(request.fine_ids):
                _record_review(
                    result.payment_ref,
                    result.amount,
                    "ไม่พบรายการค่าปรับที่ผูกกับคำขอครบถ้วน",
                    now,
                )
                return {"acknowledged": True, "status": "review"}

            already_paid = any(fine.status == FineStatus.PAID for fine in fines)
            if already_paid:
                request.status = PaymentStatus.DUPLICATE_REFUND_PENDING
                request.gateway_transaction_number = result.transaction_number
                _record_review(
                    result.payment_ref,
                    result.amount,
                    "คำขอชำระสำเร็จซ้ำหลังค่าปรับถูกชำระแล้ว; รอคืนเงิน",
                    now,
                    transaction_number=result.transaction_number,
                    expected_amount=request.amount,
                )
                return {"acknowledged": True, "status": request.status.value}

            request.status = PaymentStatus.SUCCEEDED
            request.gateway_transaction_number = result.transaction_number
            for fine in fines:
                fine.status = FineStatus.PAID

            PAYMENT_RECORDS[request.payment_ref] = PaymentRecord(
                payment_ref=request.payment_ref,
                transaction_number=result.transaction_number,
                amount=request.amount,
                fine_ids=request.fine_ids,
                paid_at=now,
            )
            for other_request in PAYMENT_REQUESTS.values():
                if (
                    other_request.payment_ref != request.payment_ref
                    and other_request.status == PaymentStatus.PENDING
                    and set(other_request.fine_ids).intersection(request.fine_ids)
                ):
                    other_request.status = PaymentStatus.CANCELLED
            return {"acknowledged": True, "status": request.status.value}

        if result.status == PaymentStatus.FAILED:
            if request.status == PaymentStatus.PENDING:
                request.status = PaymentStatus.FAILED
                request.last_checked_at = now
            return {"acknowledged": True, "status": request.status.value}

        raise InvalidGatewayResult("Gateway ส่งสถานะผลลัพธ์ที่ไม่รองรับ")


def start_payment(
    *,
    member_id: str = DEMO_MEMBER_ID,
    channel: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    current_time = _now(now)
    if not isinstance(member_id, str) or not member_id.strip():
        raise PaymentDomainError("ไม่พบรหัสสมาชิก", 422)
    if not isinstance(channel, str):
        raise PaymentDomainError("กรุณาเลือกช่องทางชำระเงิน", 422)
    normalized_channel = channel.strip()
    if not normalized_channel:
        raise PaymentDomainError("กรุณาเลือกช่องทางชำระเงิน", 422)

    with STORE_LOCK:
        fines = _outstanding_fines(member_id)
        if not fines:
            raise PaymentDomainError("ไม่มีค่าปรับค้างชำระ", 409)

        fine_ids = tuple(sorted(fine.fine_id for fine in fines))
        pending_requests = [
            request
            for request in PAYMENT_REQUESTS.values()
            if request.status == PaymentStatus.PENDING
            and set(request.fine_ids).intersection(fine_ids)
        ]
        if pending_requests:
            raise PaymentDomainError("มีคำขอชำระที่รอยืนยันผลอยู่แล้ว", 409)

        request = PaymentRequest(
            payment_ref=uuid.uuid4().hex,
            member_id=member_id,
            fine_ids=fine_ids,
            amount=sum((fine.amount for fine in fines), Decimal("0.00")),
            channel=normalized_channel,
            status=PaymentStatus.PENDING,
            created_at=current_time,
            expires_at=current_time + PENDING_DURATION,
            last_checked_at=current_time,
        )
        PAYMENT_REQUESTS[request.payment_ref] = request

    try:
        result = GATEWAY.start_payment(request)
    except GatewayNotConfigured as error:
        with STORE_LOCK:
            PAYMENT_REQUESTS.pop(request.payment_ref, None)
        raise PaymentDomainError(str(error), 503) from error
    except GatewayTimeout:
        logger.warning("Payment gateway timed out for ref=%s", request.payment_ref)
        result = None

    if result is not None:
        _apply_result(result, current_time)

    with STORE_LOCK:
        message = {
            PaymentStatus.PENDING: "ส่งคำขอชำระแล้ว กำลังรอผลยืนยัน",
            PaymentStatus.SUCCEEDED: "ชำระค่าปรับสำเร็จ",
            PaymentStatus.FAILED: "ชำระไม่สำเร็จ กรุณาลองใหม่",
            PaymentStatus.EXPIRED: "คำขอชำระหมดอายุ กรุณาเริ่มรายการใหม่",
            PaymentStatus.CANCELLED: "คำขอชำระถูกยกเลิก",
            PaymentStatus.DUPLICATE_REFUND_PENDING: "พบการชำระซ้ำ กรุณารอเจ้าหน้าที่ตรวจสอบ",
        }[request.status]
        return {
            "success": True,
            "message": message,
            "payment_request": request.to_dict(),
        }


def handle_gateway_callback(payload: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    current_time = _now(now)
    try:
        result = GATEWAY.verify_callback(payload)
    except GatewayNotConfigured as error:
        raise PaymentDomainError(str(error), 503) from error
    except InvalidGatewayResult as error:
        logger.warning(
            "Payment callback signature verification failed: payment_ref=%s",
            payload.get("payment_ref"),
        )
        raise PaymentDomainError(str(error), 401) from error
    return _apply_result(result, current_time)


def _check_request_status(request: PaymentRequest, now: datetime) -> None:
    try:
        result = GATEWAY.check_status(request.payment_ref)
    except GatewayTimeout:
        logger.warning("Payment status check timed out for ref=%s", request.payment_ref)
        result = None
    if result is not None:
        _apply_result(result, now)
        return

    with STORE_LOCK:
        if request.status == PaymentStatus.PENDING and now >= request.expires_at:
            request.status = PaymentStatus.EXPIRED


def check_payment_status(
    payment_ref: str,
    *,
    member_id: str = DEMO_MEMBER_ID,
    now: datetime | None = None,
) -> dict[str, Any]:
    current_time = _now(now)
    with STORE_LOCK:
        request = _find_request(payment_ref)
        if request is None or request.member_id != member_id:
            raise PaymentDomainError("ไม่พบคำขอชำระ", 404)
        request_to_check = request
        request.last_checked_at = current_time

    if request_to_check.status in {PaymentStatus.PENDING, PaymentStatus.EXPIRED}:
        try:
            _check_request_status(request_to_check, current_time)
        except GatewayNotConfigured as error:
            raise PaymentDomainError(str(error), 503) from error

    with STORE_LOCK:
        return {"payment_request": request_to_check.to_dict()}


def poll_pending_requests(now: datetime | None = None) -> int:
    current_time = _now(now)
    with STORE_LOCK:
        due_requests = [
            request
            for request in PAYMENT_REQUESTS.values()
            if request.status == PaymentStatus.PENDING
            and current_time - (request.last_checked_at or request.created_at)
            >= STATUS_POLL_INTERVAL
        ]

    polled = 0
    for request in due_requests:
        request.last_checked_at = current_time
        try:
            _check_request_status(request, current_time)
            polled += 1
        except GatewayNotConfigured as error:
            logger.error("Cannot poll pending payment ref=%s: %s", request.payment_ref, error)
        except PaymentDomainError:
            raise
    return polled


def list_payment_requests() -> list[dict[str, Any]]:
    with STORE_LOCK:
        return [request.to_dict() for request in PAYMENT_REQUESTS.values()]


def list_payment_reviews() -> list[dict[str, Any]]:
    with STORE_LOCK:
        return [review.to_dict() for review in PAYMENT_REVIEW_RECORDS]


def decide_payment_review(
    review_id: str,
    *,
    decision: str,
    resolved_by: str,
    reason: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    if decision not in {"ยืนยันว่าชำระแล้ว", "ส่งคืนเงิน"}:
        raise PaymentDomainError("การตัดสินใจต้องเป็น 'ยืนยันว่าชำระแล้ว' หรือ 'ส่งคืนเงิน'", 422)
    if not reason.strip():
        raise PaymentDomainError("ต้องระบุเหตุผลการตัดสินใจ", 422)

    current_time = _now(now)
    with STORE_LOCK:
        review = next(
            (item for item in PAYMENT_REVIEW_RECORDS if item.review_id == review_id),
            None,
        )
        if review is None:
            raise PaymentDomainError("ไม่พบรายการรอตรวจสอบ", 404)
        if review.status != "pending":
            raise PaymentDomainError("รายการรอตรวจสอบได้รับการตัดสินใจแล้ว", 409)

        resolved_status = (
            "resolved_confirmed"
            if decision == "ยืนยันว่าชำระแล้ว"
            else "refund_requested"
        )
        resolved_review = replace(
            review,
            status=resolved_status,
            resolved_by=resolved_by,
            resolved_at=current_time,
            resolution_reason=reason,
        )
        index = PAYMENT_REVIEW_RECORDS.index(review)
        PAYMENT_REVIEW_RECORDS[index] = resolved_review

        if decision == "ยืนยันว่าชำระแล้ว":
            request = PAYMENT_REQUESTS.get(review.received_payment_ref)
            if request is not None and review.expected_amount == request.amount:
                fines = _find_fines(request.fine_ids)
                request.status = PaymentStatus.SUCCEEDED
                request.gateway_transaction_number = review.gateway_transaction_number
                for fine in fines:
                    fine.status = FineStatus.PAID
                if review.gateway_transaction_number:
                    PAYMENT_RECORDS.setdefault(
                        request.payment_ref,
                        PaymentRecord(
                            payment_ref=request.payment_ref,
                            transaction_number=review.gateway_transaction_number,
                            amount=request.amount,
                            fine_ids=request.fine_ids,
                            paid_at=current_time,
                        ),
                    )

        return resolved_review.to_dict()
