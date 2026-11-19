from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from ..auth.models import User
from ..renew_loan.service import get_member_loans
from ..reservations.service import (
    member_id_for_user,
    reservation_store_transaction,
)

ASIA_BANGKOK = ZoneInfo("Asia/Bangkok")
GENERAL_BOOK_TYPE = "หนังสือทั่วไป"
POLICY_CONFIG_PATH = Path(__file__).with_name("policies.json")
GENERIC_REJECTION = "ไม่สามารถยืมได้"
logger = logging.getLogger(__name__)


@dataclass
class LoanError(Exception):
    status_code: int
    code: str
    message: str


def _policy_config() -> list[dict[str, Any]]:
    with POLICY_CONFIG_PATH.open(encoding="utf-8") as policy_file:
        policies = json.load(policy_file)
    if not isinstance(policies, list):
        raise ValueError("Loan policy configuration must be a list")
    return policies


def _initialize_loan_store(connection: sqlite3.Connection) -> None:
    statements = (
        """
        CREATE TABLE IF NOT EXISTS loan_policies (
            member_type TEXT NOT NULL,
            book_type TEXT NOT NULL,
            maximum_items INTEGER NOT NULL CHECK (maximum_items > 0),
            loan_days INTEGER NOT NULL CHECK (loan_days > 0),
            PRIMARY KEY (member_type, book_type)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS loans (
            loan_id TEXT PRIMARY KEY,
            member_id TEXT NOT NULL,
            request_id TEXT NOT NULL UNIQUE,
            borrowed_on TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS loan_items (
            loan_item_id TEXT PRIMARY KEY,
            loan_id TEXT NOT NULL REFERENCES loans(loan_id),
            member_id TEXT NOT NULL,
            title_id TEXT NOT NULL,
            item_identifier TEXT NOT NULL,
            due_date TEXT NOT NULL,
            returned_date TEXT,
            status TEXT NOT NULL CHECK (status IN ('Borrowed', 'Returned'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS loan_requests (
            request_id TEXT PRIMARY KEY,
            member_id TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            result_json TEXT NOT NULL
        )
        """,
    )
    for statement in statements:
        connection.execute(statement)

    loan_item_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(loan_items)")
    }
    if "returned_date" not in loan_item_columns:
        connection.execute("DROP INDEX IF EXISTS one_active_loan_per_copy")
        connection.execute("ALTER TABLE loan_items RENAME TO loan_items_legacy")
        connection.execute(
            """
            CREATE TABLE loan_items (
                loan_item_id TEXT PRIMARY KEY,
                loan_id TEXT NOT NULL REFERENCES loans(loan_id),
                member_id TEXT NOT NULL,
                title_id TEXT NOT NULL,
                item_identifier TEXT NOT NULL,
                due_date TEXT NOT NULL,
                returned_date TEXT,
                status TEXT NOT NULL CHECK (status IN ('Borrowed', 'Returned'))
            )
            """
        )
        connection.execute(
            """
            INSERT INTO loan_items (
                loan_item_id, loan_id, member_id, title_id, item_identifier,
                due_date, returned_date, status
            )
            SELECT loan_item_id, loan_id, member_id, title_id, item_identifier,
                due_date, NULL, status
            FROM loan_items_legacy
            """
        )
        connection.execute("DROP TABLE loan_items_legacy")
    try:
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS one_active_loan_per_copy
            ON loan_items(item_identifier) WHERE status = 'Borrowed'
            """
        )
    except sqlite3.IntegrityError:
        duplicate = connection.execute(
            """
            SELECT 1 FROM loan_items
            WHERE status = 'Borrowed'
            GROUP BY item_identifier HAVING COUNT(*) > 1
            LIMIT 1
            """
        ).fetchone()
        if duplicate is None:
            raise
        logger.error(
            "Duplicate active LoanItems detected; active-loan uniqueness index cannot be created"
        )

    for policy in _policy_config():
        connection.execute(
            """
            INSERT OR IGNORE INTO loan_policies (
                member_type, book_type, maximum_items, loan_days
            ) VALUES (?, ?, ?, ?)
            """,
            (
                policy["member_type"],
                policy["book_type"],
                policy["maximum_items"],
                policy["loan_days"],
            ),
        )

def _member_profile(member: User) -> dict[str, Any]:
    return {
        "member_id": member_id_for_user(member),
        "student_id": member.student_id,
        "display_name": " ".join(
            part for part in (member.first_name, member.last_name) if part
        )
        or member.username,
        "member_type": member.user_type,
        "account_status": member.account_status,
    }


def member_is_eligible(member: User) -> bool:
    return (
        member.user_type != "external"
        and member.account_status == "Active"
        and member.overdue_count == 0
        and member.unpaid_fine_count == 0
    )


def _outstanding_count(connection: sqlite3.Connection, member_id: str) -> int:
    stored_count = connection.execute(
        """
        SELECT COUNT(*) AS item_count
        FROM loan_items
        WHERE member_id = ? AND status = 'Borrowed'
        """,
        (member_id,),
    ).fetchone()["item_count"]
    return stored_count + len(get_member_loans(member_id))


def _copy_for_identifier(
    connection: sqlite3.Connection, item_identifier: str
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT item_identifier, book_id AS title_id,
            COALESCE(book_type, ?) AS book_type, status
        FROM book_copies WHERE item_identifier = ?
        """,
        (GENERAL_BOOK_TYPE, item_identifier),
    ).fetchone()


