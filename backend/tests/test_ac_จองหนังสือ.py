from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

import app.auth.service as auth_service
import app.book_search.models as catalog_models
import app.reservations.service as reservation_service
from app.auth.service import USERS
from app.book_search.models import BookCopy, CatalogRecord
from app.main import app


@pytest.fixture
def reservation_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARY_RESERVATION_DB", str(tmp_path / "reservations.sqlite3"))
    members = [
        replace(
            USERS[0],
            student_id="STU-001",
            first_name="กมล",
            last_name="ทดสอบ",
            account_status="Active",
            overdue_count=0,
            unpaid_fine_count=0,
        )
    ]
    monkeypatch.setattr(auth_service, "USERS", members)
    record = CatalogRecord(
        book_id="BOOK-RESERVATION",
        title="หนังสือทดสอบการจอง",
        copies=[
            BookCopy(
                book_id="BOOK-RESERVATION",
                item_identifier="COPY-RESERVATION",
                status="Borrowed",
            )
        ],
    )
    monkeypatch.setattr(catalog_models, "CATALOG_RECORDS", [record])
    client = TestClient(app)
    login_response = client.post(
        "/api/auth/login",
        json={"username": members[0].username, "password": "pass1234"},
    )
    assert login_response.json()["success"] is True
    return client, members, record


def _reserve(client: TestClient, request_id: str, title_id: str = "BOOK-RESERVATION"):
    return client.post(
        "/api/reservations",
        json={"title_id": title_id, "request_id": request_id},
    )


def test_AC_จองหนังสือ_01_1_creates_waiting_reservation_at_first_position(
    reservation_environment,
):
    client, _, _ = reservation_environment

    response = _reserve(client, "request-first")

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert response.json()["status"] == "Waiting"
    assert response.json()["queue_position"] == 1
    assert response.json()["message"] == "จองสำเร็จ ลำดับคิวที่ 1"
    assert len(reservation_service.list_reservations_for_testing()) == 1


def test_AC_จองหนังสือ_01_2_replays_original_result_for_same_request(
    reservation_environment,
):
    client, _, _ = reservation_environment

    first = _reserve(client, "request-replay")
    repeated = _reserve(client, "request-replay")

    assert repeated.status_code == 200
    assert repeated.json() == first.json()
    assert len(reservation_service.list_reservations_for_testing()) == 1


def test_AC_จองหนังสือ_01_3_rejects_intentional_duplicate_with_existing_position(
    reservation_environment,
):
    client, _, _ = reservation_environment
    first = _reserve(client, "request-original")

    duplicate = _reserve(client, "request-new")

    assert duplicate.status_code == 409
    assert duplicate.json()["message"] == (
        "คุณมีรายการจองหนังสือเล่มนี้อยู่แล้ว ลำดับคิวที่ 1"
    )
    assert len(reservation_service.list_reservations_for_testing()) == 1
    assert first.json()["queue_position"] == 1


