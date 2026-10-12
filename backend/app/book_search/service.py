from __future__ import annotations

from typing import Any

from .models import BOOKS, Book


def _normalize(value: str | None) -> str:
    return (value or "").strip().lower()


def _matches_query(book: Book, query: str) -> bool:
    if not query:
        return True
    needle = _normalize(query)
    haystacks = [
        book.title,
        *book.authors,
        book.isbn,
        *book.keywords,
    ]
    return any(needle in _normalize(item) for item in haystacks)


def search_books(
    query: str | None = None,
    *,
    category: str | None = None,
    author: str | None = None,
    search_type: str | None = None,
) -> list[dict[str, Any]]:
    normalized_query = _normalize(query)
    filtered: list[Book] = []
    for book in BOOKS:
        if normalized_query:
            if search_type:
                st = search_type.lower()
                if st == "title" and normalized_query not in _normalize(book.title):
                    continue
                if st == "author" and not any(normalized_query in _normalize(person) for person in book.authors):
                    continue
                if st == "isbn" and normalized_query not in _normalize(book.isbn):
                    continue
                if st == "keyword" and not any(normalized_query in _normalize(keyword) for keyword in book.keywords):
                    continue
                if st not in {"title", "author", "isbn", "keyword"} and not _matches_query(book, normalized_query):
                    continue
            elif not _matches_query(book, normalized_query):
                continue

        if category and _normalize(category) not in _normalize(book.ddc_category):
            continue
        if author and not any(_normalize(author) in _normalize(person) for person in book.authors):
            continue
        filtered.append(book)

    return [
        {
            "title": book.title,
            "authors": book.authors,
            "isbn": book.isbn,
            "item_identifier": book.item_identifier,
            "ddc_category": book.ddc_category,
        }
        for book in filtered
    ]
