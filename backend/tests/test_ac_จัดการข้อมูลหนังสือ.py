from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.auth.session import SESSION_COOKIE, create_session
from app.book_search import isbn_lookup
from app.book_search import models as catalog
from app.loans.service import _initialize_loan_store
from app.main import app
from app.reservations.service import reservation_store_transaction


@pytest.fixture
def manage_books_client(monkeypatch, tmp_path):
    monkeypatch.setenv(
        "LIBRARY_RESERVATION_DB", str(tmp_path / "reservation-store.sqlite3")
    )
    monkeypatch.setattr(catalog, "CATALOG_RECORDS", [])
    client = TestClient(app)
    client.cookies.set(SESSION_COOKIE, create_session("admin"))
    return client


def _book_payload(
    *,
    title: str = "หนังสือทดสอบการจัดการ",
    isbn: str = "9780306406157",
    copies: list[str] | None = None,
) -> dict:
    copy_ids = copies if copies is not None else ["COPY-MANAGE-01"]
    return {
        "title": title,
        "authors": ["ผู้แต่งทดสอบ"],
        "isbn": isbn,
        "publisher": "สำนักพิมพ์ทดสอบ",
        "publication_year": 2025,
        "categories": [
            {"code": "001", "label": "หมวดหนึ่ง"},
            {"code": "002", "label": "หมวดสอง"},
        ],
        "call_number": "001.1 TEST",
        "shelf": "ชั้น A",
        "zone": "โซน 1",
        "copy_count": len(copy_ids),
        "copies": copy_ids,
    }


def test_AC_จัดการข้อมูลหนังสือ_01_saves_and_reads_back_shared_catalog(
    manage_books_client,
):
    client = manage_books_client
    payload = _book_payload(copies=[" COPY-MANAGE-01 ", "COPY-MANAGE-02"])

    response = client.post("/api/manage/books", json=payload)

    assert response.status_code == 200
    saved = response.json()
    assert saved["message"] == "บันทึกข้อมูลหนังสือแล้ว"
    assert saved["book"]["copy_count"] == 2
    assert [copy["item_identifier"] for copy in saved["book"]["copies"]] == [
        "COPY-MANAGE-01",
        "COPY-MANAGE-02",
    ]
    assert {copy["status"] for copy in saved["book"]["copies"]} == {"Available"}
    assert len(saved["book"]["categories"]) == 2

    search = client.get("/api/books/search", params={"query": "หนังสือทดสอบการจัดการ"})
    assert search.status_code == 200
    assert search.json()["results"][0]["book_id"] == saved["book"]["book_id"]
    details = client.get(f"/api/books/{saved['book']['book_id']}")
    assert details.status_code == 200
    assert details.json()["copies"][0]["status"] == "Available"
    assert details.json()["call_number"] == "001.1 TEST"

    update_payload = {
        **_book_payload(title="แก้ไขข้อมูลหนังสือ"),
        "copy_count": 3,
        "copies": ["COPY-MANAGE-03"],
    }
    update = client.put(
        f"/api/manage/books/{saved['book']['book_id']}", json=update_payload
    )
    assert update.status_code == 200
    assert update.json()["book"]["title"] == "แก้ไขข้อมูลหนังสือ"
    assert update.json()["book"]["copy_count"] == 3
    assert [copy["status"] for copy in update.json()["book"]["copies"]] == [
        "Available",
        "Available",
        "Available",
    ]


def test_AC_จัดการข้อมูลหนังสือ_02_rejects_invalid_data_and_rolls_back(
    manage_books_client,
):
    client = manage_books_client
    first = client.post("/api/manage/books", json=_book_payload())
    assert first.status_code == 200

    valid_isbn_10 = _book_payload(
        title="ISBN 10 หลัก",
        isbn="0306406152",
        copies=["COPY-ISBN-10"],
    )
    assert client.post("/api/manage/books", json=valid_isbn_10).status_code == 200

    missing_required = _book_payload(
        title="", isbn="", copies=["COPY-MISSING-REQUIRED"]
    )
    missing_required["authors"] = []
    missing_required["call_number"] = ""
    missing_response = client.post("/api/manage/books", json=missing_required)
    assert missing_response.status_code == 422
    assert {"title", "authors", "isbn", "call_number"} <= set(
        missing_response.json()["field_errors"]
    )

    duplicate_isbn = _book_payload(
        title="ISBN ซ้ำ", copies=["COPY-DUPLICATE-ISBN"]
    )
    duplicate_isbn_response = client.post("/api/manage/books", json=duplicate_isbn)
    assert duplicate_isbn_response.status_code == 422
    assert "isbn" in duplicate_isbn_response.json()["field_errors"]

    invalid_isbn = _book_payload(
        title="ISBN ผิด",
        isbn="9780306406158",
        copies=["COPY-INVALID-ISBN"],
    )
    isbn_response = client.post("/api/manage/books", json=invalid_isbn)
    assert isbn_response.status_code == 422
    assert "isbn" in isbn_response.json()["field_errors"]

    duplicate_copy = _book_payload(
        title="ระเบียนต้อง rollback",
        isbn="9783161484100",
        copies=["COPY-MANAGE-01", "COPY-ROLLBACK-02"],
    )
    duplicate_copy_response = client.post("/api/manage/books", json=duplicate_copy)
    assert duplicate_copy_response.status_code == 409
    assert duplicate_copy_response.json()["message"] == "รหัสประจำเล่มนี้มีอยู่แล้ว"
    assert client.get(
        "/api/books/search", params={"query": "ระเบียนต้อง rollback"}
    ).json()["results"] == []

    existing = first.json()["book"]
    lower_count = {
        **_book_payload(title=existing["title"], isbn=existing["isbn"]),
        "copy_count": 0,
        "copies": [],
    }
    update_response = client.put(
        f"/api/manage/books/{existing['book_id']}", json=lower_count
    )
    assert update_response.status_code == 409
    assert update_response.json()["message"] == (
        "ไม่สามารถลดจำนวน Copy ได้ ให้เปลี่ยนสถานะเล่มที่เลิกใช้แทน"
    )
    read_back = client.get(f"/api/manage/books/{existing['book_id']}").json()
    assert read_back["copy_count"] == 1


