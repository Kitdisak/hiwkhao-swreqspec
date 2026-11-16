from __future__ import annotations

from datetime import date
from decimal import Decimal
from threading import RLock

from .models import (
    FineItem,
    FineStatus,
    PaymentRecord,
    PaymentRequest,
    PaymentReviewRecord,
)

DEMO_MEMBER_ID = "STU-001"

FINE_ITEMS: list[FineItem] = [
    FineItem(
        fine_id="FINE-001",
        member_id=DEMO_MEMBER_ID,
        book_title="การออกแบบซอฟต์แวร์",
        due_date=date(2026, 11, 10),
        returned_date=date(2026, 11, 12),
        overdue_days=2,
        amount=Decimal("10.00"),
    ),
    FineItem(
        fine_id="FINE-002",
        member_id=DEMO_MEMBER_ID,
        book_title="ฐานข้อมูลสำหรับนักพัฒนา",
        due_date=date(2026, 11, 8),
        returned_date=date(2026, 11, 11),
        overdue_days=3,
        amount=Decimal("15.00"),
    ),
]

PAYMENT_REQUESTS: dict[str, PaymentRequest] = {}
PAYMENT_RECORDS: dict[str, PaymentRecord] = {}
PAYMENT_REVIEW_RECORDS: list[PaymentReviewRecord] = []
STORE_LOCK = RLock()


def reset_store() -> None:
    with STORE_LOCK:
        for fine in FINE_ITEMS:
            fine.status = FineStatus.OUTSTANDING
        PAYMENT_REQUESTS.clear()
        PAYMENT_RECORDS.clear()
        PAYMENT_REVIEW_RECORDS.clear()
