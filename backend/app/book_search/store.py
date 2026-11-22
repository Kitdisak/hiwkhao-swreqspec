from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator

from . import models
from .models import BookCopy, CatalogRecord, Category

COPY_STATUSES = (
    "Available",
    "Borrowed",
    "Reserved",
    "Lost",
    "Damaged",
    "อยู่ระหว่างซ่อม",
)
BLOCKED_STATUSES = ("Lost", "Damaged", "อยู่ระหว่างซ่อม")


@dataclass
class CatalogError(Exception):
    status_code: int
    code: str
    message: str
    field_errors: dict[str, str] | None = None


def initialize_catalog_store(
    connection: sqlite3.Connection,
    seed_records: list[CatalogRecord] | None = None,
) -> None:
    statements = (
        """
        CREATE TABLE IF NOT EXISTS catalog_records (
            book_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            authors_json TEXT NOT NULL,
            isbn TEXT NOT NULL,
            publisher TEXT,
            publication_year INTEGER,
            keywords_json TEXT NOT NULL,
            call_number TEXT NOT NULL,
            shelf TEXT NOT NULL,
            zone TEXT NOT NULL
        )
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS unique_catalog_isbn
            ON catalog_records(isbn) WHERE isbn <> ''
        """,
        """
        CREATE TABLE IF NOT EXISTS catalog_categories (
            book_id TEXT NOT NULL REFERENCES catalog_records(book_id) ON DELETE CASCADE,
            category_index INTEGER NOT NULL,
            code TEXT NOT NULL,
            label TEXT NOT NULL,
            PRIMARY KEY (book_id, category_index)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS book_copies (
            item_identifier TEXT PRIMARY KEY,
            book_id TEXT NOT NULL REFERENCES catalog_records(book_id),
            status TEXT DEFAULT 'Available'
                CHECK (status IN ('Available', 'Borrowed', 'Reserved', 'Lost', 'Damaged', 'อยู่ระหว่างซ่อม')),
            expected_return_date TEXT,
            book_type TEXT
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS book_copies_by_book
            ON book_copies(book_id)
        """,
        """
        CREATE TABLE IF NOT EXISTS catalog_store_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """,
    )
    for statement in statements:
        connection.execute(statement)

    connection.execute(
        """
        UPDATE book_copies
        SET status = 'Borrowed'
        WHERE status IS NULL
        """
    )

    seeded = connection.execute(
        "SELECT value FROM catalog_store_meta WHERE key = 'legacy_catalog_seeded'"
    ).fetchone()
    if seeded is None:
        records = seed_records if seed_records is not None else models.CATALOG_RECORDS
        for record in records:
            _insert_record(connection, record)

        legacy_table = connection.execute(
            """
            SELECT 1 FROM sqlite_master
            WHERE type = 'table' AND name = 'loan_copy_status'
            """
        ).fetchone()
        if legacy_table:
            legacy_copies = connection.execute(
                """
                SELECT item_identifier, title_id, book_type, status
                FROM loan_copy_status
                """
            ).fetchall()
            for copy in legacy_copies:
                exists = connection.execute(
                    "SELECT 1 FROM catalog_records WHERE book_id = ?",
                    (copy["title_id"],),
                ).fetchone()
                if exists:
                    connection.execute(
                        """
                        INSERT INTO book_copies (
                            item_identifier, book_id, status, book_type
                        ) VALUES (?, ?, ?, ?)
                        ON CONFLICT(item_identifier) DO UPDATE SET
                            status = excluded.status,
                            book_type = excluded.book_type
                        """,
                        (
                            copy["item_identifier"],
                            copy["title_id"],
                            copy["status"],
                            copy["book_type"],
                        ),
                    )
            connection.execute("DROP TABLE loan_copy_status")

        connection.execute(
            """
            INSERT INTO catalog_store_meta (key, value)
            VALUES ('legacy_catalog_seeded', 'true')
            """
        )

    connection.execute(
        """
        CREATE VIEW IF NOT EXISTS loan_copy_status AS
            SELECT item_identifier, book_id AS title_id,
                COALESCE(book_type, 'หนังสือทั่วไป') AS book_type, status
            FROM book_copies
        """
    )
    connection.execute(
        """
        CREATE TRIGGER IF NOT EXISTS update_legacy_copy_status
        INSTEAD OF UPDATE OF status ON loan_copy_status
        BEGIN
            UPDATE book_copies SET status = NEW.status
            WHERE item_identifier = OLD.item_identifier;
        END
        """
    )


