from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from ..book_search import models as catalog
from ..fine_payment.models import FineItem
from ..fine_payment.store import initialize_fine_store, insert_fine_item
from ..loans.service import _initialize_loan_store
from ..reservations.service import (
    first_waiting_reservation,
    reservation_store_transaction,
)

ASIA_BANGKOK = ZoneInfo("Asia/Bangkok")
FINE_RATE_CONFIG_PATH = Path(__file__).parents[1] / "fine_payment" / "rate.json"
PROVISIONAL_PICKUP_DAYS = 3


class ReturnError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def _daily_rate() -> Decimal:
    with FINE_RATE_CONFIG_PATH.open(encoding="utf-8") as policy_file:
        policy = json.load(policy_file)
    if not isinstance(policy, dict) or "daily_rate" not in policy:
        raise ValueError("Fine rate configuration must define daily_rate")
    try:
        rate = Decimal(str(policy["daily_rate"]))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError("Fine daily_rate must be a decimal value") from error
    if not rate.is_finite() or rate < 0:
        raise ValueError("Fine daily_rate must be a finite non-negative value")
    return rate


def _current_date(now: datetime | None = None) -> date:
    current_time = now or datetime.now(ASIA_BANGKOK)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=ASIA_BANGKOK)
    return current_time.astimezone(ASIA_BANGKOK).date()


def _active_loan(
    connection: sqlite3.Connection, item_identifier: str
) -> sqlite3.Row:
    rows = connection.execute(
        """
        SELECT loan_item_id, loan_id, member_id, title_id, item_identifier, due_date
        FROM loan_items
        WHERE item_identifier = ? AND status = 'Borrowed'
        """,
        (item_identifier,),
    ).fetchall()
    if not rows:
        raise ReturnError(
            404,
            "active_loan_not_found",
            "ไม่พบรายการยืมที่ยังไม่คืน กรุณาตรวจสอบข้อมูล",
        )
    if len(rows) > 1:
        raise ReturnError(
            409,
            "multiple_active_loans",
            "พบรายการยืมที่ยังไม่คืนหลายรายการ กรุณาให้เจ้าหน้าที่ตรวจสอบ",
        )
    return rows[0]


def _book_title(title_id: str) -> str:
    record = next(
        (item for item in catalog.CATALOG_RECORDS if item.book_id == title_id),
        None,
    )
    if record is None:
        raise ReturnError(404, "book_not_found", "ไม่พบข้อมูลหนังสือ")
    return record.title


def _fine_amount(due_date: date, returned_date: date, rate: Decimal) -> tuple[int, Decimal]:
    overdue_days = max((returned_date - due_date).days, 0)
    amount = (rate * overdue_days).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return overdue_days, amount


def lookup_return(
    item_identifier: str, *, now: datetime | None = None
) -> dict[str, Any]:
    """ค้นหารายการยืมและคำนวณยอดประมาณการ (FR-01 ถึง FR-03, ASM-09/ASM-10)."""
    returned_date = _current_date(now)
    rate = _daily_rate()
    with reservation_store_transaction() as connection:
        _initialize_loan_store(connection)
        initialize_fine_store(connection)
        active = _active_loan(connection, item_identifier)
        due_date = date.fromisoformat(active["due_date"])
        overdue_days, amount = _fine_amount(due_date, returned_date, rate)
        return {
            "success": True,
            "item_identifier": item_identifier,
            "loan_id": active["loan_id"],
            "member_id": active["member_id"],
            "book_title": _book_title(active["title_id"]),
            "due_date": due_date.isoformat(),
            "returned_date": returned_date.isoformat(),
            "overdue_days": overdue_days,
            "daily_rate": format(rate, "f"),
            "fine_amount": format(amount, ".2f"),
        }


def confirm_return(
    item_identifier: str, *, now: datetime | None = None
) -> dict[str, Any]:
    """บันทึกการคืน ค่าปรับ และสถานะคิวแบบ atomic (FR-04, ASM-11 ถึง ASM-15)."""
    returned_date = _current_date(now)
    rate = _daily_rate()
    with reservation_store_transaction() as connection:
        _initialize_loan_store(connection)
        initialize_fine_store(connection)
        active = _active_loan(connection, item_identifier)
        copy = connection.execute(
            """
            SELECT title_id, status FROM loan_copy_status
            WHERE item_identifier = ?
            """,
            (item_identifier,),
        ).fetchone()
        if copy is None or copy["status"] != "Borrowed":
            raise ReturnError(
                409,
                "copy_status_conflict",
                "สถานะหนังสือไม่ตรงกับรายการยืม กรุณาตรวจสอบข้อมูล",
            )

        due_date = date.fromisoformat(active["due_date"])
        overdue_days, amount = _fine_amount(due_date, returned_date, rate)
        fine_id = str(uuid.uuid4()) if amount > 0 else None
        title = _book_title(active["title_id"])

        updated_loan = connection.execute(
            """
            UPDATE loan_items
            SET status = 'Returned', returned_date = ?
            WHERE loan_item_id = ? AND status = 'Borrowed'
            """,
            (returned_date.isoformat(), active["loan_item_id"]),
        )
        if updated_loan.rowcount != 1:
            raise ReturnError(
                409,
                "loan_status_changed",
                "สถานะรายการยืมเปลี่ยนแปลง กรุณาตรวจสอบข้อมูล",
            )

        waiting = first_waiting_reservation(connection, active["title_id"])
        reservation_result = None
        if waiting:
            pickup_deadline = returned_date + timedelta(days=PROVISIONAL_PICKUP_DAYS)
            updated_reservation = connection.execute(
                """
                UPDATE reservations
                SET status = 'Ready', pickup_deadline = ?,
                    reserved_item_identifier = ?
                WHERE reservation_id = ? AND status = 'Waiting'
                """,
                (
                    pickup_deadline.isoformat(),
                    item_identifier,
                    waiting["reservation_id"],
                ),
            )
            if updated_reservation.rowcount != 1:
                raise ReturnError(
                    409,
                    "reservation_status_changed",
                    "สถานะรายการจองเปลี่ยนแปลง กรุณาลองใหม่",
                )
            copy_status = "Reserved"
            reservation_result = {
                "reservation_id": waiting["reservation_id"],
                "status": "Ready",
                "pickup_deadline": pickup_deadline.isoformat(),
            }
        else:
            copy_status = "Available"

        updated_copy = connection.execute(
            """
            UPDATE loan_copy_status SET status = ?
            WHERE item_identifier = ? AND status = 'Borrowed'
            """,
            (copy_status, item_identifier),
        )
        if updated_copy.rowcount != 1:
            raise ReturnError(
                409,
                "copy_status_changed",
                "สถานะหนังสือเปลี่ยนแปลง กรุณาลองใหม่",
            )

        if fine_id:
            fine = FineItem(
                fine_id=fine_id,
                member_id=active["member_id"],
                book_title=title,
                due_date=due_date,
                returned_date=returned_date,
                overdue_days=overdue_days,
                amount=amount,
            )
            insert_fine_item(
                connection,
                fine,
                loan_id=active["loan_id"],
                applied_rate=rate,
            )

        return {
            "success": True,
            "item_identifier": item_identifier,
            "loan_id": active["loan_id"],
            "returned_date": returned_date.isoformat(),
            "due_date": due_date.isoformat(),
            "book_title": title,
            "overdue_days": overdue_days,
            "daily_rate": format(rate, "f"),
            "fine_amount": format(amount, ".2f"),
            "fine_id": fine_id,
            "copy_status": copy_status,
            "reservation": reservation_result,
        }
