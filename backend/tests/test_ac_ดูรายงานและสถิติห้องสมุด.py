from __future__ import annotations

import sqlite3
from datetime import date, datetime, time
from time import perf_counter

from fastapi.testclient import TestClient

import app.auth.service as auth_service
import app.main as main_module
from app.auth.models import User
from app.auth.service import ROLE_PERMISSIONS, hash_password
from app.auth.session import SESSION_COOKIE, create_session
from app.main import app
from app.reports.service import (
    ReportRangeError,
    build_report_csv,
    fine_report,
    get_report,
    loan_report,
    popular_books_report,
    room_usage_report,
    validate_report_range,
)
from app.rooms import store as room_store
from app.rooms.models import RoomBooking


def _session_user(role: str, permissions: tuple[str, ...]) -> User:
    return User(
        username=f"{role}-report-test",
        email=f"{role}@example.com",
        student_id=None,
        password_hash=hash_password("pass"),
        user_type="staff" if role in ("admin", "librarian") else "student",
        role=role,
        permissions=permissions,
    )


def test_T01_report_permission_is_added_to_admin_and_librarian():
    assert "view_reports" in ROLE_PERMISSIONS["admin"]
    assert "view_reports" in ROLE_PERMISSIONS["librarian"]
    assert "view_reports" not in ROLE_PERMISSIONS["member"]


