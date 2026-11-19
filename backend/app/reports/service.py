from __future__ import annotations

import sqlite3
import unicodedata
import csv
import io
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from ..reservations.service import _connect
from ..rooms import store as room_store

ASIA_BANGKOK = ZoneInfo("Asia/Bangkok")
_THAI_CONSONANTS = "กขฃคฅฆงจฉชซฌญฎฏฐฑฒณดตถทธนบปผฝพฟภมยรลวศษสหฬอฮ"
_LEADING_VOWELS = "เแโใไ"
_THAI_RANK = {character: index for index, character in enumerate(_THAI_CONSONANTS)}


class ReportRangeError(ValueError):
    def __init__(self, code: str, message: str = "ช่วงวันที่ไม่ถูกต้อง") -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def validate_report_range(
    start_date: date,
    end_date: date,
    *,
    now: datetime | None = None,
) -> None:
    current = now or datetime.now(ASIA_BANGKOK)
    if current.tzinfo is None:
        current = current.replace(tzinfo=ASIA_BANGKOK)
    today = current.astimezone(ASIA_BANGKOK).date()

    if end_date < start_date:
        raise ReportRangeError("end_before_start")
    if end_date > today:
        raise ReportRangeError("end_after_today")
    if (end_date - start_date).days > 365:
        raise ReportRangeError("range_over_one_year")


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def loan_report(start_date: date, end_date: date) -> dict[str, Any]:
    connection = _connect()
    try:
        if not _table_exists(connection, "loan_items"):
            return {"count": 0, "rows": []}
        rows = connection.execute(
            """
            SELECT COUNT(*) AS item_count
            FROM loan_items AS li
            JOIN loans AS l ON l.loan_id = li.loan_id
            WHERE DATE(l.borrowed_on) BETWEEN ? AND ?
            """,
            (start_date.isoformat(), end_date.isoformat()),
        ).fetchall()
        return {"count": rows[0]["item_count"], "rows": []}
    finally:
        connection.close()


def _title_sort_key(title: str) -> tuple[int, str]:
    normalized = unicodedata.normalize("NFC", title.strip()).casefold()
    while normalized and normalized[0] in _LEADING_VOWELS:
        normalized = normalized[1:]
    first = normalized[0] if normalized else ""
    if first in _THAI_RANK:
        category = 0
    elif first.isalpha():
        category = 1
    else:
        category = 2
    return category, normalized


