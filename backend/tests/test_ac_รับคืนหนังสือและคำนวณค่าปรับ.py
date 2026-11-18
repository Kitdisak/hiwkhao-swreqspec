import json
import sqlite3
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.auth.models import User
from app.auth.session import SESSION_COOKIE, create_session
from app.book_search import models as catalog
from app.loans import service as loan_service
from app.main import app
from app.reservations.service import reservation_store_transaction
from app.returns import service as return_service

BASE_TIME = datetime.fromisoformat("2026-11-18T12:00:00+07:00")


@pytest.fixture
def return_client(monkeypatch, tmp_path):
    database_path = tmp_path / "reservation-store.sqlite3"
    monkeypatch.setenv("LIBRARY_RESERVATION_DB", str(database_path))
    records = [
        catalog.CatalogRecord(
            book_id="BOOK-RETURN-01",
            title="หนังสือทดสอบการคืน",
            copies=[
                catalog.BookCopy(
                    book_id="BOOK-RETURN-01",
                    item_identifier="COPY-RETURN-01",
                    status="Available",
                )
            ],
        )
    ]
    monkeypatch.setattr(catalog, "CATALOG_RECORDS", records)
    test_client = TestClient(app, raise_server_exceptions=False)
    test_client.cookies.set(SESSION_COOKIE, create_session("admin"))
    return test_client, database_path


def _member():
    return User(
        username="return-student",
        email="return-student@university.ac.th",
        student_id="STU-RETURN",
        password_hash="",
        user_type="student",
    )


def _borrow_copy(database_path, *, due_date="2026-12-02"):
    monkeypatch_now = datetime.fromisoformat("2026-11-18T12:00:00+07:00")
    result = loan_service.confirm_loan(
        _member(),
        ["COPY-RETURN-01"],
        "REQUEST-RETURN-01",
        now=monkeypatch_now,
    )
    assert result["success"] is True
    assert database_path.exists()
    with reservation_store_transaction() as connection:
        connection.execute(
            "UPDATE loan_items SET due_date = ? WHERE item_identifier = ?",
            (due_date, "COPY-RETURN-01"),
        )
    return result["loan_id"]


def _insert_waiting_reservation(database_path, reservation_id="RSV-RETURN-01"):
    with reservation_store_transaction() as connection:
        connection.execute(
            """
            INSERT INTO reservations (
                reservation_id, request_id, member_id, title_id, recorded_at,
                status, queue_position_at_success, first_name, last_name, member_code
            ) VALUES (?, ?, ?, ?, ?, 'Waiting', ?, ?, ?, ?)
            """,
            (
                reservation_id,
                f"REQUEST-{reservation_id}",
                "STU-WAITING",
                "BOOK-RETURN-01",
                "2026-11-17T00:00:00+00:00",
                1,
                "Waiting",
                "Member",
                "STU-WAITING",
            ),
        )


def test_AC_รับคืนหนังสือและคำนวณค่าปรับ_01_overdue_return_creates_linked_fine(
    return_client,
):
    client, database_path = return_client
    loan_id = _borrow_copy(database_path, due_date="2026-11-15")

    result = return_service.confirm_return(
        "COPY-RETURN-01",
        now=BASE_TIME,
    )

    assert result["success"] is True
    assert result["overdue_days"] == 3
    assert result["fine_amount"] == "15.00"
    assert result["copy_status"] == "Available"
    with sqlite3.connect(database_path) as connection:
        loan_item = connection.execute(
            """
            SELECT status, returned_date FROM loan_items
            WHERE item_identifier = 'COPY-RETURN-01'
            """
        ).fetchone()
        copy_status = connection.execute(
            "SELECT status FROM loan_copy_status WHERE item_identifier = ?",
            ("COPY-RETURN-01",),
        ).fetchone()[0]
        fine = connection.execute(
            """
            SELECT loan_id, member_id, overdue_days, applied_rate, amount, status
            FROM fine_items WHERE fine_id = ?
            """,
            (result["fine_id"],),
        ).fetchone()

    assert loan_item == ("Returned", "2026-11-18")
    assert copy_status == "Available"
    assert fine == (
        loan_id,
        "STU-RETURN",
        3,
        "5.00",
        "15.00",
        "outstanding",
    )
    member_fines = client.get(
        "/api/me/fines",
        params={"member_id": "STU-RETURN"},
    ).json()
    assert member_fines["total_amount"] == "15.00"
    assert len(member_fines["fines"]) == 1


