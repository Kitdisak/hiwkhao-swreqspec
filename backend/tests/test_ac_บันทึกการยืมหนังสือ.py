from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import threading
import time
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.auth.models import User
from app.auth import service as auth_service
from app.auth.session import SESSION_COOKIE, create_session
from app.book_search import models as catalog
from app.loans import service as loan_service
from app.main import app
from app.reservations.service import reservation_store_transaction


@pytest.fixture
def loan_client(monkeypatch, tmp_path):
    database_path = tmp_path / "reservation-store.sqlite3"
    monkeypatch.setenv("LIBRARY_RESERVATION_DB", str(database_path))
    records = [
        catalog.CatalogRecord(
            book_id="BOOK-T-01",
            title="หนังสือทั่วไป A",
            copies=[
                catalog.BookCopy(
                    book_id="BOOK-T-01",
                    item_identifier="COPY-T-01",
                    status="Available",
                ),
                catalog.BookCopy(
                    book_id="BOOK-T-01",
                    item_identifier="COPY-T-02",
                    status="Available",
                ),
            ],
        ),
        catalog.CatalogRecord(
            book_id="BOOK-T-02",
            title="หนังสือทั่วไป B",
            copies=[
                catalog.BookCopy(
                    book_id="BOOK-T-02",
                    item_identifier="COPY-T-03",
                    status="Available",
                )
            ],
        ),
    ]
    monkeypatch.setattr(catalog, "CATALOG_RECORDS", records)
    test_client = TestClient(app, raise_server_exceptions=False)
    test_client.cookies.set(SESSION_COOKIE, create_session("admin"))
    return test_client, database_path


def _student():
    return User(
        username="s12345",
        email="s12345@university.ac.th",
        student_id="STU-001",
        password_hash="",
        user_type="student",
    )


def _insert_ready_reservation(database_path, item_identifier="COPY-T-01"):
    with reservation_store_transaction() as connection:
        connection.execute(
            """
            INSERT INTO reservations (
                reservation_id, request_id, member_id, title_id, recorded_at,
                status, reserved_item_identifier, queue_position_at_success,
                first_name, last_name, member_code
            ) VALUES (?, ?, ?, ?, ?, 'Ready', ?, ?, ?, ?, ?)
            """,
            (
                "RSV-READY-01",
                "REQUEST-READY-01",
                "STU-001",
                "BOOK-T-01",
                "2026-11-18T00:00:00+00:00",
                item_identifier,
                1,
                "Test",
                "Member",
                "STU-001",
            ),
        )
        connection.execute(
            "UPDATE loan_copy_status SET status = 'Reserved' WHERE item_identifier = ?",
            (item_identifier,),
        )


def test_AC_บันทึกการยืมหนังสือ_01_lookup_student_and_staff(loan_client):
    client, _ = loan_client
    student = client.get(
        "/api/members/lookup", params={"identifier": "STU-001"}
    )
    staff = client.get(
        "/api/members/lookup",
        params={"identifier": "admin@university.ac.th"},
    )
    missing = client.get(
        "/api/members/lookup", params={"identifier": "not-a-member"}
    )

    assert student.status_code == 200
    assert student.json()["member"]["member_type"] == "student"
    assert staff.status_code == 200
    assert staff.json()["member"]["member_type"] == "staff"
    assert missing.status_code == 404
    assert missing.json()["message"] == "ไม่พบข้อมูลสมาชิก"


def test_AC_บันทึกการยืมหนังสือ_01_borrow_completes_reserved_copy_in_same_store(
    loan_client,
):
    client, database_path = loan_client
    loan_service.check_copy(_student(), "COPY-T-01")
    _insert_ready_reservation(database_path)

    response = client.post(
        "/api/loans",
        json={
            "member_identifier": "STU-001",
            "item_identifiers": ["COPY-T-01"],
            "request_id": "REQUEST-LOAN-01",
        },
    )

    assert response.status_code == 200
    result = response.json()
    assert result["success"] is True
    assert result["items"][0]["due_date"]
    with sqlite3.connect(database_path) as connection:
        reservation_status = connection.execute(
            "SELECT status FROM reservations WHERE reservation_id = 'RSV-READY-01'"
        ).fetchone()[0]
        copy_status = connection.execute(
            "SELECT status FROM loan_copy_status WHERE item_identifier = 'COPY-T-01'"
        ).fetchone()[0]
        loan_count = connection.execute("SELECT COUNT(*) FROM loans").fetchone()[0]
    assert reservation_status == "Completed"
    assert copy_status == "Borrowed"
    assert loan_count == 1


