from fastapi.testclient import TestClient

from app.main import app
from app.book_details import service
from app.book_search.models import CatalogRecord, Category

client = TestClient(app)


def test_AC_ดูรายละเอียดและตำแหน่งหนังสือ_01(monkeypatch):
    record = CatalogRecord(
        book_id="BOOK-DETAIL",
        title="หนังสือรายละเอียด",
        authors=["ผู้แต่งทดสอบ"],
        isbn="9780000000000",
        categories=[Category(code="005.1", label="หมวดทดสอบ")],
        status="Available",
        shelf="ชั้น 2",
        zone="โซน A",
        call_number="005.1 ก123",
    )
    monkeypatch.setattr(service, "BOOKS", [record])

    response = client.get("/api/books/BOOK-DETAIL")

    assert response.status_code == 200
    assert response.json() == {
        "book_id": "BOOK-DETAIL",
        "title": "หนังสือรายละเอียด",
        "authors": ["ผู้แต่งทดสอบ"],
        "isbn": "9780000000000",
        "categories": [{"code": "005.1", "label": "หมวดทดสอบ"}],
        "status": "Available",
        "shelf": "ชั้น 2",
        "zone": "โซน A",
        "call_number": "005.1 ก123",
    }


def test_AC_ดูรายละเอียดและตำแหน่งหนังสือ_02_แสดงเฉพาะข้อมูลที่มี(monkeypatch):
    record = CatalogRecord(book_id="BOOK-PARTIAL", title="ข้อมูลบางส่วน")
    monkeypatch.setattr(service, "BOOKS", [record])

    response = client.get("/api/books/BOOK-PARTIAL")

    assert response.status_code == 200
    assert response.json() == {
        "book_id": "BOOK-PARTIAL",
        "title": "ข้อมูลบางส่วน",
    }


def test_AC_ดูรายละเอียดและตำแหน่งหนังสือ_03_แสดงวันคาดว่าจะคืน(monkeypatch):
    record = CatalogRecord(
        book_id="BOOK-BORROWED",
        status="Borrowed",
        expected_return_date="2026-12-01",
    )
    monkeypatch.setattr(service, "BOOKS", [record])

    response = client.get("/api/books/BOOK-BORROWED")

    assert response.status_code == 200
    assert response.json()["expected_return_date"] == "2026-12-01"


def test_ไม่แสดงวันคาดว่าจะคืนเมื่อไม่ได้ยืมหรือไม่มีวันที่(monkeypatch):
    records = [
        CatalogRecord(
            book_id="BOOK-AVAILABLE",
            status="Available",
            expected_return_date="2026-12-01",
        ),
        CatalogRecord(book_id="BOOK-NO-DATE", status="Borrowed"),
    ]
    monkeypatch.setattr(service, "BOOKS", records)

    for book_id in ("BOOK-AVAILABLE", "BOOK-NO-DATE"):
        response = client.get(f"/api/books/{book_id}")
        assert response.status_code == 200
        assert "expected_return_date" not in response.json()


def test_รายละเอียดหนังสือที่ไม่มีอยู่คืน_not_found(monkeypatch):
    monkeypatch.setattr(service, "BOOKS", [])

    response = client.get("/api/books/UNKNOWN")

    assert response.status_code == 404
