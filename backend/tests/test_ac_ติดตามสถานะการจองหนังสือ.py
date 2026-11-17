from __future__ import annotations

import sqlite3
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

import app.auth.service as auth_service
import app.book_search.models as catalog_models
import app.reservations.service as reservation_service
from app.auth.service import USERS
from app.book_search.models import CatalogRecord
from app.main import app


@pytest.fixture
def reservation_tracking_environment(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "LIBRARY_RESERVATION_DB", str(tmp_path / "reservations.sqlite3")
    )
    members = [
        replace(
            USERS[0],
            username="member-one",
            student_id="STU-001",
            first_name="กมล",
            last_name="ทดสอบ",
        ),
        replace(
            USERS[0],
            username="member-two",
            student_id="STU-002",
            first_name="กนก",
            last_name="ตัวอย่าง",
        ),
    ]
    monkeypatch.setattr(auth_service, "USERS", members)
    monkeypatch.setattr(
        catalog_models,
        "CATALOG_RECORDS",
        [
            CatalogRecord(
                book_id="BOOK-001",
                title="หนังสือรอรับ",
                authors=["ผู้แต่งหนึ่ง"],
            ),
            CatalogRecord(
                book_id="BOOK-002",
                title="หนังสือพร้อมรับ",
                authors=["ผู้แต่งสอง"],
            ),
            CatalogRecord(
                book_id="BOOK-003",
                title="หนังสือที่เสร็จแล้ว",
                authors=["ผู้แต่งสาม"],
            ),
        ],
    )
    client = TestClient(app)
    login_response = client.post(
        "/api/auth/login",
        json={"username": members[0].username, "password": "pass1234"},
    )
    assert login_response.json()["success"] is True
    return client, members


def _insert_reservation(
    *,
    reservation_id: str,
    member_id: str,
    title_id: str,
    status: str,
    recorded_at: str,
    first_name: str,
    last_name: str,
    member_code: str,
    pickup_deadline: str | None = None,
):
    connection = reservation_service._connect()
    try:
        connection.execute(
            """
            INSERT INTO reservations (
                reservation_id, request_id, member_id, title_id, recorded_at,
                status, pickup_deadline, queue_position_at_success,
                first_name, last_name, member_code
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
            """,
            (
                reservation_id,
                f"request-{reservation_id}",
                member_id,
                title_id,
                recorded_at,
                status,
                pickup_deadline,
                first_name,
                last_name,
                member_code,
            ),
        )
    finally:
        connection.close()


def _insert_member_reservation(
    members,
    *,
    reservation_id: str,
    member_index: int = 0,
    title_id: str,
    status: str,
    recorded_at: str,
    pickup_deadline: str | None = None,
):
    member = members[member_index]
    _insert_reservation(
        reservation_id=reservation_id,
        member_id=member.student_id,
        title_id=title_id,
        status=status,
        recorded_at=recorded_at,
        first_name=member.first_name,
        last_name=member.last_name,
        member_code=member.student_id,
        pickup_deadline=pickup_deadline,
    )


def test_AC_ติดตามสถานะการจองหนังสือ_01_lists_current_user_and_recalculates_waiting_queue(
    reservation_tracking_environment,
):
    client, members = reservation_tracking_environment
    _insert_member_reservation(
        members,
        reservation_id="ahead",
        member_index=1,
        title_id="BOOK-001",
        status="Waiting",
        recorded_at="2026-11-15T08:00:00+00:00",
    )
    _insert_member_reservation(
        members,
        reservation_id="waiting",
        title_id="BOOK-001",
        status="Waiting",
        recorded_at="2026-11-16T08:00:00+00:00",
    )
    _insert_member_reservation(
        members,
        reservation_id="ready",
        title_id="BOOK-002",
        status="Ready",
        recorded_at="2026-11-16T09:00:00+00:00",
        pickup_deadline="2026-11-20",
    )
    _insert_member_reservation(
        members,
        reservation_id="completed",
        title_id="BOOK-003",
        status="Completed",
        recorded_at="2026-11-16T10:00:00+00:00",
        pickup_deadline="2026-11-21",
    )

    response = client.get("/api/me/reservations")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    reservations = {
        item["reservation_id"]: item for item in response.json()["reservations"]
    }
    assert set(reservations) == {"waiting", "ready", "completed"}
    assert reservations["waiting"]["title"] == "หนังสือรอรับ"
    assert reservations["waiting"]["authors"] == ["ผู้แต่งหนึ่ง"]
    assert reservations["waiting"]["recorded_at"] == "2026-11-16T08:00:00+00:00"
    assert reservations["waiting"]["status"] == "Waiting"
    assert reservations["waiting"]["queue_position"] == 2
    assert reservations["ready"]["status"] == "Ready"
    assert reservations["ready"]["pickup_deadline"] == "2026-11-20"
    assert reservations["completed"]["status"] == "Completed"
    assert reservations["completed"]["pickup_deadline"] is None
    assert all(
        "item_identifier" not in reservation
        for reservation in response.json()["reservations"]
    )

    connection = reservation_service._connect()
    try:
        connection.execute(
            "UPDATE reservations SET status = 'Completed' WHERE reservation_id = ?",
            ("ahead",),
        )
    finally:
        connection.close()

    updated = client.get("/api/me/reservations")
    updated_reservations = {
        item["reservation_id"]: item for item in updated.json()["reservations"]
    }
    assert updated_reservations["waiting"]["queue_position"] == 1


