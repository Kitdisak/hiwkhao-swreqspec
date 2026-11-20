from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any


class FineStatus(StrEnum):
    OUTSTANDING = "outstanding"
    PAID = "paid"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    DUPLICATE_REFUND_PENDING = "ชำระซ้ำ – รอคืนเงิน"


@dataclass
class FineItem:
    fine_id: str
    member_id: str
    book_title: str
    due_date: date
    returned_date: date
    overdue_days: int
    amount: Decimal
    status: FineStatus = FineStatus.OUTSTANDING

    def to_dict(self) -> dict[str, Any]:
        return {
            "fine_id": self.fine_id,
            "member_id": self.member_id,
            "book_title": self.book_title,
            "due_date": self.due_date.isoformat(),
            "returned_date": self.returned_date.isoformat(),
            "overdue_days": self.overdue_days,
            "amount": format(self.amount, ".2f"),
            "status": self.status.value,
        }


@dataclass
class PaymentRequest:
    payment_ref: str
    member_id: str
    fine_ids: tuple[str, ...]
    amount: Decimal
    channel: str
    status: PaymentStatus
    created_at: datetime
    expires_at: datetime
    last_checked_at: datetime | None = None
    gateway_transaction_number: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "payment_ref": self.payment_ref,
            "member_id": self.member_id,
            "fine_ids": list(self.fine_ids),
            "amount": format(self.amount, ".2f"),
            "channel": self.channel,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "last_checked_at": self.last_checked_at.isoformat() if self.last_checked_at else None,
            "gateway_transaction_number": self.gateway_transaction_number,
        }


@dataclass(frozen=True)
class GatewayResult:
    payment_ref: str
    amount: Decimal
    status: PaymentStatus
    transaction_number: str | None = None


@dataclass(frozen=True)
class PaymentRecord:
    payment_ref: str
    transaction_number: str
    amount: Decimal
    fine_ids: tuple[str, ...]
    paid_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "payment_ref": self.payment_ref,
            "transaction_number": self.transaction_number,
            "amount": format(self.amount, ".2f"),
            "fine_ids": list(self.fine_ids),
            "paid_at": self.paid_at.isoformat(),
        }


@dataclass(frozen=True)
class PaymentReviewRecord:
    review_id: str
    received_payment_ref: str
    reported_amount: Decimal | None
    reason: str
    created_at: datetime
    gateway_transaction_number: str | None = None
    expected_amount: Decimal | None = None
    raw_gateway_data: dict[str, Any] | None = None
    status: str = "pending"
    resolved_by: str | None = None
    resolved_at: datetime | None = None
    resolution_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "review_id": self.review_id,
            "received_payment_ref": self.received_payment_ref,
            "reported_amount": (
                format(self.reported_amount, ".2f") if self.reported_amount is not None else None
            ),
            "gateway_transaction_number": self.gateway_transaction_number,
            "expected_amount": (
                format(self.expected_amount, ".2f") if self.expected_amount is not None else None
            ),
            "raw_gateway_data": self.raw_gateway_data,
            "reason": self.reason,
            "created_at": self.created_at.isoformat(),
            "status": self.status,
            "resolved_by": self.resolved_by,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "resolution_reason": self.resolution_reason,
        }