def test_AC_บันทึกการยืมหนังสือ_01_available_copy_records_due_date_and_status(
    loan_client,
):
    _, database_path = loan_client
    borrowed_at = datetime(2026, 11, 18, 23, 30, tzinfo=ZoneInfo("Asia/Bangkok"))

    result = loan_service.confirm_loan(
        _student(),
        ["COPY-T-01"],
        "REQUEST-AVAILABLE-01",
        now=borrowed_at,
    )

    assert result["success"] is True
    assert result["items"][0]["due_date"] == "2026-12-02"
    with sqlite3.connect(database_path) as connection:
        loan_item = connection.execute(
            """
            SELECT due_date, status
            FROM loan_items
            WHERE item_identifier = 'COPY-T-01'
            """
        ).fetchone()
        copy_status = connection.execute(
            "SELECT status FROM loan_copy_status WHERE item_identifier = 'COPY-T-01'"
        ).fetchone()[0]
        loan_count = connection.execute("SELECT COUNT(*) FROM loans").fetchone()[0]

    assert loan_item == ("2026-12-02", "Borrowed")
    assert copy_status == "Borrowed"
    assert loan_count == 1


def test_AC_บันทึกการยืมหนังสือ_01_repeated_request_returns_original_result(
    loan_client,
):
    client, database_path = loan_client
    payload = {
        "member_identifier": "STU-001",
        "item_identifiers": ["COPY-T-01"],
        "request_id": "REQUEST-IDEMPOTENT-01",
    }

    first = client.post("/api/loans", json=payload)
    second = client.post("/api/loans", json=payload)

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM loans").fetchone()[0] == 1


@pytest.mark.parametrize(
    "member",
    [
        User(
            username="suspended",
            email="suspended@university.ac.th",
            student_id="STU-SUSPENDED",
            password_hash="",
            user_type="student",
            account_status="Suspended",
        ),
        User(
            username="overdue",
            email="overdue@university.ac.th",
            student_id="STU-OVERDUE",
            password_hash="",
            user_type="student",
            overdue_count=1,
        ),
        User(
            username="fine",
            email="fine@university.ac.th",
            student_id="STU-FINE",
            password_hash="",
            user_type="student",
            unpaid_fine_count=1,
        ),
        User(
            username="external",
            email="external@example.org",
            student_id=None,
            password_hash="",
            user_type="external",
        ),
    ],
    ids=["suspended", "overdue", "unpaid-fine", "external"],
)
def test_AC_บันทึกการยืมหนังสือ_02_rejects_ineligible_member_and_whole_list(
    loan_client, monkeypatch, member
):
    _, database_path = loan_client
    monkeypatch.setattr(loan_service, "get_member_loans", lambda _member_id: [])

    result = loan_service.confirm_loan(
        member,
        ["COPY-T-01", "COPY-T-02"],
        f"REQUEST-INELIGIBLE-{member.username}",
    )

    assert result["success"] is False
    assert result["message"] == "ไม่สามารถยืมได้"
    assert [item["message"] for item in result["items"]] == [
        "ไม่สามารถยืมได้",
        "ไม่สามารถยืมได้",
    ]
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM loans").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM loan_items").fetchone()[0] == 0
        copy_statuses = connection.execute(
            """
            SELECT status FROM loan_copy_status
            WHERE item_identifier IN ('COPY-T-01', 'COPY-T-02')
            ORDER BY item_identifier
            """
        ).fetchall()
    assert copy_statuses == [("Available",), ("Available",)]