def test_AC_ติดตามสถานะการจองหนังสือ_02_1_includes_ready_deadline(
    reservation_tracking_environment,
):
    client, members = reservation_tracking_environment
    _insert_member_reservation(
        members,
        reservation_id="ready-with-deadline",
        title_id="BOOK-002",
        status="Ready",
        recorded_at="2026-11-16T09:00:00+00:00",
        pickup_deadline="2026-11-20",
    )

    response = client.get("/api/me/reservations")

    assert response.status_code == 200
    assert response.json()["reservations"][0]["pickup_deadline"] == "2026-11-20"


def test_AC_ติดตามสถานะการจองหนังสือ_02_2_omits_ready_deadline_when_missing(
    reservation_tracking_environment,
):
    client, members = reservation_tracking_environment
    _insert_member_reservation(
        members,
        reservation_id="ready-without-deadline",
        title_id="BOOK-002",
        status="Ready",
        recorded_at="2026-11-16T09:00:00+00:00",
    )

    response = client.get("/api/me/reservations")

    assert response.status_code == 200
    assert response.json()["reservations"][0]["pickup_deadline"] is None


def test_AC_ติดตามสถานะการจองหนังสือ_02_3_hides_deadline_for_other_statuses(
    reservation_tracking_environment,
):
    client, members = reservation_tracking_environment
    _insert_member_reservation(
        members,
        reservation_id="waiting-with-deadline",
        title_id="BOOK-001",
        status="Waiting",
        recorded_at="2026-11-16T08:00:00+00:00",
        pickup_deadline="2026-11-20",
    )
    _insert_member_reservation(
        members,
        reservation_id="completed-with-deadline",
        title_id="BOOK-003",
        status="Completed",
        recorded_at="2026-11-16T10:00:00+00:00",
        pickup_deadline="2026-11-20",
    )

    response = client.get("/api/me/reservations")
    reservations = {
        item["reservation_id"]: item for item in response.json()["reservations"]
    }

    assert response.status_code == 200
    assert reservations["waiting-with-deadline"]["pickup_deadline"] is None
    assert reservations["completed-with-deadline"]["pickup_deadline"] is None
    assert reservations["waiting-with-deadline"]["queue_position"] == 1
    assert reservations["completed-with-deadline"]["queue_position"] is None


def test_AC_ติดตามสถานะการจองหนังสือ_03_returns_empty_list(
    reservation_tracking_environment,
):
    client, _ = reservation_tracking_environment

    response = client.get("/api/me/reservations")

    assert response.status_code == 200
    assert response.json() == {"reservations": []}


def test_reservations_endpoint_requires_login():
    response = TestClient(app).get("/api/me/reservations")

    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["code"] == "authentication_required"


def test_existing_reservation_database_adds_optional_pickup_deadline(
    tmp_path, monkeypatch
):
    database_path = tmp_path / "existing-reservations.sqlite3"
    connection = sqlite3.connect(database_path)
    connection.execute(
        """
        CREATE TABLE reservations (
            reservation_id TEXT PRIMARY KEY,
            request_id TEXT NOT NULL UNIQUE,
            member_id TEXT NOT NULL,
            title_id TEXT NOT NULL,
            recorded_at TEXT NOT NULL,
            status TEXT NOT NULL CHECK (status IN ('Waiting', 'Ready', 'Completed')),
            queue_position_at_success INTEGER NOT NULL,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            member_code TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        INSERT INTO reservations (
            reservation_id, request_id, member_id, title_id, recorded_at, status,
            queue_position_at_success, first_name, last_name, member_code
        ) VALUES ('old', 'old-request', 'STU-001', 'BOOK-001',
                  '2026-11-16T08:00:00+00:00', 'Waiting', 1, 'กมล',
                  'ทดสอบ', 'STU-001')
        """
    )
    connection.commit()
    connection.close()
    monkeypatch.setenv("LIBRARY_RESERVATION_DB", str(database_path))

    migrated = reservation_service._connect()
    try:
        columns = {
            row["name"] for row in migrated.execute("PRAGMA table_info(reservations)")
        }
        reservation = migrated.execute(
            "SELECT pickup_deadline FROM reservations WHERE reservation_id = 'old'"
        ).fetchone()
    finally:
        migrated.close()

    assert "pickup_deadline" in columns
    assert reservation["pickup_deadline"] is None