def _insert_record(connection: sqlite3.Connection, record: CatalogRecord) -> None:
    connection.execute(
        """
        INSERT OR IGNORE INTO catalog_records (
            book_id, title, authors_json, isbn, publisher, publication_year,
            keywords_json, call_number, shelf, zone
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            record.book_id,
            record.title,
            json.dumps(record.authors, ensure_ascii=False),
            record.isbn,
            record.publisher,
            record.publication_year,
            json.dumps(record.keywords, ensure_ascii=False),
            record.call_number or "",
            record.shelf or "",
            record.zone or "",
        ),
    )
    for index, category in enumerate(record.categories):
        connection.execute(
            """
            INSERT OR IGNORE INTO catalog_categories (
                book_id, category_index, code, label
            ) VALUES (?, ?, ?, ?)
            """,
            (record.book_id, index, category.code, category.label),
        )
    for copy in record.copies:
        connection.execute(
            """
            INSERT OR IGNORE INTO book_copies (
                item_identifier, book_id, status, expected_return_date, book_type
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                copy.item_identifier.strip(),
                record.book_id,
                copy.status,
                copy.expected_return_date,
                copy.book_type,
            ),
        )


def _record_from_row(
    connection: sqlite3.Connection, row: sqlite3.Row
) -> CatalogRecord:
    categories = connection.execute(
        """
        SELECT code, label FROM catalog_categories
        WHERE book_id = ? ORDER BY category_index
        """,
        (row["book_id"],),
    ).fetchall()
    copies = connection.execute(
        """
        SELECT item_identifier, status, expected_return_date, book_type
        FROM book_copies WHERE book_id = ? ORDER BY item_identifier
        """,
        (row["book_id"],),
    ).fetchall()
    return CatalogRecord(
        book_id=row["book_id"],
        title=row["title"],
        authors=json.loads(row["authors_json"]),
        isbn=row["isbn"],
        keywords=json.loads(row["keywords_json"]),
        categories=[Category(code=item["code"], label=item["label"]) for item in categories],
        copies=[
            BookCopy(
                book_id=row["book_id"],
                item_identifier=item["item_identifier"],
                status=item["status"],
                expected_return_date=item["expected_return_date"],
                book_type=item["book_type"],
            )
            for item in copies
        ],
        shelf=row["shelf"],
        zone=row["zone"],
        call_number=row["call_number"],
        publisher=row["publisher"],
        publication_year=row["publication_year"],
    )


def get_catalog_records(connection: sqlite3.Connection | None = None) -> list[CatalogRecord]:
    owns_connection = connection is None
    if connection is None:
        from ..reservations.service import _connect

        connection = _connect()
    try:
        rows = connection.execute(
            "SELECT * FROM catalog_records ORDER BY title, book_id"
        ).fetchall()
        return [_record_from_row(connection, row) for row in rows]
    finally:
        if owns_connection:
            connection.close()


def get_catalog_record(
    book_id: str, connection: sqlite3.Connection | None = None
) -> CatalogRecord | None:
    owns_connection = connection is None
    if connection is None:
        from ..reservations.service import _connect

        connection = _connect()
    try:
        row = connection.execute(
            "SELECT * FROM catalog_records WHERE book_id = ?", (book_id,)
        ).fetchone()
        return _record_from_row(connection, row) if row else None
    finally:
        if owns_connection:
            connection.close()