def test_AC_บันทึกการยืมหนังสือ_02_rejects_member_at_limit_before_request(
    loan_client, monkeypatch
):
    _, database_path = loan_client
    monkeypatch.setattr(loan_service, "get_member_loans", lambda _member_id: [])
    loan_service.check_copy(_student(), "COPY-T-01")

    with reservation_store_transaction() as connection:
        maximum_items = connection.execute(
            """
            SELECT maximum_items FROM loan_policies
            WHERE member_type = 'student' AND book_type = 'หนังสือทั่วไป'
            """
        ).fetchone()["maximum_items"]
        connection.execute(
            """
            INSERT INTO loans (loan_id, member_id, request_id, borrowed_on)
            VALUES ('FULL-LOAN', 'STU-001', 'FULL-REQUEST', '2026-11-18')
            """
        )
        for index in range(maximum_items):
            connection.execute(
                """
                INSERT INTO loan_items (
                    loan_item_id, loan_id, member_id, title_id,
                    item_identifier, due_date, status
                ) VALUES (?, 'FULL-LOAN', 'STU-001', 'OLD-BOOK', ?, '2026-12-01', 'Borrowed')
                """,
                (f"FULL-ITEM-{index}", f"FULL-COPY-{index}"),
            )

    result = loan_service.confirm_loan(
        _student(),
        ["COPY-T-01", "COPY-T-02"],
        "REQUEST-FULL-01",
    )

    assert result["success"] is False
    assert result["message"] == "ไม่สามารถยืมได้"
    assert [item["message"] for item in result["items"]] == [
        "ไม่สามารถยืมได้",
        "ไม่สามารถยืมได้",
    ]
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM loans WHERE request_id = 'REQUEST-FULL-01'"
        ).fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM loan_items").fetchone()[0] == maximum_items
        copy_statuses = connection.execute(
            """
            SELECT status FROM loan_copy_status
            WHERE item_identifier IN ('COPY-T-01', 'COPY-T-02')
            ORDER BY item_identifier
            """
        ).fetchall()
    assert copy_statuses == [("Available",), ("Available",)]


def test_AC_บันทึกการยืมหนังสือ_03_partial_success_and_duplicate(loan_client):
    client, database_path = loan_client

    response = client.post(
        "/api/loans",
        json={
            "member_identifier": "STU-001",
            "item_identifiers": [
                "COPY-T-01",
                "COPY-NOT-FOUND",
                "COPY-T-01",
            ],
            "request_id": "REQUEST-PARTIAL-01",
        },
    )

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["success"] for item in items] == [True, False, False]
    assert [item["item_identifier"] for item in items] == [
        "COPY-T-01",
        "COPY-NOT-FOUND",
        "COPY-T-01",
    ]
    assert items[0]["due_date"]
    assert items[1]["message"] == "ไม่สามารถยืมได้"
    assert items[2]["message"] == "รหัสนี้อยู่ในรายการแล้ว"
    with sqlite3.connect(database_path) as connection:
        loan_items = connection.execute(
            "SELECT item_identifier, status FROM loan_items"
        ).fetchall()
        copy_statuses = connection.execute(
            """
            SELECT item_identifier, status FROM loan_copy_status
            WHERE item_identifier IN ('COPY-T-01', 'COPY-T-02')
            ORDER BY item_identifier
            """
        ).fetchall()
    assert loan_items == [("COPY-T-01", "Borrowed")]
    assert copy_statuses == [
        ("COPY-T-01", "Borrowed"),
        ("COPY-T-02", "Available"),
    ]


