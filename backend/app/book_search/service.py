from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from .models import BOOKS, CatalogRecord
from .store import get_catalog_records

_INITIAL_BOOKS = BOOKS


def _normalize(value: str | None) -> str:
    return (value or "").strip().casefold()


def _matches_query(record: CatalogRecord, query: str) -> bool:
    """จับคู่คำค้นบางส่วนกับฟิลด์ค้นหาที่กำหนด (FR-ค้นหาหนังสือ-01, ASM-01)."""

    needle = _normalize(query)
    if not needle:
        return True

    searchable_values = [
        record.title,
        *record.authors,
        record.isbn,
        *record.keywords,
    ]
    return any(needle in _normalize(value) for value in searchable_values)


def _matches_all_values(selected: Sequence[str], available: Sequence[str]) -> bool:
    """ต้องตรงกับค่าทุกค่าที่เลือกในตัวกรอง (FR-ค้นหาหนังสือ-03, ASM-03)."""

    normalized_values = [_normalize(value) for value in selected if _normalize(value)]
    normalized_available = [_normalize(value) for value in available]
    return all(
        any(value in candidate for candidate in normalized_available)
        for value in normalized_values
    )


def search_books(
    query: str | None = None,
    *,
    categories: Sequence[str] | None = None,
    authors: Sequence[str] | None = None,
    category: str | None = None,
    author: str | None = None,
) -> list[dict[str, Any]]:
    """ค้นหาและกรองระเบียนหนังสือ (FR-ค้นหาหนังสือ-01, FR-ค้นหาหนังสือ-03)."""

    selected_categories = [*(categories or []), *([category] if category else [])]
    selected_authors = [*(authors or []), *([author] if author else [])]

    records = get_catalog_records() if BOOKS is _INITIAL_BOOKS else BOOKS
    results = []
    for record in records:
        if not _matches_query(record, query or ""):
            continue

        category_values = [
            value
            for category_item in record.categories
            for value in (category_item.code, category_item.label)
        ]
        if not _matches_all_values(selected_categories, category_values):
            continue
        if not _matches_all_values(selected_authors, record.authors):
            continue

        results.append(record.to_dict())

    return results