def _policy_for_copy(
    connection: sqlite3.Connection, member: User, book_type: str
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT maximum_items, loan_days
        FROM loan_policies
        WHERE member_type = ? AND book_type = ?
        """,
        (member.user_type, book_type),
    ).fetchone()


def _ready_reservation(
    connection: sqlite3.Connection,
    member_id: str,
    title_id: str,
    item_identifier: str,
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT reservation_id
        FROM reservations
        WHERE member_id = ? AND title_id = ? AND status = 'Ready'
            AND reserved_item_identifier = ?
        """,
        (member_id, title_id, item_identifier),
    ).fetchone()


def _copy_is_eligible(
    connection: sqlite3.Connection, member_id: str, copy: sqlite3.Row
) -> bool:
    if copy["status"] == "Available":
        return True
    return copy["status"] == "Reserved" and _ready_reservation(
        connection, member_id, copy["title_id"], copy["item_identifier"]
    ) is not None


def lookup_member(identifier: str) -> dict[str, Any] | None:
    from ..auth.service import find_borrow_member

    member = find_borrow_member(identifier)
    return _member_profile(member) if member else None


def check_copy(
    member: User,
    item_identifier: str,
    pending_item_identifiers: list[str] | None = None,
) -> dict[str, Any]:
    member_id = member_id_for_user(member)
    with reservation_store_transaction() as connection:
        _initialize_loan_store(connection)
        if not member_is_eligible(member):
            return {
                "success": False,
                "item_identifier": item_identifier,
                "message": GENERIC_REJECTION,
            }

        existing_count = _outstanding_count(connection, member_id)
        accepted_pending: set[str] = set()
        for pending_identifier in pending_item_identifiers or []:
            if pending_identifier in accepted_pending:
                continue
            pending_copy = _copy_for_identifier(connection, pending_identifier)
            pending_policy = (
                _policy_for_copy(connection, member, pending_copy["book_type"])
                if pending_copy
                else None
            )
            if (
                pending_copy is None
                or pending_policy is None
                or existing_count >= pending_policy["maximum_items"]
                or not _copy_is_eligible(connection, member_id, pending_copy)
            ):
                continue
            accepted_pending.add(pending_identifier)
            existing_count += 1

        copy = _copy_for_identifier(connection, item_identifier)
        if copy is None:
            return {
                "success": False,
                "item_identifier": item_identifier,
                "message": GENERIC_REJECTION,
            }

        policy = _policy_for_copy(connection, member, copy["book_type"])
        if (
            policy is None
            or existing_count >= policy["maximum_items"]
            or not _copy_is_eligible(connection, member_id, copy)
        ):
            return {
                "success": False,
                "item_identifier": item_identifier,
                "message": GENERIC_REJECTION,
            }

        return {
            "success": True,
            "item_identifier": item_identifier,
            "message": "พร้อมบันทึกการยืม",
        }