def management_record(record: CatalogRecord) -> dict[str, Any]:
    return {
        "book_id": record.book_id,
        "title": record.title,
        "authors": record.authors,
        "isbn": record.isbn,
        "publisher": record.publisher or "",
        "publication_year": record.publication_year,
        "keywords": record.keywords,
        "categories": [category.to_dict() for category in record.categories],
        "call_number": record.call_number or "",
        "shelf": record.shelf or "",
        "zone": record.zone or "",
        "copy_count": len(record.copies),
        "copies": [
            {"item_identifier": copy.item_identifier, "status": copy.status}
            for copy in record.copies
        ],
    }


def _valid_isbn(value: str) -> bool:
    if len(value) == 10 and value.isascii() and value.isdigit():
        return sum((10 - index) * int(digit) for index, digit in enumerate(value)) % 11 == 0
    if len(value) == 13 and value.isascii() and value.isdigit():
        checksum = sum(
            int(digit) * (1 if index % 2 == 0 else 3)
            for index, digit in enumerate(value[:12])
        )
        return (10 - checksum % 10) % 10 == int(value[-1])
    return False


def _invalid(message: str, field_errors: dict[str, str]) -> CatalogError:
    return CatalogError(422, "validation_error", message, field_errors)


def _normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    title = str(payload.get("title") or "").strip()
    isbn = str(payload.get("isbn") or "").strip()
    authors = [
        str(author).strip()
        for author in payload.get("authors", [])
        if str(author).strip()
    ]
    call_number = str(payload.get("call_number") or "").strip()
    copies = [
        str(identifier).strip()
        for identifier in payload.get("copies", [])
    ]
    categories = []
    for item in payload.get("categories", []):
        if not isinstance(item, dict):
            continue
        categories.append(
            {
                "code": str(item.get("code") or "").strip(),
                "label": str(item.get("label") or "").strip(),
            }
        )
    return {
        "title": title,
        "isbn": isbn,
        "authors": authors,
        "publisher": str(payload.get("publisher") or "").strip() or None,
        "publication_year": payload.get("publication_year"),
        "keywords": payload.get("keywords") or [],
        "categories": categories,
        "call_number": call_number,
        "shelf": str(payload.get("shelf") or "").strip(),
        "zone": str(payload.get("zone") or "").strip(),
        "copies": copies,
        "copy_count": payload.get("copy_count"),
    }