def test_AC_บันทึกการยืมหนังสือ_03_scan_stops_at_member_limit(
    loan_client, monkeypatch
):
    client, database_path = loan_client
    monkeypatch.setattr(loan_service, "get_member_loans", lambda _member_id: [])
    with reservation_store_transaction() as connection:
        loan_service._initialize_loan_store(connection)
        maximum_items = connection.execute(
            """
            SELECT maximum_items FROM loan_policies
            WHERE member_type = 'student' AND book_type = 'หนังสือทั่วไป'
            """
        ).fetchone()["maximum_items"]
        connection.execute(
            """
            INSERT INTO loans (loan_id, member_id, request_id, borrowed_on)
            VALUES ('OLD-LOAN', 'STU-001', 'OLD-REQUEST', '2026-11-18')
            """
        )
        for index in range(maximum_items - 1):
            connection.execute(
                """
                INSERT INTO loan_items (
                    loan_item_id, loan_id, member_id, title_id,
                    item_identifier, due_date, status
                ) VALUES (?, 'OLD-LOAN', 'STU-001', 'OLD-BOOK', ?, '2026-12-01', 'Borrowed')
                """,
                (f"OLD-ITEM-{index}", f"OLD-COPY-{index}"),
            )

    first_scan = client.post(
        "/api/loans/check",
        json={
            "member_identifier": "STU-001",
            "item_identifier": "COPY-T-01",
            "pending_item_identifiers": [],
        },
    )
    next_scan = client.post(
        "/api/loans/check",
        json={
            "member_identifier": "STU-001",
            "item_identifier": "COPY-T-02",
            "pending_item_identifiers": ["COPY-T-01"],
        },
    )

    assert first_scan.json()["success"] is True
    assert next_scan.json()["success"] is False
    assert next_scan.json()["message"] == "ไม่สามารถยืมได้"

    confirmation = client.post(
        "/api/loans",
        json={
            "member_identifier": "STU-001",
            "item_identifiers": ["COPY-T-01", "COPY-T-02"],
            "request_id": "REQUEST-LIMIT-DURING-SCAN",
        },
    )

    assert confirmation.status_code == 200
    results = confirmation.json()["items"]
    assert [item["success"] for item in results] == [True, False]
    assert results[1]["message"] == "ไม่สามารถยืมได้"
    with sqlite3.connect(database_path) as connection:
        item_count = connection.execute(
            "SELECT COUNT(*) FROM loan_items"
        ).fetchone()[0]
        copy_statuses = connection.execute(
            """
            SELECT item_identifier, status FROM loan_copy_status
            WHERE item_identifier IN ('COPY-T-01', 'COPY-T-02')
            ORDER BY item_identifier
            """
        ).fetchall()
    assert item_count == maximum_items
    assert copy_statuses == [
        ("COPY-T-01", "Borrowed"),
        ("COPY-T-02", "Available"),
    ]

