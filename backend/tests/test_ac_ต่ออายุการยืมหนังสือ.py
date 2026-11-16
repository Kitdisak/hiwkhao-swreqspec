from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app.renew_loan.models import Loan
from app.renew_loan import service

client = TestClient(app)


def test_AC_ต่ออายุการยืมหนังสือ_01(monkeypatch):
    loan = Loan(
        loan_id="LOAN-OK",
        member_id="STU-001",
        member_type="undergraduate",
        book_id="BOOK-001",
        due_date=(date.today() + timedelta(days=2)).isoformat(),
        renewal_count=0,
        waiting_reservations=0,
    )
    monkeypatch.setattr(service, "LOANS", [loan])

    response = client.post(
        "/api/loans/LOAN-OK/renew",
        json={"member_id": "STU-001", "member_type": "undergraduate", "renewed_by": "STU-001"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["loan"]["renewal_count"] == 1
    assert payload["loan"]["due_date"] != loan.due_date.isoformat()


def test_AC_ต่ออายุการยืมหนังสือ_02_แยกเหตุผลการปฏิเสธ(monkeypatch):
    loan = Loan(
        loan_id="LOAN-WAITING",
        member_id="STU-001",
        member_type="undergraduate",
        book_id="BOOK-002",
        due_date=(date.today() + timedelta(days=2)).isoformat(),
        renewal_count=0,
        waiting_reservations=1,
    )
    monkeypatch.setattr(service, "LOANS", [loan])

    response = client.post(
        "/api/loans/LOAN-WAITING/renew",
        json={"member_id": "STU-001", "member_type": "undergraduate"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert "มีผู้จองหนังสือเล่มนี้ไว้" in payload["reasons"]


def test_AC_ต่ออายุการยืมหนังสือ_02_ครบจำนวนครั้งให้ปฏิเสธ(monkeypatch):
    loan = Loan(
        loan_id="LOAN-MAX",
        member_id="STU-001",
        member_type="undergraduate",
        book_id="BOOK-003",
        due_date=(date.today() + timedelta(days=1)).isoformat(),
        renewal_count=1,
        waiting_reservations=0,
    )
    monkeypatch.setattr(service, "LOANS", [loan])

    response = client.post(
        "/api/loans/LOAN-MAX/renew",
        json={"member_id": "STU-001", "member_type": "undergraduate"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert "ต่ออายุครบจำนวนครั้งที่กำหนดแล้ว (1/1 ครั้ง)" in payload["reasons"]


def test_AC_ต่ออายุการยืมหนังสือ_03_ต่ออายุได้ในช่วงสามวันก่อนครบกำหนด(monkeypatch):
    due_date = date.today() + timedelta(days=3)
    loan = Loan(
        loan_id="LOAN-NEAR-DUE",
        member_id="STU-001",
        member_type="undergraduate",
        book_id="BOOK-006",
        due_date=due_date.isoformat(),
        renewal_count=0,
        waiting_reservations=0,
    )
    monkeypatch.setattr(service, "LOANS", [loan])
    monkeypatch.setattr(service, "RENEWAL_AUDIT_LOG", [])

    response = client.post(
        "/api/loans/LOAN-NEAR-DUE/renew",
        json={"member_id": "STU-001", "member_type": "undergraduate", "renewed_by": "STU-001"},
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["success"] is True
    assert payload["loan"]["renewal_count"] == 1
    assert payload["audit"]["old_due_date"] == due_date.isoformat()
    assert payload["audit"]["renewed_by"] == "STU-001"
    assert payload["audit"]["renewed_at"]
    assert service.RENEWAL_AUDIT_LOG == [payload["audit"]]


def test_AC_ต่ออายุการยืมหนังสือ_02_เกินกำหนดและไม่เปลี่ยนข้อมูล(monkeypatch):
    due_date = date.today() - timedelta(days=1)
    loan = Loan(
        loan_id="LOAN-OVERDUE",
        member_id="STU-001",
        member_type="undergraduate",
        book_id="BOOK-004",
        due_date=due_date.isoformat(),
        renewal_count=0,
        waiting_reservations=0,
    )
    monkeypatch.setattr(service, "LOANS", [loan])
    monkeypatch.setattr(service, "RENEWAL_AUDIT_LOG", [])

    response = client.post(
        "/api/loans/LOAN-OVERDUE/renew",
        json={"member_id": "STU-001", "member_type": "undergraduate"},
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["success"] is False
    assert payload["reasons"] == [
        "หนังสือเกินกำหนดคืนแล้ว กรุณาคืนหนังสือที่เคาน์เตอร์"
    ]
    assert payload["loan"]["due_date"] == due_date.isoformat()
    assert payload["loan"]["renewal_count"] == 0
    assert service.RENEWAL_AUDIT_LOG == []


def test_AC_ต่ออายุการยืมหนังสือ_02_แสดงทุกสาเหตุตามลำดับและไม่เปลี่ยนข้อมูล(monkeypatch):
    due_date = date.today() - timedelta(days=1)
    loan = Loan(
        loan_id="LOAN-MULTIPLE-REASONS",
        member_id="STU-001",
        member_type="undergraduate",
        book_id="BOOK-005",
        due_date=due_date.isoformat(),
        renewal_count=1,
        waiting_reservations=1,
    )
    monkeypatch.setattr(service, "LOANS", [loan])
    monkeypatch.setattr(service, "RENEWAL_AUDIT_LOG", [])

    response = client.post(
        "/api/loans/LOAN-MULTIPLE-REASONS/renew",
        json={"member_id": "STU-001", "member_type": "undergraduate"},
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["success"] is False
    assert payload["reasons"] == [
        "หนังสือเกินกำหนดคืนแล้ว กรุณาคืนหนังสือที่เคาน์เตอร์",
        "มีผู้จองหนังสือเล่มนี้ไว้",
        "ต่ออายุครบจำนวนครั้งที่กำหนดแล้ว (1/1 ครั้ง)",
    ]
    assert payload["loan"]["due_date"] == due_date.isoformat()
    assert payload["loan"]["renewal_count"] == 1
    assert service.RENEWAL_AUDIT_LOG == []
