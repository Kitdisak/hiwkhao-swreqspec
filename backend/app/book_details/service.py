from __future__ import annotations

from typing import Any

from ..book_search.models import CATALOG_RECORDS

BOOKS = CATALOG_RECORDS


def get_book_details(book_id: str) -> dict[str, Any] | None:
    """อ่านรายละเอียดล่าสุดที่มีใน catalog (FR-ดูรายละเอียดและตำแหน่งหนังสือ-01 ถึง FR-ดูรายละเอียดและตำแหน่งหนังสือ-05)."""
    record = next((book for book in BOOKS if book.book_id == book_id), None)
    return record.to_detail_dict() if record else None
