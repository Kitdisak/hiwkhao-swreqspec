from __future__ import annotations

import os
import sqlite3
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
from contextlib import contextmanager

from ..auth.models import User
from ..book_search import models as catalog

_THAI_CONSONANTS = "กขฃคฅฆงจฉชซฌญฎฏฐฑฒณดตถทธนบปผฝพฟภมยรลวศษสหฬอฮ"
_LEADING_VOWELS = "เแโใไ"
_THAI_CONSONANT_RANK = {character: index for index, character in enumerate(_THAI_CONSONANTS)}


@contextmanager
def reservation_store_transaction() -> Iterator[sqlite3.Connection]:
    """เปิด transaction ที่ใช้ store การจองเดิมร่วมกับการบันทึกการยืม."""
    connection = _connect()
    try:
        connection.execute("BEGIN IMMEDIATE")
        yield connection
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def member_id_for_user(member: User) -> str:
    return _member_id(member)


@dataclass
class ReservationError(Exception):
    status_code: int
    code: str
    message: str


def _database_path() -> Path:
    configured = os.environ.get("LIBRARY_RESERVATION_DB")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[2] / "data" / "reservations.sqlite3"


def _connect() -> sqlite3.Connection:
    path = _database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 10000")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS reservations (
            reservation_id TEXT PRIMARY KEY,
            request_id TEXT NOT NULL UNIQUE,
            member_id TEXT NOT NULL,
            title_id TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('Waiting', 'Ready', 'Completed')),
            pickup_deadline TEXT,
            reserved_item_identifier TEXT,
            queue_position_at_success INTEGER NOT NULL,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            member_code TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS one_pending_reservation_per_member_title
        ON reservations(member_id, title_id)
        WHERE status IN ('Waiting', 'Ready');
        """
    )
    columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(reservations)")
    }
    if "pickup_deadline" not in columns:
        connection.execute("ALTER TABLE reservations ADD COLUMN pickup_deadline TEXT")
    if "reserved_item_identifier" not in columns:
        connection.execute(
            "ALTER TABLE reservations ADD COLUMN reserved_item_identifier TEXT"
        )
    return connection


def _name_sort_key(value: str) -> tuple[int, str]:
    normalized = unicodedata.normalize("NFC", value.strip()).casefold()
    while normalized and normalized[0] in _LEADING_VOWELS:
        normalized = normalized[1:]
    first = normalized[0] if normalized else ""
    if first in _THAI_CONSONANT_RANK:
        category = 0
    elif first.isalpha():
        category = 1
    else:
        category = 2
    return category, normalized


def _reservation_sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row["recorded_at"],
        _name_sort_key(row["first_name"]),
        _name_sort_key(row["last_name"]),
        row["member_code"].casefold(),
    )


def _catalog_record(title_id: str):
    return next(
        (record for record in catalog.CATALOG_RECORDS if record.book_id == title_id),
        None,
    )


def _copy_statuses(
    title_id: str, connection: sqlite3.Connection
) -> list[str | None]:
    record = _catalog_record(title_id)
    if record is None:
        raise ReservationError(404, "book_not_found", "ไม่พบหนังสือที่เลือก")
    has_copy_status_store = connection.execute(
        """
        SELECT 1 FROM sqlite_master
        WHERE type = 'table' AND name = 'loan_copy_status'
        """
    ).fetchone()
    if not has_copy_status_store:
        return [copy.status for copy in record.copies]

    statuses = {
        row["item_identifier"]: row["status"]
        for row in connection.execute(
            "SELECT item_identifier, status FROM loan_copy_status WHERE title_id = ?",
            (title_id,),
        ).fetchall()
    }
    return [
        statuses.get(copy.item_identifier, copy.status) for copy in record.copies
    ]


def _eligibility_reasons(member: User) -> list[str]:
    reasons = []
    if member.account_status == "Suspended":
        reasons.append("บัญชีถูกระงับ")
    if member.overdue_count > 0:
        reasons.append("มีหนังสือเกินกำหนด")
    if member.unpaid_fine_count > 0:
        reasons.append("มีค่าปรับค้างชำระ")
    return reasons


def _book_unavailable_message(
    title_id: str, connection: sqlite3.Connection
) -> str | None:
    statuses = _copy_statuses(title_id, connection)
    if "Available" in statuses:
        return "มีเล่มว่าง สามารถยืมได้ที่ห้องสมุด"
    reservable_statuses = {"Borrowed", "Reserved"}
    blocked_statuses = {"Lost", "Damaged", "อยู่ระหว่างซ่อม"}
    if not statuses or any(status is None for status in statuses):
        raise ReservationError(
            503, "book_status_unavailable", "ไม่สามารถตรวจสอบสถานะหนังสือได้"
        )
    if not any(status in reservable_statuses for status in statuses):
        if all(status in blocked_statuses for status in statuses):
            return "หนังสือนี้ไม่พร้อมให้บริการ"
        raise ReservationError(
            503, "book_status_unavailable", "ไม่สามารถตรวจสอบสถานะหนังสือได้"
        )
    if any(status not in reservable_statuses | blocked_statuses for status in statuses):
        raise ReservationError(
            503, "book_status_unavailable", "ไม่สามารถตรวจสอบสถานะหนังสือได้"
        )
    return None


def _current_queue_position(
    connection: sqlite3.Connection, reservation: sqlite3.Row
) -> int:
    if reservation["status"] != "Waiting":
        return reservation["queue_position_at_success"]
    waiting = [
        dict(row)
        for row in connection.execute(
            """
            SELECT reservation_id, recorded_at, first_name, last_name, member_code
            FROM reservations WHERE title_id = ? AND status = 'Waiting'
            """,
            (reservation["title_id"],),
        ).fetchall()
    ]
    waiting.sort(key=_reservation_sort_key)
    return next(
        index
        for index, row in enumerate(waiting, start=1)
        if row["reservation_id"] == reservation["reservation_id"]
    )


def first_waiting_reservation(
    connection: sqlite3.Connection, title_id: str
) -> dict[str, Any] | None:
    """เลือกคิว Waiting แรกด้วยลำดับเดิมของ SPEC-004 (SPEC-012 ASM-14)."""
    waiting = [
        dict(row)
        for row in connection.execute(
            """
            SELECT reservation_id, recorded_at, first_name, last_name, member_code
            FROM reservations WHERE title_id = ? AND status = 'Waiting'
            """,
            (title_id,),
        ).fetchall()
    ]
    if not waiting:
        return None
    waiting.sort(key=_reservation_sort_key)
    return waiting[0]


def _member_id(member: User) -> str:
    return member.student_id or member.username


def _member_snapshot(member: User) -> tuple[str, str, str]:
    return member.first_name, member.last_name, member.student_id or member.username


def reserve_book(member: User, title_id: str, request_id: str) -> dict[str, Any]:
    if not request_id.strip() or len(request_id) > 200:
        raise ReservationError(422, "invalid_request_id", "กรุณาระบุตัวระบุคำขอ")

    member_id = _member_id(member)
    connection = _connect()
    try:
        connection.execute("BEGIN IMMEDIATE")
        existing_request = connection.execute(
            "SELECT * FROM reservations WHERE request_id = ?", (request_id,)
        ).fetchone()
        if existing_request:
            if (
                existing_request["member_id"] != member_id
                or existing_request["title_id"] != title_id
            ):
                raise ReservationError(
                    409, "request_id_conflict", "ตัวระบุคำขอนี้ถูกใช้แล้ว"
                )
            result = _success_result(existing_request)
            connection.commit()
            return result

        pending = connection.execute(
            """
            SELECT * FROM reservations
            WHERE member_id = ? AND title_id = ? AND status IN ('Waiting', 'Ready')
            """,
            (member_id, title_id),
        ).fetchone()
        if pending:
            queue_position = _current_queue_position(connection, pending)
            raise ReservationError(
                409,
                "reservation_exists",
                f"คุณมีรายการจองหนังสือเล่มนี้อยู่แล้ว ลำดับคิวที่ {queue_position}",
            )

        reasons = _eligibility_reasons(member)
        if reasons:
            raise ReservationError(403, "member_ineligible", " และ ".join(reasons))

        unavailable_message = _book_unavailable_message(title_id, connection)
        if unavailable_message:
            raise ReservationError(409, "book_unavailable", unavailable_message)

        first_name, last_name, member_code = _member_snapshot(member)
        recorded_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        queue = [
            dict(row)
            for row in connection.execute(
                """
                SELECT recorded_at, first_name, last_name, member_code
                FROM reservations WHERE title_id = ? AND status = 'Waiting'
                """,
                (title_id,),
            ).fetchall()
        ]
        candidate = {
            "recorded_at": recorded_at,
            "first_name": first_name,
            "last_name": last_name,
            "member_code": member_code,
        }
        queue_position = len(
            [row for row in queue if _reservation_sort_key(row) < _reservation_sort_key(candidate)]
        ) + 1
        reservation_id = f"RSV-{request_id}"
        connection.execute(
            """
            INSERT INTO reservations (
                reservation_id, request_id, member_id, title_id, recorded_at, status,
                queue_position_at_success, first_name, last_name, member_code
            ) VALUES (?, ?, ?, ?, ?, 'Waiting', ?, ?, ?, ?)
            """,
            (
                reservation_id,
                request_id,
                member_id,
                title_id,
                recorded_at,
                queue_position,
                first_name,
                last_name,
                member_code,
            ),
        )
        result = {
            "success": True,
            "reservation_id": reservation_id,
            "status": "Waiting",
            "queue_position": queue_position,
            "message": f"จองสำเร็จ ลำดับคิวที่ {queue_position}",
        }
        connection.commit()
        return result
    finally:
        connection.close()


def _success_result(row: sqlite3.Row) -> dict[str, Any]:
    queue_position = row["queue_position_at_success"]
    return {
        "success": True,
        "reservation_id": row["reservation_id"],
        "status": row["status"],
        "queue_position": queue_position,
        "message": f"จองสำเร็จ ลำดับคิวที่ {queue_position}",
    }


def list_reservations_for_member(member: User) -> list[dict[str, Any]]:
    """อ่านรายการล่าสุดของสมาชิกและคำนวณคิว Waiting ใหม่
    (FR-ติดตามสถานะการจองหนังสือ-01 ถึง FR-ติดตามสถานะการจองหนังสือ-03, NFR-ACC-01, ASM-08, ASM-09).
    """
    connection = _connect()
    try:
        connection.execute("BEGIN")
        rows = connection.execute(
            "SELECT * FROM reservations WHERE member_id = ?",
            (_member_id(member),),
        ).fetchall()
        reservations = []
        for row in rows:
            record = _catalog_record(row["title_id"])
            if record is None:
                raise ReservationError(
                    404,
                    "reservation_title_not_found",
                    "ไม่พบข้อมูลชื่อหนังสือของรายการจอง",
                )
            reservations.append(
                {
                    "reservation_id": row["reservation_id"],
                    "title": record.title,
                    "authors": [author for author in record.authors if author],
                    "recorded_at": row["recorded_at"],
                    "status": row["status"],
                    "queue_position": (
                        _current_queue_position(connection, row)
                        if row["status"] == "Waiting"
                        else None
                    ),
                    "pickup_deadline": (
                        row["pickup_deadline"]
                        if row["status"] == "Ready"
                        else None
                    ),
                }
            )
        connection.commit()
        return reservations
    finally:
        connection.close()


def list_reservations_for_testing() -> list[dict[str, Any]]:
    connection = _connect()
    try:
        return [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM reservations ORDER BY recorded_at, reservation_id"
            ).fetchall()
        ]
    finally:
        connection.close()
