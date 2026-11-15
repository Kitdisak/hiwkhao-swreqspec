import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.book_search import service
from app.book_search.models import (
    BookCopy,
    CatalogRecord,
    Category,
    validate_unique_item_identifiers,
)

client = TestClient(app)


def test_FR_ค้นหาหนังสือ_01_groups_all_copy_identifiers(monkeypatch):
    record = CatalogRecord(
        book_id="BOOK-TEST",
        title="หนังสือทดสอบ",
        authors=["ผู้แต่งทดสอบ"],
        isbn="9780000000000",
        keywords=["คำสำคัญทดสอบ"],
        categories=[Category(code="005.1", label="หมวดทดสอบ")],
        copies=[
            BookCopy(book_id="BOOK-TEST", item_identifier="COPY-001"),
            BookCopy(book_id="BOOK-TEST", item_identifier="COPY-002"),
        ],
    )
    monkeypatch.setattr(service, "BOOKS", [record])

    for query in (
        "หนังสือ",
        "ผู้แต่งทดสอบ",
        "9780000000000",
        "คำสำคัญ",
    ):
        results = service.search_books(query)
        assert len(results) == 1
        assert results[0]["book_id"] == "BOOK-TEST"
        assert results[0]["item_identifiers"] == ["COPY-001", "COPY-002"]


def test_FR_ค้นหาหนังสือ_03_requires_every_selected_filter_value(monkeypatch):
    matching = CatalogRecord(
        book_id="BOOK-MATCH",
        title="หนังสือที่ตรงทุกเงื่อนไข",
        authors=["ผู้แต่งหนึ่ง", "ผู้แต่งสอง"],
        categories=[
            Category(code="005.1", label="หมวดหนึ่ง"),
            Category(code="006.2", label="หมวดสอง"),
        ],
        copies=[BookCopy(book_id="BOOK-MATCH", item_identifier="COPY-MATCH")],
    )
    missing_author = CatalogRecord(
        book_id="BOOK-MISSING-AUTHOR",
        title="หนังสือที่ขาดผู้แต่ง",
        authors=["ผู้แต่งหนึ่ง"],
        categories=matching.categories,
        copies=[
            BookCopy(
                book_id="BOOK-MISSING-AUTHOR",
                item_identifier="COPY-MISSING-AUTHOR",
            )
        ],
    )
    missing_category = CatalogRecord(
        book_id="BOOK-MISSING-CATEGORY",
        title="หนังสือที่ขาดหมวดหมู่",
        authors=matching.authors,
        categories=[matching.categories[0]],
        copies=[
            BookCopy(
                book_id="BOOK-MISSING-CATEGORY",
                item_identifier="COPY-MISSING-CATEGORY",
            )
        ],
    )
    monkeypatch.setattr(
        service,
        "BOOKS",
        [matching, missing_author, missing_category],
    )

    results = service.search_books(
        categories=["005", "006"],
        authors=["ผู้แต่งหนึ่ง", "ผู้แต่งสอง"],
    )

    assert [record["book_id"] for record in results] == ["BOOK-MATCH"]


def test_FR_ค้นหาหนังสือ_03_accepts_repeated_filter_parameters(monkeypatch):
    record = CatalogRecord(
        book_id="BOOK-API",
        title="หนังสือทดสอบ API",
        authors=["ผู้แต่งหนึ่ง", "ผู้แต่งสอง"],
        categories=[
            Category(code="005.1", label="หมวดหนึ่ง"),
            Category(code="006.2", label="หมวดสอง"),
        ],
        copies=[BookCopy(book_id="BOOK-API", item_identifier="COPY-API")],
    )
    monkeypatch.setattr(service, "BOOKS", [record])

    response = client.get(
        "/api/books/search",
        params=[
            ("category", "005"),
            ("category", "006"),
            ("author", "ผู้แต่งหนึ่ง"),
            ("author", "ผู้แต่งสอง"),
        ],
    )

    assert response.status_code == 200
    assert [item["book_id"] for item in response.json()["results"]] == ["BOOK-API"]


def test_DOM_OPAC_05_rejects_duplicate_item_identifiers():
    duplicate_records = [
        CatalogRecord(
            book_id="BOOK-001",
            title="เล่มหนึ่ง",
            copies=[BookCopy(book_id="BOOK-001", item_identifier="DUPLICATE")],
        ),
        CatalogRecord(
            book_id="BOOK-002",
            title="เล่มสอง",
            copies=[BookCopy(book_id="BOOK-002", item_identifier="DUPLICATE")],
        ),
    ]

    with pytest.raises(ValueError, match="ไม่ซ้ำกัน"):
        validate_unique_item_identifiers(duplicate_records)
