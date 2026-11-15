from fastapi.testclient import TestClient

from app.main import app
from app.book_search import service
from app.book_search.models import BookCopy, CatalogRecord, Category

client = TestClient(app)


def test_AC_ค้นหาหนังสือ_03_requires_all_selected_values(monkeypatch):
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
    payload = response.json()
    assert payload["message"] is None
    assert [record["book_id"] for record in payload["results"]] == ["BOOK-MATCH"]