def test_T02_report_api_requires_session_and_report_permission(monkeypatch):
    monkeypatch.setenv("LIBRARY_RESERVATION_DB", "/tmp/spec015-no-session.sqlite3")
    client = TestClient(app)

    unauthenticated = client.get(
        "/api/reports",
        params={
            "type": "loans",
            "startDate": "2026-11-01",
            "endDate": "2026-11-19",
        },
    )
    assert unauthenticated.status_code == 401

    member = _session_user("member", ("borrow_book",))
    monkeypatch.setattr(main_module, "get_session_user", lambda token: member)
    forbidden = client.get(
        "/api/reports",
        params={
            "type": "loans",
            "startDate": "2026-11-01",
            "endDate": "2026-11-19",
        },
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["message"] == "คุณไม่มีสิทธิ์ดูรายงาน"


def test_T04_report_range_validation(monkeypatch, tmp_path):
    now = __import__("datetime").datetime(2026, 11, 19, 12, 0)
    validate_report_range(date(2026, 11, 1), date(2026, 11, 19), now=now)

    try:
        validate_report_range(date(2026, 11, 20), date(2026, 11, 19), now=now)
        raise AssertionError("ควรปฏิเสธวันสิ้นสุดก่อนวันเริ่ม")
    except ReportRangeError:
        pass

    try:
        validate_report_range(date(2026, 11, 1), date(2026, 11, 20), now=now)
        raise AssertionError("ควรปฏิเสธวันสิ้นสุดเกินวันนี้")
    except ReportRangeError:
        pass

    try:
        validate_report_range(date(2025, 1, 1), date(2026, 11, 19), now=now)
        raise AssertionError("ควรปฏิเสธช่วงเกิน 1 ปี")
    except ReportRangeError:
        pass


def test_T05_06_07_report_services(monkeypatch, tmp_path):
    database_path = tmp_path / "spec015.sqlite3"
    monkeypatch.setenv("LIBRARY_RESERVATION_DB", str(database_path))

    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE loans (
                loan_id TEXT PRIMARY KEY,
                member_id TEXT NOT NULL,
                request_id TEXT NOT NULL UNIQUE,
                borrowed_on TEXT NOT NULL
            );
            CREATE TABLE loan_items (
                loan_item_id TEXT PRIMARY KEY,
                loan_id TEXT NOT NULL,
                member_id TEXT NOT NULL,
                title_id TEXT NOT NULL,
                item_identifier TEXT NOT NULL,
                due_date TEXT NOT NULL,
                returned_date TEXT,
                status TEXT NOT NULL
            );
            CREATE TABLE catalog_records (
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
            );
            CREATE TABLE fine_items (
                fine_id TEXT PRIMARY KEY,
                loan_id TEXT,
                member_id TEXT NOT NULL,
                book_title TEXT NOT NULL,
                due_date TEXT NOT NULL,
                returned_date TEXT NOT NULL,
                overdue_days INTEGER NOT NULL,
                applied_rate TEXT NOT NULL,
                amount TEXT NOT NULL,
                status TEXT NOT NULL
            );
            """
        )
        connection.execute(
            "INSERT INTO loans VALUES ('LOAN-1', 'STU-1', 'REQ-1', '2026-11-10')"
        )
        connection.execute(
            """
            INSERT INTO loan_items VALUES
            ('LI-1', 'LOAN-1', 'STU-1', 'BOOK-1', 'COPY-1', '2026-11-24', NULL, 'Borrowed')
            """
        )
        connection.execute(
            """
            INSERT INTO catalog_records
            (book_id, title, authors_json, isbn, keywords_json, call_number, shelf, zone)
            VALUES ('BOOK-1', 'กขค', '[]', 'ISBN-1', '[]', '', '', '')
            """
        )
        connection.execute(
            """
            INSERT INTO fine_items
            (fine_id, loan_id, member_id, book_title, due_date, returned_date,
             overdue_days, applied_rate, amount, status)
            VALUES ('F-1', 'LOAN-1', 'STU-1', 'กขค', '2026-11-09', '2026-11-10',
                    1, '5.00', '1250.00', 'paid')
            """,
        )

    assert loan_report(date(2026, 11, 1), date(2026, 11, 19))["count"] == 1
    popular = popular_books_report(date(2026, 11, 1), date(2026, 11, 19))
    assert popular["rows"][0]["borrow_count"] == 1
    assert popular["rows"][0]["title_name"] == "กขค"

    fine = fine_report(date(2026, 11, 1), date(2026, 11, 19))
    assert fine["total_all"] == "1250.00"
    assert fine["total_paid"] == "1250.00"
    assert fine["total_outstanding"] == "0.00"

    monkeypatch.setattr(
        room_store,
        "get_room_bookings",
        lambda: [
            RoomBooking(
                booking_id="R-1",
                room_id="ROOM-1",
                booking_date=date(2026, 11, 10),
                start_time=time(9, 0),
                end_time=time(11, 30),
            )
        ],
    )
    room = room_usage_report(date(2026, 11, 1), date(2026, 11, 19))
    assert room["rows"] == [
        {"room_id": "ROOM-1", "booking_count": 1, "booked_hours": "2.50"}
    ]


def test_T11_report_metrics_and_permission(monkeypatch, tmp_path):
    monkeypatch.setenv("LIBRARY_RESERVATION_DB", str(tmp_path / "report-ac1.sqlite3"))
    admin = _session_user("admin", ("manage_users", "view_reports"))
    monkeypatch.setattr(main_module, "get_session_user", lambda token: admin)
    client = TestClient(app)

    response = client.get(
        "/api/reports",
        params={"type": "loans", "startDate": "2026-11-01", "endDate": "2026-11-19"},
    )
    assert response.status_code in (200, 422)
    if response.status_code == 200:
        payload = response.json()
        assert payload["report_type"] == "loans"
        assert "has_data" in payload

    forbidden_member = _session_user("member", ("borrow_book",))
    monkeypatch.setattr(main_module, "get_session_user", lambda token: forbidden_member)
    forbidden = client.get(
        "/api/reports",
        params={"type": "loans", "startDate": "2026-11-01", "endDate": "2026-11-19"},
    )
    assert forbidden.status_code == 403


def test_T12_csv_export_and_no_data(monkeypatch, tmp_path):
    monkeypatch.setenv("LIBRARY_RESERVATION_DB", str(tmp_path / "report-csv.sqlite3"))
    admin = _session_user("admin", ("view_reports",))
    monkeypatch.setattr(main_module, "get_session_user", lambda token: admin)
    client = TestClient(app)

    no_data = client.get(
        "/api/reports/export",
        params={"type": "loans", "startDate": "2026-11-01", "endDate": "2026-11-19"},
    )
    assert no_data.status_code == 200
    assert no_data.headers["content-type"].startswith("application/json")
    assert no_data.json()["message"] == "ไม่พบข้อมูลในช่วงเวลาที่เลือก"

    with sqlite3.connect(tmp_path / "report-csv.sqlite3") as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS loans (
                loan_id TEXT PRIMARY KEY,
                member_id TEXT NOT NULL,
                request_id TEXT NOT NULL,
                borrowed_on TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS loan_items (
                loan_item_id TEXT PRIMARY KEY,
                loan_id TEXT NOT NULL,
                member_id TEXT NOT NULL,
                title_id TEXT NOT NULL,
                item_identifier TEXT NOT NULL,
                due_date TEXT NOT NULL,
                returned_date TEXT,
                status TEXT NOT NULL
            );
            """
        )
        connection.execute(
            "INSERT INTO loans VALUES ('LOAN-CSV', 'STU-1', 'REQ-CSV', '2026-11-10')"
        )
        connection.execute(
            """
            INSERT INTO loan_items VALUES
            ('LI-CSV', 'LOAN-CSV', 'STU-1', 'BOOK-1', 'COPY-1',
             '2026-11-24', NULL, 'Borrowed')
            """
        )

    exported = client.get(
        "/api/reports/export",
        params={"type": "loans", "startDate": "2026-11-01", "endDate": "2026-11-19"},
    )
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/csv")
    assert "report-loans-2026-11-01-2026-11-19.csv" in exported.headers["content-disposition"]
    assert exported.content.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" in exported.content
    assert "จำนวนรายการยืม".encode("utf-8") in exported.content

    direct_result = get_report(
        "loans",
        date(2026, 11, 1),
        date(2026, 11, 19),
    )
    csv_bytes, filename = build_report_csv("loans", direct_result)
    assert filename == "report-loans-2026-11-01-2026-11-19.csv"
    assert csv_bytes.startswith(b"\xef\xbb\xbf")