def test_AC_บันทึกการยืมหนังสือ_01_rolls_back_copy_and_loan_if_reservation_fails(
    loan_client,
):
    client, database_path = loan_client
    loan_service.check_copy(_student(), "COPY-T-01")
    _insert_ready_reservation(database_path)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TRIGGER fail_reservation_completion
            BEFORE UPDATE OF status ON reservations
            WHEN NEW.status = 'Completed'
            BEGIN
                SELECT RAISE(ABORT, 'forced reservation failure');
            END
            """
        )

    response = client.post(
        "/api/loans",
        json={
            "member_identifier": "STU-001",
            "item_identifiers": ["COPY-T-01"],
            "request_id": "REQUEST-ROLLBACK-01",
        },
    )

    assert response.status_code == 500
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM loans").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM loan_items").fetchone()[0] == 0
        assert connection.execute(
            "SELECT status FROM loan_copy_status WHERE item_identifier = 'COPY-T-01'"
        ).fetchone()[0] == "Reserved"
        assert connection.execute(
            "SELECT status FROM reservations WHERE reservation_id = 'RSV-READY-01'"
        ).fetchone()[0] == "Ready"


def test_AC_บันทึกการยืมหนังสือ_03_only_one_concurrent_borrow_succeeds(
    loan_client,
):
    def borrow(request_id):
        return loan_service.confirm_loan(
            _student(),
            ["COPY-T-01"],
            request_id,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                borrow,
                ["REQUEST-CONCURRENT-01", "REQUEST-CONCURRENT-02"],
            )
        )

    assert sum(result["success"] for result in results) == 1


def test_AC_บันทึกการยืมหนังสือ_01_due_date_uses_server_bangkok_date(
    loan_client,
):
    _, _database_path = loan_client
    server_time = datetime(2026, 11, 18, 23, 30, tzinfo=ZoneInfo("Asia/Bangkok"))
    member = User(
        username="staff",
        email="admin@university.ac.th",
        student_id="ADM-001",
        password_hash="",
        user_type="staff",
    )

    result = loan_service.confirm_loan(
        member,
        ["COPY-T-01"],
        "REQUEST-DATE-01",
        now=server_time,
    )

    assert result["items"][0]["due_date"] == "2026-12-18"


def test_AC_บันทึกการยืมหนังสือ_03_staff_only_and_missing_member_responses(
    loan_client,
):
    client, _ = loan_client
    client.cookies.clear()

    unauthenticated = client.get(
        "/api/members/lookup", params={"identifier": "STU-001"}
    )
    assert unauthenticated.status_code == 401

    client.cookies.set(SESSION_COOKIE, create_session("s12345"))
    student_actor = client.post(
        "/api/loans",
        json={
            "member_identifier": "STU-001",
            "item_identifiers": ["COPY-T-01"],
            "request_id": "REQUEST-STUDENT-ACTOR",
        },
    )
    assert student_actor.status_code == 403


def test_NFR_PERF_01_scan_and_confirm_targets_with_ten_librarians(
    monkeypatch, tmp_path
):
    database_path = tmp_path / "reservation-performance.sqlite3"
    monkeypatch.setenv("LIBRARY_RESERVATION_DB", str(database_path))
    copies_per_member = 10
    staff_members = [
        User(
            username=f"perf-librarian-{index:02d}",
            email=f"perf-librarian-{index:02d}@library.example",
            student_id=f"PERF-{index:02d}",
            password_hash="",
            user_type="staff",
            first_name="Library",
            last_name=f"Staff {index:02d}",
        )
        for index in range(10)
    ]
    monkeypatch.setattr(auth_service, "USERS", staff_members)
    records = []
    for member_index in range(10):
        copies = [
            catalog.BookCopy(
                book_id=f"PERF-BOOK-{member_index:02d}",
                item_identifier=f"PERF-COPY-{member_index:02d}-{copy_index:02d}",
                status="Available",
            )
            for copy_index in range(copies_per_member)
        ]
        records.append(
            catalog.CatalogRecord(
                book_id=f"PERF-BOOK-{member_index:02d}",
                title=f"หนังสือทดสอบ {member_index:02d}",
                copies=copies,
            )
        )
    monkeypatch.setattr(catalog, "CATALOG_RECORDS", records)

    clients = []
    for member in staff_members:
        client = TestClient(app)
        client.cookies.set(SESSION_COOKIE, create_session(member.username))
        clients.append(client)

    barrier = threading.Barrier(len(staff_members))

    def scan_once(index):
        barrier.wait()
        started = time.perf_counter()
        response = clients[index].post(
            "/api/loans/check",
            json={
                "member_identifier": staff_members[index].email,
                "item_identifier": f"PERF-COPY-{index:02d}-00",
            },
        )
        elapsed = time.perf_counter() - started
        assert response.status_code == 200
        assert response.json()["success"] is True
        return elapsed

    with ThreadPoolExecutor(max_workers=10) as executor:
        scan_times = list(executor.map(scan_once, range(10)))

    barrier = threading.Barrier(len(staff_members))

    def confirm_once(index):
        barrier.wait()
        started = time.perf_counter()
        response = clients[index].post(
            "/api/loans",
            json={
                "member_identifier": staff_members[index].email,
                "item_identifiers": [
                    f"PERF-COPY-{index:02d}-{copy_index:02d}"
                    for copy_index in range(copies_per_member)
                ],
                "request_id": f"PERF-REQUEST-{index:02d}",
            },
        )
        elapsed = time.perf_counter() - started
        assert response.status_code == 200
        assert response.json()["success"] is True
        return elapsed

    with ThreadPoolExecutor(max_workers=10) as executor:
        confirm_times = list(executor.map(confirm_once, range(10)))

    assert sum(value <= 1.0 for value in scan_times) / len(scan_times) >= 0.95
    assert sum(value <= 2.0 for value in confirm_times) / len(confirm_times) >= 0.95