def confirm_loan(
    member: User,
    item_identifiers: list[str],
    request_id: str,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    if not request_id.strip() or len(request_id) > 200:
        raise LoanError(422, "invalid_request_id", "กรุณาระบุตัวระบุคำขอ")

    current_time = now or datetime.now(ASIA_BANGKOK)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=ASIA_BANGKOK)
    borrowed_on = current_time.astimezone(ASIA_BANGKOK).date()
    member_id = member_id_for_user(member)
    payload_json = json.dumps(
        item_identifiers, ensure_ascii=False, separators=(",", ":")
    )

    with reservation_store_transaction() as connection:
        _initialize_loan_store(connection)
        previous_request = connection.execute(
            "SELECT member_id, payload_json, result_json FROM loan_requests WHERE request_id = ?",
            (request_id,),
        ).fetchone()
        if previous_request:
            if (
                previous_request["member_id"] != member_id
                or previous_request["payload_json"] != payload_json
            ):
                raise LoanError(
                    409,
                    "request_id_conflict",
                    "ตัวระบุคำขอนี้ถูกใช้แล้ว",
                )
            return json.loads(previous_request["result_json"])

        seen: set[str] = set()
        unique_identifiers = []
        for item_identifier in item_identifiers:
            if item_identifier not in seen:
                unique_identifiers.append(item_identifier)
                seen.add(item_identifier)
        existing_count = _outstanding_count(connection, member_id)
        candidate_policies = []
        for item_identifier in unique_identifiers:
            copy = _copy_for_identifier(connection, item_identifier)
            if copy:
                policy = _policy_for_copy(connection, member, copy["book_type"])
                if policy:
                    candidate_policies.append(policy["maximum_items"])

        member_blocked = not member_is_eligible(member) or (
            bool(candidate_policies)
            and all(existing_count >= maximum for maximum in candidate_policies)
        )
        results: list[dict[str, Any]] = []
        successful: list[dict[str, Any]] = []
        seen.clear()

        for item_identifier in item_identifiers:
            if item_identifier in seen:
                results.append(
                    {
                        "item_identifier": item_identifier,
                        "success": False,
                        "message": "รหัสนี้อยู่ในรายการแล้ว",
                    }
                )
                continue
            seen.add(item_identifier)

            if member_blocked:
                results.append(
                    {
                        "item_identifier": item_identifier,
                        "success": False,
                        "message": GENERIC_REJECTION,
                    }
                )
                continue

            copy = _copy_for_identifier(connection, item_identifier)
            policy = (
                _policy_for_copy(connection, member, copy["book_type"])
                if copy
                else None
            )
            if (
                copy is None
                or policy is None
                or existing_count + len(successful) >= policy["maximum_items"]
                or not _copy_is_eligible(connection, member_id, copy)
            ):
                results.append(
                    {
                        "item_identifier": item_identifier,
                        "success": False,
                        "message": GENERIC_REJECTION,
                    }
                )
                continue

            due_date = (
                borrowed_on + timedelta(days=policy["loan_days"])
            ).isoformat()
            results.append(
                {
                    "item_identifier": item_identifier,
                    "success": True,
                    "message": "บันทึกการยืมสำเร็จ",
                    "due_date": due_date,
                }
            )
            successful.append(
                {
                    "copy": copy,
                    "due_date": due_date,
                    "reservation": (
                        _ready_reservation(
                            connection,
                            member_id,
                            copy["title_id"],
                            copy["item_identifier"],
                        )
                        if copy["status"] == "Reserved"
                        else None
                    ),
                }
            )

        loan_id = str(uuid.uuid4()) if successful else None
        if loan_id:
            connection.execute(
                """
                INSERT INTO loans (loan_id, member_id, request_id, borrowed_on)
                VALUES (?, ?, ?, ?)
                """,
                (loan_id, member_id, request_id, borrowed_on.isoformat()),
            )
            for success in successful:
                copy = success["copy"]
                connection.execute(
                    """
                    INSERT INTO loan_items (
                        loan_item_id, loan_id, member_id, title_id,
                        item_identifier, due_date, status
                    ) VALUES (?, ?, ?, ?, ?, ?, 'Borrowed')
                    """,
                    (
                        str(uuid.uuid4()),
                        loan_id,
                        member_id,
                        copy["title_id"],
                        copy["item_identifier"],
                        success["due_date"],
                    ),
                )
                updated = connection.execute(
                    """
                    UPDATE book_copies SET status = 'Borrowed'
                    WHERE item_identifier = ? AND status = ?
                    """,
                    (copy["item_identifier"], copy["status"]),
                )
                if updated.rowcount != 1:
                    raise LoanError(
                        409,
                        "copy_status_changed",
                        GENERIC_REJECTION,
                    )
                if success["reservation"]:
                    updated_reservation = connection.execute(
                        """
                        UPDATE reservations SET status = 'Completed'
                        WHERE reservation_id = ? AND status = 'Ready'
                        """,
                        (success["reservation"]["reservation_id"],),
                    )
                    if updated_reservation.rowcount != 1:
                        raise LoanError(
                            409,
                            "reservation_status_changed",
                            GENERIC_REJECTION,
                        )

        result = {
            "success": bool(successful),
            "loan_id": loan_id,
            "message": (
                "บันทึกการยืมสำเร็จ"
                if successful
                else GENERIC_REJECTION
            ),
            "items": results,
        }
        connection.execute(
            """
            INSERT INTO loan_requests (request_id, member_id, payload_json, result_json)
            VALUES (?, ?, ?, ?)
            """,
            (
                request_id,
                member_id,
                payload_json,
                json.dumps(result, ensure_ascii=False, separators=(",", ":")),
            ),
        )
        return result