def test_AC_รับคืนหนังสือและคำนวณค่าปรับ_01_staff_confirm_endpoint(
    return_client, monkeypatch
):
    client, database_path = return_client
    _borrow_copy(database_path, due_date="2026-11-15")
    monkeypatch.setattr(return_service, "_current_date", lambda now=None: date(2026, 11, 18))

    response = client.post(
        "/api/returns",
        json={"item_identifier": "COPY-RETURN-01"},
    )

    assert response.status_code == 200
    assert response.json()["fine_amount"] == "15.00"
    assert response.json()["copy_status"] == "Available"


def test_AC_รับคืนหนังสือและคำนวณค่าปรับ_01_round_half_up_and_bangkok_date(
    return_client, monkeypatch, tmp_path
):
    _, database_path = return_client
    _borrow_copy(database_path, due_date="2026-11-17")
    config_path = tmp_path / "fine-rate.json"
    config_path.write_text(json.dumps({"daily_rate": "2.125"}), encoding="utf-8")
    monkeypatch.setattr(return_service, "FINE_RATE_CONFIG_PATH", config_path)
    utc_time = datetime(2026, 11, 17, 18, 0, tzinfo=timezone.utc)

    result = return_service.lookup_return("COPY-RETURN-01", now=utc_time)

    assert result["returned_date"] == "2026-11-18"
    assert result["overdue_days"] == 1
    assert result["fine_amount"] == "2.13"


def test_AC_รับคืนหนังสือและคำนวณค่าปรับ_02_on_time_return_has_no_fine(
    return_client,
):
    _, database_path = return_client
    _borrow_copy(database_path, due_date="2026-11-18")

    result = return_service.confirm_return("COPY-RETURN-01", now=BASE_TIME)

    assert result["fine_amount"] == "0.00"
    assert result["fine_id"] is None
    with sqlite3.connect(database_path) as connection:
        fine_count = connection.execute(
            "SELECT COUNT(*) FROM fine_items WHERE loan_id = ?",
            (result["loan_id"],),
        ).fetchone()[0]
        copy_status = connection.execute(
            "SELECT status FROM loan_copy_status WHERE item_identifier = ?",
            ("COPY-RETURN-01",),
        ).fetchone()[0]
    assert fine_count == 0
    assert copy_status == "Available"