def popular_books_report(start_date: date, end_date: date) -> dict[str, Any]:
    connection = _connect()
    try:
        if not _table_exists(connection, "loan_items"):
            return {"rows": []}
        catalog_exists = _table_exists(connection, "catalog_records")
        if catalog_exists:
            rows = connection.execute(
                """
                SELECT li.title_id, cr.title AS title_name,
                       COUNT(*) AS borrow_count
                FROM loan_items AS li
                JOIN loans AS l ON l.loan_id = li.loan_id
                LEFT JOIN catalog_records AS cr ON cr.book_id = li.title_id
                WHERE DATE(l.borrowed_on) BETWEEN ? AND ?
                GROUP BY li.title_id, cr.title
                """,
                (start_date.isoformat(), end_date.isoformat()),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT li.title_id, li.title_id AS title_name,
                       COUNT(*) AS borrow_count
                FROM loan_items AS li
                JOIN loans AS l ON l.loan_id = li.loan_id
                WHERE DATE(l.borrowed_on) BETWEEN ? AND ?
                GROUP BY li.title_id
                """,
                (start_date.isoformat(), end_date.isoformat()),
            ).fetchall()
    finally:
        connection.close()

    ranked = [
        {
            "title_id": row["title_id"],
            "title_name": row["title_name"] or row["title_id"],
            "borrow_count": row["borrow_count"],
        }
        for row in rows
    ]
    ranked.sort(
        key=lambda item: (
            -item["borrow_count"],
            _title_sort_key(item["title_name"]),
            item["title_id"].casefold(),
        )
    )
    return {"rows": ranked[:10]}


def fine_report(start_date: date, end_date: date) -> dict[str, Any]:
    totals = {
        "all": Decimal("0.00"),
        "paid": Decimal("0.00"),
        "outstanding": Decimal("0.00"),
    }
    connection = _connect()
    try:
        if not _table_exists(connection, "fine_items"):
            return {
                "total_all": "0.00",
                "total_paid": "0.00",
                "total_outstanding": "0.00",
                "rows": [],
            }
        rows = connection.execute(
            """
            SELECT amount, status
            FROM fine_items
            WHERE DATE(returned_date) BETWEEN ? AND ?
            """,
            (start_date.isoformat(), end_date.isoformat()),
        ).fetchall()
    finally:
        connection.close()

    for row in rows:
        try:
            amount = Decimal(row["amount"]).quantize(Decimal("0.01"))
        except Exception:
            continue
        totals["all"] += amount
        if row["status"] == "paid":
            totals["paid"] += amount
        else:
            totals["outstanding"] += amount

    return {
        "total_all": format(totals["all"], ".2f"),
        "total_paid": format(totals["paid"], ".2f"),
        "total_outstanding": format(totals["outstanding"], ".2f"),
        "rows": [],
    }


def room_usage_report(start_date: date, end_date: date) -> dict[str, Any]:
    grouped: dict[str, dict[str, Any]] = {}
    for booking in room_store.get_room_bookings():
        if booking.status == "ยกเลิกแล้ว":
            continue
        if not (start_date <= booking.booking_date <= end_date):
            continue
        room = grouped.setdefault(
            booking.room_id,
            {"room_id": booking.room_id, "booking_count": 0, "booked_hours": Decimal("0")},
        )
        room["booking_count"] += 1
        start_minutes = booking.start_time.hour * 60 + booking.start_time.minute
        end_minutes = booking.end_time.hour * 60 + booking.end_time.minute
        room["booked_hours"] += Decimal(end_minutes - start_minutes) / Decimal("60")

    rows = []
    for room_id in sorted(grouped):
        booked_hours = grouped[room_id]["booked_hours"].quantize(Decimal("0.01"))
        rows.append(
            {
                "room_id": room_id,
                "booking_count": grouped[room_id]["booking_count"],
                "booked_hours": format(booked_hours, ".2f"),
            }
        )
    return {"rows": rows}


def get_report(report_type: str, start_date: date, end_date: date) -> dict[str, Any]:
    validate_report_range(start_date, end_date)
    normalized = report_type.strip().casefold()
    aliases = {
        "loans": ("loan", "loans", "การยืม", "borrow"),
        "popular_books": ("popular", "popular_books", "หนังสือยอดนิยม"),
        "fines": ("fine", "fines", "ค่าปรับ"),
        "room_usage": ("room", "rooms", "room_usage", "การใช้ห้อง"),
    }
    selected = next(
        (
            name
            for name, values in aliases.items()
            if normalized in values
        ),
        None,
    )
    if selected is None:
        return {
            "success": False,
            "code": "invalid_report_type",
            "message": "ประเภทรายงานไม่ถูกต้อง",
            "has_data": False,
        }

    if selected == "loans":
        data = loan_report(start_date, end_date)
        has_data = data["count"] > 0
    elif selected == "popular_books":
        data = popular_books_report(start_date, end_date)
        has_data = bool(data["rows"])
    elif selected == "fines":
        data = fine_report(start_date, end_date)
        has_data = any(
            Decimal(data[key]) > 0
            for key in ("total_all", "total_paid", "total_outstanding")
        )
    else:
        data = room_usage_report(start_date, end_date)
        has_data = bool(data["rows"])

    result: dict[str, Any] = {
        "success": True,
        "report_type": selected,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "has_data": has_data,
        "data": data,
    }
    if not has_data:
        result["message"] = "ไม่พบข้อมูลในช่วงเวลาที่เลือก"
    return result


def build_report_csv(report_type: str, result: dict[str, Any]) -> tuple[bytes, str]:
    selected = result["report_type"]
    start_date = result["start_date"]
    end_date = result["end_date"]
    data = result["data"]
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")

    if selected == "loans":
        writer.writerow(["ช่วงวันที่เริ่ม", "ช่วงวันที่สิ้นสุด", "จำนวนรายการยืม"])
        writer.writerow([start_date, end_date, data["count"]])
    elif selected == "popular_books":
        writer.writerow(["อันดับ", "รหัสหนังสือ", "ชื่อหนังสือ", "จำนวนครั้งยืม"])
        for index, row in enumerate(data["rows"], start=1):
            writer.writerow([index, row["title_id"], row["title_name"], row["borrow_count"]])
    elif selected == "fines":
        writer.writerow(["ค่าปรับที่เกิดขึ้นทั้งหมด", "ชำระแล้ว", "ยังไม่ชำระ"])
        writer.writerow([data["total_all"], data["total_paid"], data["total_outstanding"]])
    else:
        writer.writerow(["รหัสห้อง", "จำนวนรายการจอง", "จำนวนชั่วโมงที่ถูกจอง"])
        for row in data["rows"]:
            writer.writerow([row["room_id"], row["booking_count"], row["booked_hours"]])

    filename = f"report-{selected}-{start_date}-{end_date}.csv"
    text = output.getvalue()
    return ("\ufeff" + text).encode("utf-8"), filename