def test_AC_จองหนังสือ_01_4_concurrent_requests_create_one_reservation(
    reservation_environment,
):
    client, members, _ = reservation_environment
    second_client = TestClient(app)
    second_client.post(
        "/api/auth/login",
        json={"username": members[0].username, "password": "pass1234"},
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(
            executor.map(
                lambda args: _reserve(args[0], args[1]),
                [(client, "request-race-1"), (second_client, "request-race-2")],
            )
        )

    assert sorted(response.status_code for response in responses) == [200, 409]
    assert len(reservation_service.list_reservations_for_testing()) == 1


def test_AC_จองหนังสือ_02_1_queue_position_counts_waiting_reservations(
    reservation_environment,
):
    client, members, _ = reservation_environment
    members[0] = replace(members[0], first_name="Alice")
    for index in (2, 3):
        member = replace(
            members[0],
            username=f"member-{index}",
            student_id=f"STU-{index:03d}",
            first_name=f"ผู้ใช้{index}",
            last_name="ทดสอบ",
        )
        members.append(member)

    first_client = TestClient(app)
    second_client = TestClient(app)
    first_client.post(
        "/api/auth/login",
        json={"username": members[1].username, "password": "pass1234"},
    )
    second_client.post(
        "/api/auth/login",
        json={"username": members[2].username, "password": "pass1234"},
    )

    first = _reserve(first_client, "queue-first")
    second = _reserve(second_client, "queue-second")
    third = _reserve(client, "queue-third")

    assert first.json()["queue_position"] == 1
    assert second.json()["queue_position"] == 2
    assert third.json()["queue_position"] == 3


def test_AC_จองหนังสือ_02_2_tie_breaks_thai_names_before_latin_names(
    reservation_environment, monkeypatch
):
    client, members, _ = reservation_environment
    first_member = members[0]
    second_member = replace(
        first_member,
        username="member-kanok",
        student_id="STU-002",
        first_name="กนก",
    )
    third_member = replace(
        first_member,
        username="member-alice",
        student_id="STU-003",
        first_name="Alice",
    )
    members.extend([second_member, third_member])

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 11, 16, 15, 0, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(reservation_service, "datetime", FixedDateTime)
    second_client = TestClient(app)
    third_client = TestClient(app)
    second_client.post(
        "/api/auth/login",
        json={"username": second_member.username, "password": "pass1234"},
    )
    third_client.post(
        "/api/auth/login",
        json={"username": third_member.username, "password": "pass1234"},
    )

    kamol = _reserve(client, "tie-kamol")
    kanok = _reserve(second_client, "tie-kanok")
    alice = _reserve(third_client, "tie-alice")

    assert kamol.json()["queue_position"] == 1
    assert kanok.json()["queue_position"] == 1
    assert alice.json()["queue_position"] == 3


def test_AC_จองหนังสือ_02_2_uses_surname_and_member_code_as_final_tie_breakers():
    rows = [
        {
            "recorded_at": "2026-11-16T15:00:00+00:00",
            "first_name": "กนก",
            "last_name": "สุขใจ",
            "member_code": "STU-003",
        },
        {
            "recorded_at": "2026-11-16T15:00:00+00:00",
            "first_name": "กนก",
            "last_name": "ใจดี",
            "member_code": "STU-002",
        },
        {
            "recorded_at": "2026-11-16T15:00:00+00:00",
            "first_name": "กนก",
            "last_name": "ใจดี",
            "member_code": "STU-001",
        },
    ]

    ordered = sorted(rows, key=reservation_service._reservation_sort_key)

    assert [row["member_code"] for row in ordered] == [
        "STU-001",
        "STU-002",
        "STU-003",
    ]
    assert reservation_service._name_sort_key("เกียรติ") == reservation_service._name_sort_key(
        "กียรติ"
    )


@pytest.mark.parametrize(
    ("account_status", "overdue_count", "unpaid_fine_count", "expected"),
    [
        ("Suspended", 0, 0, ["บัญชีถูกระงับ"]),
        ("Active", 1, 0, ["มีหนังสือเกินกำหนด"]),
        ("Active", 0, 1, ["มีค่าปรับค้างชำระ"]),
        (
            "Suspended",
            1,
            1,
            ["บัญชีถูกระงับ", "มีหนังสือเกินกำหนด", "มีค่าปรับค้างชำระ"],
        ),
    ],
)
def test_AC_จองหนังสือ_03_1_rejects_ineligible_member_without_creating_record(
    reservation_environment,
    monkeypatch,
    account_status,
    overdue_count,
    unpaid_fine_count,
    expected,
):
    client, members, _ = reservation_environment
    members[0] = replace(
        members[0],
        account_status=account_status,
        overdue_count=overdue_count,
        unpaid_fine_count=unpaid_fine_count,
    )

    response = _reserve(client, f"request-ineligible-{account_status}-{overdue_count}-{unpaid_fine_count}")

    assert response.status_code == 403
    message = response.json()["message"]
    assert all(reason in message for reason in expected)
    assert [message.index(reason) for reason in expected] == sorted(
        message.index(reason) for reason in expected
    )
    assert reservation_service.list_reservations_for_testing() == []


@pytest.mark.parametrize("blocked_status", ["Lost", "Damaged", "อยู่ระหว่างซ่อม"])
def test_AC_จองหนังสือ_03_2_rejects_title_with_only_unreservable_copies(
    reservation_environment, blocked_status
):
    client, _, record = reservation_environment
    record.copies[0] = replace(record.copies[0], status=blocked_status)

    response = _reserve(client, f"request-{blocked_status}")

    assert response.status_code == 409
    assert response.json()["message"] == "หนังสือนี้ไม่พร้อมให้บริการ"
    assert reservation_service.list_reservations_for_testing() == []


def test_AC_จองหนังสือ_03_3_temporarily_rejects_available_copy(
    reservation_environment,
):
    client, _, record = reservation_environment
    record.copies[0] = replace(record.copies[0], status="Available")

    response = _reserve(client, "request-available")

    assert response.status_code == 409
    assert response.json()["message"] == "มีเล่มว่าง สามารถยืมได้ที่ห้องสมุด"
    assert reservation_service.list_reservations_for_testing() == []


def test_reservation_rejects_unknown_copy_status_explicitly(reservation_environment):
    client, _, record = reservation_environment
    record.copies[0] = replace(record.copies[0], status=None)

    response = _reserve(client, "request-unknown-status")

    assert response.status_code == 503
    assert response.json()["code"] == "book_status_unavailable"
    assert response.json()["message"] == "ไม่สามารถตรวจสอบสถานะหนังสือได้"
    assert reservation_service.list_reservations_for_testing() == []


def test_reservation_requires_authenticated_session(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRARY_RESERVATION_DB", str(tmp_path / "reservations.sqlite3"))
    client = TestClient(app)

    response = _reserve(client, "request-anonymous")

    assert response.status_code == 401
    assert response.json()["code"] == "authentication_required"
    assert reservation_service.list_reservations_for_testing() == []
