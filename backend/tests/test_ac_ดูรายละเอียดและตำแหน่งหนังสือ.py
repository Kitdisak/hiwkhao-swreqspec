from fastapi.testclient import TestClient

from app.main import app
from app.book_details import service
from app.book_search.models import BookCopy, CatalogRecord, Category

client = TestClient(app)


def test_AC_ดูรายละเอียดและตำแหน่งหนังสือ_01(monkeypatch):
    record = CatalogRecord(
        book_id="BOOK-DETAIL",
        title="หนังสือรายละเอียด",
        authors=["ผู้แต่งทดสอบ"],
        isbn="9780000000000",
        categories=[Category(code="005.1", label="หมวดทดสอบ")],
        shelf="2",
        zone="A",
        call_number="005.1 ก123",
        copies=[
            BookCopy(
                book_id="BOOK-DETAIL",
                item_identifier="COPY-001",
                status="Available",
            ),
            BookCopy(
                book_id="BOOK-DETAIL",
                item_identifier="COPY-002",
                status="Borrowed",
                expected_return_date="2026-12-01",
            ),
            BookCopy(
                book_id="BOOK-DETAIL",
                item_identifier="COPY-003",
                status="Reserved",
            ),
            BookCopy(
                book_id="BOOK-DETAIL",
                item_identifier="COPY-004",
                status="Lost",
            ),
            BookCopy(
                book_id="BOOK-DETAIL",
                item_identifier="COPY-005",
                status="Damaged",
            ),
            BookCopy(
                book_id="BOOK-DETAIL",
                item_identifier="COPY-006",
                status="อยู่ระหว่างซ่อม",
            ),
        ],
    )
    monkeypatch.setattr(service, "BOOKS", [record])

    response = client.get("/api/books/BOOK-DETAIL")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "book_id": "BOOK-DETAIL",
        "title": "หนังสือรายละเอียด",
        "authors": ["ผู้แต่งทดสอบ"],
        "isbn": "9780000000000",
        "categories": [{"code": "005.1", "label": "หมวดทดสอบ"}],
        "shelf": "2",
        "zone": "A",
        "call_number": "005.1 ก123",
        "copies": [
            {"item_identifier": "COPY-001", "status": "Available"},
            {
                "item_identifier": "COPY-002",
                "status": "Borrowed",
                "expected_return_date": "2026-12-01",
            },
            {"item_identifier": "COPY-003", "status": "Reserved"},
            {"item_identifier": "COPY-004", "status": "Lost"},
            {"item_identifier": "COPY-005", "status": "Damaged"},
            {"item_identifier": "COPY-006", "status": "อยู่ระหว่างซ่อม"},
        ],
    }

    record.copies[0] = BookCopy(
        book_id="BOOK-DETAIL",
        item_identifier="COPY-001",
        status="Lost",
    )
    refreshed_response = client.get("/api/books/BOOK-DETAIL")

    assert refreshed_response.status_code == 200
    assert refreshed_response.json()["copies"][0]["status"] == "Lost"


def test_AC_ดูรายละเอียดและตำแหน่งหนังสือ_02_แสดงเฉพาะข้อมูลที่มี(monkeypatch):
    record = CatalogRecord(
        book_id="BOOK-PARTIAL",
        title="ข้อมูลบางส่วน",
        authors=["", "ผู้แต่งที่มีข้อมูล"],
        categories=[
            Category(code="", label="หมวดที่มีข้อมูล"),
            Category(code="", label=""),
        ],
        shelf="2",
        call_number="005.13 ส123ก",
        copies=[
            BookCopy(book_id="BOOK-PARTIAL", item_identifier="COPY-NO-STATUS"),
        ],
    )
    book_without_copies = CatalogRecord(book_id="BOOK-NO-COPIES", title="ไม่มีตัวเล่ม")
    monkeypatch.setattr(service, "BOOKS", [record, book_without_copies])

    response = client.get("/api/books/BOOK-PARTIAL")

    assert response.status_code == 200
    assert response.json() == {
        "book_id": "BOOK-PARTIAL",
        "title": "ข้อมูลบางส่วน",
        "authors": ["ผู้แต่งที่มีข้อมูล"],
        "categories": [{"code": "", "label": "หมวดที่มีข้อมูล"}],
        "shelf": "2",
        "call_number": "005.13 ส123ก",
        "copies": [{"item_identifier": "COPY-NO-STATUS"}],
    }

    no_copies_response = client.get("/api/books/BOOK-NO-COPIES")
    assert no_copies_response.status_code == 200
    assert "copies" not in no_copies_response.json()


def test_AC_ดูรายละเอียดและตำแหน่งหนังสือ_03_วันคืนแสดงเฉพาะ_Copy_Borrowed(monkeypatch):
    record = CatalogRecord(
        book_id="BOOK-COPY-RETURNS",
        copies=[
            BookCopy(
                book_id="BOOK-COPY-RETURNS",
                item_identifier="COPY-BORROWED-DATE",
                status="Borrowed",
                expected_return_date="2026-12-01",
            ),
            BookCopy(
                book_id="BOOK-COPY-RETURNS",
                item_identifier="COPY-BORROWED-NO-DATE",
                status="Borrowed",
            ),
            BookCopy(
                book_id="BOOK-COPY-RETURNS",
                item_identifier="COPY-AVAILABLE-DATE",
                status="Available",
                expected_return_date="2026-12-02",
            ),
        ],
    )
    monkeypatch.setattr(service, "BOOKS", [record])

    response = client.get("/api/books/BOOK-COPY-RETURNS")

    assert response.status_code == 200
    assert response.json()["copies"] == [
        {
            "item_identifier": "COPY-BORROWED-DATE",
            "status": "Borrowed",
            "expected_return_date": "2026-12-01",
        },
        {
            "item_identifier": "COPY-BORROWED-NO-DATE",
            "status": "Borrowed",
        },
        {
            "item_identifier": "COPY-AVAILABLE-DATE",
            "status": "Available",
        },
    ]


def test_รายละเอียดหนังสือที่ไม่มีอยู่คืน_not_found(monkeypatch):
    monkeypatch.setattr(service, "BOOKS", [])

    response = client.get("/api/books/UNKNOWN")

    assert response.status_code == 404
