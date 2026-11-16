from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any


@dataclass
class RenewalPolicy:
    member_type: str
    renewal_days: int
    max_renewals: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "member_type": self.member_type,
            "renewal_days": self.renewal_days,
            "max_renewals": self.max_renewals,
        }


@dataclass
class Loan:
    loan_id: str
    member_id: str
    member_type: str
    book_id: str
    due_date: date | str
    renewal_count: int = 0
    status: str = "borrowed"
    waiting_reservations: int = 0
    fine_amount: float = 0.0
    suspended: bool = False
    last_renewed_at: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.due_date, str):
            self.due_date = date.fromisoformat(self.due_date)

    def to_dict(self) -> dict[str, Any]:
        return {
            "loan_id": self.loan_id,
            "member_id": self.member_id,
            "member_type": self.member_type,
            "book_id": self.book_id,
            "due_date": self.due_date.isoformat(),
            "renewal_count": self.renewal_count,
            "status": self.status,
            "waiting_reservations": self.waiting_reservations,
            "fine_amount": self.fine_amount,
            "suspended": self.suspended,
            "last_renewed_at": self.last_renewed_at,
        }


@dataclass
class LoanRenewalAudit:
    loan_id: str
    member_id: str
    old_due_date: str
    new_due_date: str
    renewed_by: str
    renewed_at: str
    renewal_days: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "loan_id": self.loan_id,
            "member_id": self.member_id,
            "old_due_date": self.old_due_date,
            "new_due_date": self.new_due_date,
            "renewed_by": self.renewed_by,
            "renewed_at": self.renewed_at,
            "renewal_days": self.renewal_days,
        }


DEFAULT_RENEWAL_POLICY: dict[str, RenewalPolicy] = {
    "undergraduate": RenewalPolicy(member_type="undergraduate", renewal_days=7, max_renewals=1),
    "graduate": RenewalPolicy(member_type="graduate", renewal_days=14, max_renewals=2),
    "staff": RenewalPolicy(member_type="staff", renewal_days=30, max_renewals=3),
}


def normalize_member_type(member_type: str | None) -> str:
    cleaned = (member_type or "").strip().lower()
    if cleaned in {"undergraduate", "undergrad", "student", "student_undergraduate"}:
        return "undergraduate"
    if cleaned in {"graduate", "postgraduate", "student_graduate"}:
        return "graduate"
    if cleaned in {"staff", "faculty", "employee", "academic", "lecturer"}:
        return "staff"
    return cleaned or "undergraduate"


ROSTER: list[Loan] = [
    Loan(
        loan_id="LOAN-001",
        member_id="STU-001",
        member_type="undergraduate",
        book_id="BOOK-001",
        due_date=(date.today() + timedelta(days=2)).isoformat(),
        renewal_count=0,
        status="borrowed",
        waiting_reservations=0,
        fine_amount=0,
        suspended=False,
    ),
    Loan(
        loan_id="LOAN-002",
        member_id="GRAD-001",
        member_type="graduate",
        book_id="BOOK-002",
        due_date=(date.today() + timedelta(days=5)).isoformat(),
        renewal_count=1,
        status="borrowed",
        waiting_reservations=0,
        fine_amount=0,
        suspended=False,
    ),
    Loan(
        loan_id="LOAN-003",
        member_id="STAFF-001",
        member_type="staff",
        book_id="BOOK-003",
        due_date=(date.today() + timedelta(days=10)).isoformat(),
        renewal_count=2,
        status="borrowed",
        waiting_reservations=0,
        fine_amount=0,
        suspended=False,
    ),
]


RENEWAL_AUDIT_LOG: list[dict[str, Any]] = []
