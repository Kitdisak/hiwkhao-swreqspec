from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .models import DEFAULT_RENEWAL_POLICY, Loan, LoanRenewalAudit, ROSTER, RENEWAL_AUDIT_LOG, normalize_member_type

ASIA_BANGKOK = ZoneInfo("Asia/Bangkok")

LOANS: list[Loan] = ROSTER


def get_member_loans(member_id: str | None = None) -> list[dict[str, Any]]:
    if member_id is None:
        return [loan.to_dict() for loan in LOANS if loan.status == "borrowed"]
    return [loan.to_dict() for loan in LOANS if loan.member_id == member_id and loan.status == "borrowed"]


def _get_policy(member_type: str | None) -> dict[str, int]:
    normalized = normalize_member_type(member_type)
    policy = DEFAULT_RENEWAL_POLICY.get(normalized)
    if policy is None:
        return {"renewal_days": 7, "max_renewals": 1}
    return {"renewal_days": policy.renewal_days, "max_renewals": policy.max_renewals}


def _is_overdue(due_date: date, current_day: date) -> bool:
    return current_day > due_date


def _days_remaining(due_date: date, current_day: date) -> int:
    return (due_date - current_day).days


def _is_near_due(due_date: date, current_day: date) -> bool:
    remaining = _days_remaining(due_date, current_day)
    return 0 <= remaining <= 3


def _advance_due_date(base_date: date, renewal_days: int) -> date:
    updated = base_date
    for _ in range(renewal_days):
        updated += timedelta(days=1)
        while updated.weekday() >= 5:
            updated += timedelta(days=1)
    return updated


def _all_reasons(loan: Loan, current_day: date, member_type: str | None) -> list[str]:
    reasons: list[str] = []
    if _is_overdue(loan.due_date, current_day):
        reasons.append("หนังสือเกินกำหนดคืนแล้ว กรุณาคืนหนังสือที่เคาน์เตอร์")
    if loan.waiting_reservations > 0:
        reasons.append("มีผู้จองหนังสือเล่มนี้ไว้")
    policy = _get_policy(member_type or loan.member_type)
    if loan.renewal_count >= policy["max_renewals"]:
        reasons.append(f"ต่ออายุครบจำนวนครั้งที่กำหนดแล้ว ({loan.renewal_count}/{policy['max_renewals']} ครั้ง)")
    return reasons


def _loan_for_id(loan_id: str) -> Loan | None:
    for loan in LOANS:
        if loan.loan_id == loan_id:
            return loan
    return None


def renew_loan(
    loan_id: str,
    *,
    member_id: str | None = None,
    member_type: str | None = None,
    renewed_by: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    current_time = now or datetime.now(ASIA_BANGKOK)
    current_day = current_time.date()
    loan = _loan_for_id(loan_id)
    if loan is None:
        return {
            "success": False,
            "message": "ไม่พบรายการยืม",
            "reasons": [],
            "loan": None,
        }

    if member_id is not None and loan.member_id != member_id:
        return {
            "success": False,
            "message": "ทำรายการไม่สำเร็จ กรุณาลองใหม่อีกครั้ง",
            "reasons": [],
            "loan": loan.to_dict(),
        }

    if loan.status != "borrowed":
        return {
            "success": False,
            "message": "ไม่สามารถต่ออายุได้",
            "reasons": ["หนังสือเกินกำหนดคืนแล้ว กรุณาคืนหนังสือที่เคาน์เตอร์"],
            "loan": loan.to_dict(),
        }

    if loan.fine_amount > 100 or loan.suspended:
        return {
            "success": False,
            "message": "ทำรายการไม่สำเร็จ กรุณาลองใหม่อีกครั้ง",
            "reasons": [],
            "loan": loan.to_dict(),
        }

    effective_member_type = normalize_member_type(member_type or loan.member_type)
    reasons = _all_reasons(loan, current_day, effective_member_type)
    if reasons:
        return {
            "success": False,
            "message": "ไม่สามารถต่ออายุได้",
            "reasons": reasons,
            "loan": loan.to_dict(),
        }

    if not _is_near_due(loan.due_date, current_day):
        return {
            "success": False,
            "message": "ไม่สามารถต่ออายุได้",
            "reasons": [],
            "loan": loan.to_dict(),
        }

    policy = _get_policy(effective_member_type)
    old_due_date = loan.due_date.isoformat()
    new_due_date = _advance_due_date(loan.due_date, policy["renewal_days"])

    updated_loan = Loan(
        loan_id=loan.loan_id,
        member_id=loan.member_id,
        member_type=loan.member_type,
        book_id=loan.book_id,
        due_date=new_due_date,
        renewal_count=loan.renewal_count + 1,
        status=loan.status,
        waiting_reservations=loan.waiting_reservations,
        fine_amount=loan.fine_amount,
        suspended=loan.suspended,
        last_renewed_at=current_time.isoformat(),
    )
    for index, existing in enumerate(LOANS):
        if existing.loan_id == loan_id:
            LOANS[index] = updated_loan
            break

    audit = LoanRenewalAudit(
        loan_id=updated_loan.loan_id,
        member_id=updated_loan.member_id,
        old_due_date=old_due_date,
        new_due_date=new_due_date.isoformat(),
        renewed_by=renewed_by or updated_loan.member_id,
        renewed_at=current_time.isoformat(),
        renewal_days=policy["renewal_days"],
    )
    RENEWAL_AUDIT_LOG.append(audit.to_dict())

    return {
        "success": True,
        "message": "ต่ออายุสำเร็จ",
        "reasons": [],
        "loan": updated_loan.to_dict(),
        "audit": audit.to_dict(),
    }
