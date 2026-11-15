from fastapi.testclient import TestClient

from app.main import app
from app.book_search import service
from app.book_search.models import BookCopy, CatalogRecord, Category

client = TestClient(app)


def test_AC_ค้นหาหนังสือ_01(monkeypatch):
    record = CatalogRecord(
        book_id="BOOK-TEST",
        title="หนังสือทดสอบบางส่วน",
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
        "ทดสอบบาง",
        "แต่งทด",
        "0000000000",
        "สำคัญทด",
    ):
        response = client.get("/api/books/search", params={"query": query})
        assert response.status_code == 200
        payload = response.json()
        assert payload["message"] is None
        assert len(payload["results"]) == 1
        assert payload["results"][0] == {
            "book_id": "BOOK-TEST",
            "title": "หนังสือทดสอบบางส่วน",
            "authors": ["ผู้แต่งทดสอบ"],
            "isbn": "9780000000000",
            "keywords": ["คำสำคัญทดสอบ"],
            "categories": [{"code": "005.1", "label": "หมวดทดสอบ"}],
            "item_identifiers": ["COPY-001", "COPY-002"],
        }