def test_AC_จัดการข้อมูลหนังสือ_03_enforces_status_transitions_and_permission(
    manage_books_client,
):
    client = manage_books_client
    created = client.post(
        "/api/manage/books",
        json=_book_payload(copies=["COPY-MANAGE-01", "COPY-MANAGE-02"]),
    ).json()["book"]
    item_identifier = created["copies"][0]["item_identifier"]

    changed = client.patch(
        f"/api/manage/copies/{item_identifier}/status",
        json={"status": "Damaged"},
    )
    assert changed.status_code == 200
    blocked_manual_borrow = client.patch(
        f"/api/manage/copies/{item_identifier}/status",
        json={"status": "Borrowed"},
    )
    assert blocked_manual_borrow.status_code == 422
    repaired = client.patch(
        f"/api/manage/copies/{item_identifier}/status",
        json={"status": "อยู่ระหว่างซ่อม"},
    )
    assert repaired.status_code == 200
    available = client.patch(
        f"/api/manage/copies/{item_identifier}/status",
        json={"status": "Available"},
    )
    assert available.status_code == 200

    with reservation_store_transaction() as connection:
        _initialize_loan_store(connection)
        connection.execute(
            """
            INSERT INTO loans (loan_id, member_id, request_id, borrowed_on)
            VALUES ('LOAN-STATUS-TEST', 'MEMBER-TEST', 'REQUEST-STATUS-TEST', '2026-01-01')
            """
        )
        connection.execute(
            """
            INSERT INTO loan_items (
                loan_item_id, loan_id, member_id, title_id, item_identifier,
                due_date, status
            ) VALUES (
                'LOAN-ITEM-STATUS-TEST', 'LOAN-STATUS-TEST', 'MEMBER-TEST',
                ?, ?, '2026-01-08', 'Borrowed'
            )
            """,
            (created["book_id"], item_identifier),
        )
        connection.execute(
            "UPDATE book_copies SET status = 'Borrowed' WHERE item_identifier = ?",
            (item_identifier,),
        )
        reserved_identifier = created["copies"][1]["item_identifier"]
        connection.execute(
            """
            INSERT INTO reservations (
                reservation_id, request_id, member_id, title_id, recorded_at,
                status, pickup_deadline, reserved_item_identifier,
                queue_position_at_success, first_name, last_name, member_code
            ) VALUES (
                'RESERVATION-STATUS-TEST', 'REQUEST-RESERVATION-STATUS-TEST',
                'MEMBER-TEST', ?, '2026-01-01T00:00:00+00:00', 'Ready',
                '2026-01-04', ?, 1, 'Test', 'Member', 'MEMBER-TEST'
            )
            """,
            (created["book_id"], reserved_identifier),
        )
        connection.execute(
            "UPDATE book_copies SET status = 'Reserved' WHERE item_identifier = ?",
            (reserved_identifier,),
        )

    pending = client.patch(
        f"/api/manage/copies/{item_identifier}/status",
        json={"status": "Lost"},
    )
    assert pending.status_code == 409
    assert pending.json()["message"] == (
        "ไม่สามารถเปลี่ยนสถานะได้ เนื่องจากมีรายการยืมหรือจองค้างอยู่"
    )
    ready_reservation = client.patch(
        "/api/manage/copies/COPY-MANAGE-02/status",
        json={"status": "Available"},
    )
    assert ready_reservation.status_code == 409
    assert ready_reservation.json()["message"] == (
        "ไม่สามารถเปลี่ยนสถานะได้ เนื่องจากมีรายการยืมหรือจองค้างอยู่"
    )

    unauthorized = TestClient(app)
    unauthorized.cookies.set(SESSION_COOKIE, create_session("s12345"))
    no_permission = unauthorized.get("/api/manage/books")
    assert no_permission.status_code == 403


def test_AC_จัดการข้อมูลหนังสือ_01_isbn_lookup_uses_mock(monkeypatch, manage_books_client):
    class MockResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def read(self):
            return json.dumps(
                {
                    "ISBN:9780306406157": {
                        "title": "ข้อมูลจำลอง",
                        "authors": [{"name": "ผู้แต่งจำลอง"}],
                    }
                }
            ).encode()

    def mocked_urlopen(url, timeout):
        assert "openlibrary.org/api/books" in url
        assert timeout == 5
        return MockResponse()

    monkeypatch.setattr(isbn_lookup, "urlopen", mocked_urlopen)
    response = manage_books_client.get(
        "/api/manage/isbn-metadata", params={"isbn": "9780306406157"}
    )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "title": "ข้อมูลจำลอง",
        "authors": ["ผู้แต่งจำลอง"],
    }

    def timeout(*_args, **_kwargs):
        raise TimeoutError

    monkeypatch.setattr(isbn_lookup, "urlopen", timeout)
    timed_out = manage_books_client.get(
        "/api/manage/isbn-metadata", params={"isbn": "9780306406157"}
    )
    assert timed_out.status_code == 502
    assert "กรุณากรอกข้อมูลเอง" in timed_out.json()["message"]