def _validate_record(
    connection: sqlite3.Connection,
    payload: dict[str, Any],
    *,
    existing_book_id: str | None = None,
) -> tuple[dict[str, Any], int]:
    data = _normalize_payload(payload)
    if "keywords" not in payload and existing_book_id:
        current_keywords = connection.execute(
            "SELECT keywords_json FROM catalog_records WHERE book_id = ?",
            (existing_book_id,),
        ).fetchone()
        if current_keywords:
            data["keywords"] = json.loads(current_keywords["keywords_json"])
    errors: dict[str, str] = {}
    if not data["title"]:
        errors["title"] = "กรุณากรอกชื่อหนังสือ"
    if not data["authors"]:
        errors["authors"] = "กรุณากรอกผู้แต่งอย่างน้อย 1 คน"
    if not data["isbn"]:
        errors["isbn"] = "กรุณากรอก ISBN"
    elif not _valid_isbn(data["isbn"]):
        errors["isbn"] = "ISBN ต้องเป็น 10 หรือ 13 หลักและมีเลขตรวจสอบถูกต้อง"
    if not data["call_number"]:
        errors["call_number"] = "กรุณากรอกเลขเรียกหนังสือ"
    for index, category in enumerate(data["categories"]):
        if not category["code"] or not category["label"]:
            errors[f"categories.{index}"] = "กรุณากรอกรหัสและชื่อหมวดหมู่"
    for index, identifier in enumerate(data["copies"]):
        if not identifier:
            errors[f"copies.{index}"] = "กรุณากรอกรหัสประจำเล่ม"

    if errors:
        raise _invalid("กรุณาตรวจสอบข้อมูลที่จำเป็น", errors)

    isbn_owner = connection.execute(
        "SELECT book_id FROM catalog_records WHERE isbn = ?", (data["isbn"],)
    ).fetchone()
    if isbn_owner and isbn_owner["book_id"] != existing_book_id:
        raise _invalid("ISBN นี้มีอยู่แล้ว", {"isbn": "ISBN นี้มีอยู่แล้ว"})

    record = (
        connection.execute(
            "SELECT COUNT(*) AS copy_count FROM book_copies WHERE book_id = ?",
            (existing_book_id,),
        ).fetchone()["copy_count"]
        if existing_book_id
        else 0
    )
    copy_count = data["copy_count"]
    if (
        not isinstance(copy_count, int)
        or isinstance(copy_count, bool)
        or copy_count < 0
    ):
        raise _invalid(
            "จำนวน Copy ต้องเป็นจำนวนเต็มไม่ติดลบ",
            {"copy_count": "กรุณาระบุจำนวน Copy"},
        )
    if existing_book_id:
        if copy_count < record:
            raise CatalogError(
                409,
                "copy_count_reduction",
                "ไม่สามารถลดจำนวน Copy ได้ ให้เปลี่ยนสถานะเล่มที่เลิกใช้แทน",
                {"copy_count": "ไม่สามารถลดจำนวน Copy ได้ ให้เปลี่ยนสถานะเล่มที่เลิกใช้แทน"},
            )
        expected_new_copies = copy_count - record
    else:
        if copy_count < 1:
            raise _invalid(
                "จำนวน Copy ต้องไม่น้อยกว่า 1",
                {"copy_count": "กรุณาระบุจำนวน Copy"},
            )
        expected_new_copies = copy_count
    if len(data["copies"]) != expected_new_copies:
        raise _invalid(
            "จำนวนรหัส Copy ใหม่ไม่ตรงกับจำนวนที่ระบุ",
            {"copies": "กรุณาระบุรหัสประจำเล่มให้ครบตามจำนวน Copy ใหม่"},
        )

    seen: set[str] = set()
    for index, identifier in enumerate(data["copies"]):
        if identifier in seen:
            raise CatalogError(
                409,
                "duplicate_copy_identifier",
                "รหัสประจำเล่มนี้มีอยู่แล้ว",
                {f"copies.{index}": "รหัสประจำเล่มนี้มีอยู่แล้ว"},
            )
        seen.add(identifier)
        found = connection.execute(
            "SELECT 1 FROM book_copies WHERE item_identifier = ?", (identifier,)
        ).fetchone()
        if found:
            raise CatalogError(
                409,
                "duplicate_copy_identifier",
                "รหัสประจำเล่มนี้มีอยู่แล้ว",
                {f"copies.{index}": "รหัสประจำเล่มนี้มีอยู่แล้ว"},
            )
    return data, record


def _insert_children(
    connection: sqlite3.Connection, book_id: str, data: dict[str, Any]
) -> None:
    for index, category in enumerate(data["categories"]):
        connection.execute(
            """
            INSERT INTO catalog_categories (book_id, category_index, code, label)
            VALUES (?, ?, ?, ?)
            """,
            (book_id, index, category["code"], category["label"]),
        )
    for identifier in data["copies"]:
        connection.execute(
            """
            INSERT INTO book_copies (item_identifier, book_id, status)
            VALUES (?, ?, 'Available')
            """,
            (identifier, book_id),
        )


@contextmanager
def _write_transaction() -> Iterator[sqlite3.Connection]:
    from ..reservations.service import reservation_store_transaction

    with reservation_store_transaction() as connection:
        yield connection