def test_T13_invalid_ranges_and_permission(monkeypatch, tmp_path):
    monkeypatch.setenv("LIBRARY_RESERVATION_DB", str(tmp_path / "report-range.sqlite3"))
    admin = _session_user("admin", ("view_reports",))
    monkeypatch.setattr(main_module, "get_session_user", lambda token: admin)
    client = TestClient(app)

    invalid_cases = (
        ("2026-11-20", "2026-11-19"),
        ("2026-11-01", "2026-11-20"),
        ("2025-11-01", "2026-11-19"),
    )
    for start, end in invalid_cases:
        response = client.get(
            "/api/reports",
            params={"type": "loans", "startDate": start, "endDate": end},
        )
        assert response.status_code == 422
        assert response.json()["message"] == "ช่วงวันที่ไม่ถูกต้อง"

    client.cookies.clear()
    monkeypatch.setattr(main_module, "get_session_user", lambda token: None)
    unauthenticated = client.get(
        "/api/reports/export",
        params={"type": "loans", "startDate": "2026-11-01", "endDate": "2026-11-19"},
    )
    assert unauthenticated.status_code == 401


def test_T14_report_performance_95_percent_under_5_seconds(monkeypatch, tmp_path):
    database_path = tmp_path / "report-performance.sqlite3"
    monkeypatch.setenv("LIBRARY_RESERVATION_DB", str(database_path))

    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE loans (
                loan_id TEXT PRIMARY KEY,
                member_id TEXT NOT NULL,
                request_id TEXT NOT NULL UNIQUE,
                borrowed_on TEXT NOT NULL
            );
            CREATE TABLE loan_items (
                loan_item_id TEXT PRIMARY KEY,
                loan_id TEXT NOT NULL,
                member_id TEXT NOT NULL,
                title_id TEXT NOT NULL,
                item_identifier TEXT NOT NULL,
                due_date TEXT NOT NULL,
                returned_date TEXT,
                status TEXT NOT NULL
            );
            """
        )
        connection.executemany(
            "INSERT INTO loans VALUES (?, 'STU-1', ?, '2026-11-10')",
            [(f"LOAN-{index}", f"REQ-{index}") for index in range(20_000)],
        )
        connection.executemany(
            """
            INSERT INTO loan_items VALUES (?, ?, 'STU-1', 'BOOK-1', ?, '2026-11-24', NULL, 'Borrowed')
            """,
            [
                (f"LI-{index}", f"LOAN-{index}", f"COPY-{index}")
                for index in range(20_000)
            ],
        )

    durations = []
    for _ in range(100):
        started = perf_counter()
        result = loan_report(date(2026, 11, 1), date(2026, 11, 19))
        durations.append(perf_counter() - started)
        assert result["count"] == 20_000

    durations.sort()
    percentile_95 = durations[94]
    assert percentile_95 < 5.0