def test_AC_รับคืนหนังสือและคำนวณค่าปรับ_03_missing_active_loan_does_not_change_data(
    return_client,
):
    client, database_path = return_client

    response = client.get(
        "/api/returns/lookup",
        params={"item_identifier": "COPY-MISSING"},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "active_loan_not_found"
    assert "ตรวจสอบ" in response.json()["message"]
    with sqlite3.connect(database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert "loan_items" not in tables


def test_AC_รับคืนหนังสือและคำนวณค่าปรับ_01_02_waiting_reservation_becomes_ready(
    return_client,
):
    _, database_path = return_client
    _borrow_copy(database_path, due_date="2026-11-18")
    _insert_waiting_reservation(database_path)

    result = return_service.confirm_return("COPY-RETURN-01", now=BASE_TIME)

    assert result["copy_status"] == "Reserved"
    assert result["reservation"] == {
        "reservation_id": "RSV-RETURN-01",
        "status": "Ready",
        "pickup_deadline": "2026-11-21",
    }
    with sqlite3.connect(database_path) as connection:
        reservation_status = connection.execute(
            """
            SELECT status, reserved_item_identifier, pickup_deadline
            FROM reservations WHERE reservation_id = ?
            """,
            ("RSV-RETURN-01",),
        ).fetchone()
        copy_status = connection.execute(
            "SELECT status FROM loan_copy_status WHERE item_identifier = ?",
            ("COPY-RETURN-01",),
        ).fetchone()[0]
    assert reservation_status == ("Ready", "COPY-RETURN-01", "2026-11-21")
    assert copy_status == "Reserved"


def test_AC_รับคืนหนังสือและคำนวณค่าปรับ_01_rollback_on_fine_storage_failure(
    return_client, monkeypatch
):
    _, database_path = return_client
    loan_id = _borrow_copy(database_path, due_date="2026-11-15")
    _insert_waiting_reservation(database_path)

    def fail_insert(*args, **kwargs):
        raise sqlite3.OperationalError("fine storage unavailable")

    monkeypatch.setattr(return_service, "insert_fine_item", fail_insert)
    with pytest.raises(sqlite3.OperationalError):
        return_service.confirm_return("COPY-RETURN-01", now=BASE_TIME)

    with sqlite3.connect(database_path) as connection:
        loan_status = connection.execute(
            "SELECT status FROM loan_items WHERE item_identifier = ?",
            ("COPY-RETURN-01",),
        ).fetchone()[0]
        copy_status = connection.execute(
            "SELECT status FROM loan_copy_status WHERE item_identifier = ?",
            ("COPY-RETURN-01",),
        ).fetchone()[0]
        reservation_status = connection.execute(
            "SELECT status FROM reservations WHERE reservation_id = ?",
            ("RSV-RETURN-01",),
        ).fetchone()[0]
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        fine_count = (
            connection.execute(
                "SELECT COUNT(*) FROM fine_items WHERE loan_id = ?",
                (loan_id,),
            ).fetchone()[0]
            if "fine_items" in tables
            else 0
        )
    assert loan_status == "Borrowed"
    assert copy_status == "Borrowed"
    assert reservation_status == "Waiting"
    assert fine_count == 0


def test_AC_รับคืนหนังสือและคำนวณค่าปรับ_01_rejects_multiple_active_loans(
    return_client,
):
    _, database_path = return_client
    loan_id = _borrow_copy(database_path, due_date="2026-11-15")
    with reservation_store_transaction() as connection:
        connection.execute("DROP INDEX one_active_loan_per_copy")
        connection.execute(
            """
            INSERT INTO loans (loan_id, member_id, request_id, borrowed_on)
            VALUES (?, ?, ?, ?)
            """,
            ("LOAN-DUPLICATE", "STU-RETURN", "REQUEST-DUPLICATE", "2026-11-18"),
        )
        connection.execute(
            """
            INSERT INTO loan_items (
                loan_item_id, loan_id, member_id, title_id, item_identifier,
                due_date, returned_date, status
            ) VALUES (?, ?, ?, ?, ?, ?, NULL, 'Borrowed')
            """,
            (
                "ITEM-DUPLICATE",
                "LOAN-DUPLICATE",
                "STU-RETURN",
                "BOOK-RETURN-01",
                "COPY-RETURN-01",
                "2026-11-15",
            ),
        )

    with pytest.raises(return_service.ReturnError) as error:
        return_service.confirm_return("COPY-RETURN-01", now=BASE_TIME)

    assert error.value.code == "multiple_active_loans"
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            """
            SELECT COUNT(*) FROM loan_items
            WHERE item_identifier = ? AND status = 'Borrowed'
            """,
            ("COPY-RETURN-01",),
        ).fetchone()[0] == 2
        assert connection.execute(
            "SELECT status FROM loan_copy_status WHERE item_identifier = ?",
            ("COPY-RETURN-01",),
        ).fetchone()[0] == "Borrowed"
    assert loan_id


def test_AC_รับคืนหนังสือและคำนวณค่าปรับ_01_migrates_legacy_loan_items_schema(
    monkeypatch, tmp_path
):
    database_path = tmp_path / "legacy-store.sqlite3"
    monkeypatch.setenv("LIBRARY_RESERVATION_DB", str(database_path))
    with reservation_store_transaction() as connection:
        connection.execute(
            """
            CREATE TABLE loans (
                loan_id TEXT PRIMARY KEY,
                member_id TEXT NOT NULL,
                request_id TEXT NOT NULL UNIQUE,
                borrowed_on TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO loans VALUES ('LOAN-LEGACY', 'STU-LEGACY', 'REQ-LEGACY', '2026-11-01')
            """
        )
        connection.execute(
            """
            CREATE TABLE loan_items (
                loan_item_id TEXT PRIMARY KEY,
                loan_id TEXT NOT NULL REFERENCES loans(loan_id),
                member_id TEXT NOT NULL,
                title_id TEXT NOT NULL,
                item_identifier TEXT NOT NULL,
                due_date TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status = 'Borrowed')
            )
            """
        )
        connection.execute(
            """
            INSERT INTO loan_items VALUES (
                'ITEM-LEGACY', 'LOAN-LEGACY', 'STU-LEGACY', 'BOOK-RETURN-01',
                'COPY-RETURN-01', '2026-11-15', 'Borrowed'
            )
            """
        )
        connection.execute(
            """
            CREATE UNIQUE INDEX one_active_loan_per_copy
            ON loan_items(item_identifier) WHERE status = 'Borrowed'
            """
        )

    with reservation_store_transaction() as connection:
        loan_service._initialize_loan_store(connection)
        item = connection.execute(
            "SELECT status, returned_date FROM loan_items WHERE loan_item_id = ?",
            ("ITEM-LEGACY",),
        ).fetchone()

    assert tuple(item) == ("Borrowed", None)