def create_book(payload: dict[str, Any]) -> dict[str, Any]:
    with _write_transaction() as connection:
        data, _ = _validate_record(connection, payload)
        book_id = str(uuid.uuid4())
        connection.execute(
            """
            INSERT INTO catalog_records (
                book_id, title, authors_json, isbn, publisher, publication_year,
                keywords_json, call_number, shelf, zone
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                book_id,
                data["title"],
                json.dumps(data["authors"], ensure_ascii=False),
                data["isbn"],
                data["publisher"],
                data["publication_year"],
                json.dumps(data["keywords"], ensure_ascii=False),
                data["call_number"],
                data["shelf"],
                data["zone"],
            ),
        )
        _insert_children(connection, book_id, data)
        record = get_catalog_record(book_id, connection)
        if record is None:
            raise RuntimeError("New Catalog record could not be read back")
        return management_record(record)


def update_book(book_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    with _write_transaction() as connection:
        current = connection.execute(
            "SELECT 1 FROM catalog_records WHERE book_id = ?", (book_id,)
        ).fetchone()
        if current is None:
            raise CatalogError(404, "book_not_found", "ไม่พบข้อมูลหนังสือ")
        data, _ = _validate_record(
            connection, payload, existing_book_id=book_id
        )
        connection.execute(
            """
            UPDATE catalog_records
            SET title = ?, authors_json = ?, isbn = ?, publisher = ?, publication_year = ?,
                keywords_json = ?, call_number = ?, shelf = ?, zone = ?
            WHERE book_id = ?
            """,
            (
                data["title"],
                json.dumps(data["authors"], ensure_ascii=False),
                data["isbn"],
                data["publisher"],
                data["publication_year"],
                json.dumps(data["keywords"], ensure_ascii=False),
                data["call_number"],
                data["shelf"],
                data["zone"],
                book_id,
            ),
        )
        connection.execute(
            "DELETE FROM catalog_categories WHERE book_id = ?", (book_id,)
        )
        _insert_children(connection, book_id, data)
        record = get_catalog_record(book_id, connection)
        if record is None:
            raise RuntimeError("Updated Catalog record could not be read back")
        return management_record(record)


def change_copy_status(item_identifier: str, new_status: str) -> dict[str, Any]:
    if new_status not in COPY_STATUSES or new_status in ("Borrowed", "Reserved"):
        raise CatalogError(
            422, "invalid_copy_status", "ไม่สามารถกำหนดสถานะนี้ด้วยมือได้"
        )
    with _write_transaction() as connection:
        copy = connection.execute(
            """
            SELECT item_identifier, book_id, status
            FROM book_copies WHERE item_identifier = ?
            """,
            (item_identifier.strip(),),
        ).fetchone()
        if copy is None:
            raise CatalogError(404, "copy_not_found", "ไม่พบข้อมูล Copy")

        active_loan = connection.execute(
            """
            SELECT 1 FROM loan_items
            WHERE item_identifier = ? AND status = 'Borrowed' LIMIT 1
            """,
            (item_identifier.strip(),),
        ).fetchone() if _table_exists(connection, "loan_items") else None
        ready_reservation = connection.execute(
            """
            SELECT 1 FROM reservations
            WHERE reserved_item_identifier = ? AND status = 'Ready' LIMIT 1
            """,
            (item_identifier.strip(),),
        ).fetchone()
        if copy["status"] in ("Borrowed", "Reserved") or active_loan or ready_reservation:
            raise CatalogError(
                409,
                "copy_has_pending_record",
                "ไม่สามารถเปลี่ยนสถานะได้ เนื่องจากมีรายการยืมหรือจองค้างอยู่",
            )

        current_status = copy["status"]
        allowed = (
            ("Lost", "Damaged", "อยู่ระหว่างซ่อม")
            if current_status == "Available"
            else ("Available", *BLOCKED_STATUSES)
            if current_status in BLOCKED_STATUSES
            else ()
        )
        if new_status not in allowed:
            raise CatalogError(422, "invalid_status_transition", "ไม่สามารถเปลี่ยนสถานะนี้ได้")
        connection.execute(
            "UPDATE book_copies SET status = ? WHERE item_identifier = ?",
            (new_status, item_identifier.strip()),
        )
        return {
            "item_identifier": item_identifier.strip(),
            "status": new_status,
        }


def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
    ).fetchone() is not None
