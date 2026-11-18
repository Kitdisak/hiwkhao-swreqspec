from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app import main as app_main
from app.auth.session import SESSION_COOKIE, create_session
from app.main import app
from app.rooms import availability as room_availability
from app.rooms import store as room_store
from app.rooms.booking import create_room_booking
from app.rooms.models import Room, RoomBooking


_BANGKOK = ZoneInfo("Asia/Bangkok")
_ROOM = Room("ROOM-A", "ห้องอ่านหนังสือ", 6)


class _FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        fixed = datetime(2030, 1, 2, 10, 0, tzinfo=_BANGKOK)
        return fixed.astimezone(tz) if tz is not None else fixed.replace(tzinfo=None)


def _client(monkeypatch):
    monkeypatch.setattr(app_main, "datetime", _FixedDateTime)
    client = TestClient(app)
    client.cookies.set(SESSION_COOKIE, create_session("s12345"))
    return client


def test_T01_cancelled_booking_is_kept_with_cancelled_status(monkeypatch):
    bookings = [
        RoomBooking(
            booking_id="BK-1",
            room_id="ROOM-A",
            booking_date=date(2030, 1, 2),
            start_time=time(11, 0),
            end_time=time(12, 0),
            member_id="STU-001",
        )
    ]
    monkeypatch.setattr(room_store, "ROOM_BOOKINGS", bookings)
    client = _client(monkeypatch)

    response = client.post("/api/me/room-reservations/BK-1/cancel")

    assert response.status_code == 200
    assert response.json()["booking"]["status"] == "ยกเลิกแล้ว"
    assert len(bookings) == 1
    assert bookings[0].booking_id == "BK-1"


def test_T02_list_and_detail_use_session_and_do_not_change_data(monkeypatch):
    bookings = [
        RoomBooking(
            booking_id="BK-1",
            room_id="ROOM-A",
            booking_date=date(2030, 1, 2),
            start_time=time(11, 0),
            end_time=time(12, 0),
            member_id="STU-001",
        ),
        RoomBooking(
            booking_id="BK-2",
            room_id="ROOM-A",
            booking_date=date(2030, 1, 2),
            start_time=time(12, 0),
            end_time=time(13, 0),
            member_id="other",
        ),
    ]
    monkeypatch.setattr(room_store, "ROOM_BOOKINGS", bookings)
    client = _client(monkeypatch)

    list_response = client.get("/api/me/room-reservations")
    detail_response = client.get("/api/me/room-reservations/BK-1")

    assert list_response.status_code == 200
    assert [item["booking_id"] for item in list_response.json()["bookings"]] == ["BK-1"]
    assert detail_response.status_code == 200
    assert detail_response.json()["booking"]["booking_id"] == "BK-1"
    assert list(bookings) == bookings


def test_T03_cancel_and_list_return_401_without_session(monkeypatch):
    monkeypatch.setattr(room_store, "ROOM_BOOKINGS", [])
    client = TestClient(app)

    list_response = client.get("/api/me/room-reservations")
    cancel_response = client.post("/api/me/room-reservations/BK-1/cancel")

    assert list_response.status_code == 401
    assert cancel_response.status_code == 401


def test_T04_exact_start_and_after_start_are_not_cancellable(monkeypatch):
    bookings = [
            RoomBooking(
                booking_id="BK-EXACT",
                room_id="ROOM-A",
                booking_date=date(2030, 1, 2),
                start_time=time(10, 0),
                end_time=time(11, 0),
                member_id="STU-001",
            ),
            RoomBooking(
                booking_id="BK-PAST",
                room_id="ROOM-A",
                booking_date=date(2030, 1, 2),
                start_time=time(9, 0),
                end_time=time(10, 0),
                member_id="STU-001",
            ),
        ]
    monkeypatch.setattr(room_store, "ROOM_BOOKINGS", bookings)
    client = _client(monkeypatch)

    exact = client.post("/api/me/room-reservations/BK-EXACT/cancel")
    past = client.post("/api/me/room-reservations/BK-PAST/cancel")

    assert exact.status_code == 409
    assert exact.json()["message"] == "ไม่สามารถยกเลิกได้"
    assert past.status_code == 409
    assert past.json()["message"] == "ไม่สามารถยกเลิกได้"
    assert all(booking.status == "จองแล้ว" for booking in bookings)


def test_T05_repeat_cancel_and_cancelled_booking_not_in_availability_or_overlap(monkeypatch):
    room_store_data = [
        RoomBooking(
            booking_id="BK-1",
            room_id="ROOM-A",
            booking_date=date(2030, 1, 2),
            start_time=time(11, 0),
            end_time=time(12, 0),
            member_id="STU-001",
        )
    ]
    monkeypatch.setattr(room_store, "ROOMS", [_ROOM])
    monkeypatch.setattr(room_store, "ROOM_BOOKINGS", room_store_data)
    client = _client(monkeypatch)

    first = client.post("/api/me/room-reservations/BK-1/cancel")
    second = client.post("/api/me/room-reservations/BK-1/cancel")

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["outcome"] == "already_cancelled"
    assert second.json()["message"] == "ยกเลิกแล้ว"
    assert len(room_store_data) == 1

    available = room_availability.calculate_availability(
        rooms=[_ROOM],
        bookings=room_store_data,
        selected_date=date(2030, 1, 2),
        room_type="ห้องอ่านหนังสือ",
        user_count=None,
        now=datetime(2030, 1, 2, 10, 0, tzinfo=_BANGKOK),
    )
    slots = available[0].available_slots
    assert any(slot.start_time == time(11, 0) for slot in slots)

    booking = create_room_booking(
        room=_ROOM,
        booking_date=date(2030, 1, 2),
        start_time=time(11, 0),
        end_time=time(12, 0),
        user_count=2,
        member_id="member-new",
        request_id="new-after-cancel",
        now=datetime(2030, 1, 2, 10, 0, tzinfo=_BANGKOK),
    )
    assert booking.member_id == "member-new"


def test_T06_repeat_cancel_after_start_stays_already_cancelled(monkeypatch):
    bookings = [
        RoomBooking(
            booking_id="BK-CANCELLED",
            room_id="ROOM-A",
            booking_date=date(2030, 1, 2),
            start_time=time(9, 0),
            end_time=time(10, 0),
            member_id="STU-001",
            status="ยกเลิกแล้ว",
        )
    ]
    monkeypatch.setattr(room_store, "ROOM_BOOKINGS", bookings)
    client = _client(monkeypatch)

    response = client.post(
        "/api/me/room-reservations/BK-CANCELLED/cancel",
        json={"member_id": "ATTACKER-ID"},
    )

    assert response.status_code == 200
    assert response.json()["outcome"] == "already_cancelled"
    assert response.json()["message"] == "ยกเลิกแล้ว"
    assert len(bookings) == 1
    assert bookings[0].status == "ยกเลิกแล้ว"


def test_T06_other_or_missing_booking_returns_same_non_disclosing_error(monkeypatch):
    bookings = [
        RoomBooking(
            booking_id="BK-OTHER",
            room_id="ROOM-A",
            booking_date=date(2030, 1, 2),
            start_time=time(11, 0),
            end_time=time(12, 0),
            member_id="OTHER-001",
        )
    ]
    monkeypatch.setattr(room_store, "ROOM_BOOKINGS", bookings)
    client = _client(monkeypatch)

    other = client.post("/api/me/room-reservations/BK-OTHER/cancel")
    missing = client.post("/api/me/room-reservations/BK-MISSING/cancel")

    for response in (other, missing):
        assert response.status_code == 409
        assert response.json()["success"] is False
        assert response.json()["code"] == "cancellation_not_allowed"
        assert response.json()["message"] == "ไม่สามารถยกเลิกได้"

    assert list(bookings) == bookings


def test_AC_ติดตามยกเลิกห้อง_010_01_success_is_immediate_for_availability_and_booking(monkeypatch):
    bookings = [
        RoomBooking(
            booking_id="AC-01",
            room_id="ROOM-A",
            booking_date=date(2030, 1, 2),
            start_time=time(11, 0),
            end_time=time(12, 0),
            member_id="STU-001",
        )
    ]
    monkeypatch.setattr(room_store, "ROOMS", [_ROOM])
    monkeypatch.setattr(room_store, "ROOM_BOOKINGS", bookings)
    client = _client(monkeypatch)

    cancelled = client.post("/api/me/room-reservations/AC-01/cancel")

    assert cancelled.status_code == 200
    assert cancelled.json()["outcome"] == "cancelled"
    assert cancelled.json()["booking"]["status"] == "ยกเลิกแล้ว"
    assert len(bookings) == 1
    assert bookings[0].booking_id == "AC-01"
    assert bookings[0].status == "ยกเลิกแล้ว"

    repeat = client.post("/api/me/room-reservations/AC-01/cancel")
    assert repeat.status_code == 200
    assert repeat.json()["outcome"] == "already_cancelled"
    assert repeat.json()["message"] == "ยกเลิกแล้ว"
    assert len(bookings) == 1
    assert bookings[0].status == "ยกเลิกแล้ว"

    available = room_availability.calculate_availability(
        rooms=[_ROOM],
        bookings=room_store.get_room_bookings(),
        selected_date=date(2030, 1, 2),
        room_type="ห้องอ่านหนังสือ",
        user_count=None,
        now=datetime(2030, 1, 2, 10, 0, tzinfo=_BANGKOK),
    )
    assert any(slot.start_time == time(11, 0) for slot in available[0].available_slots)

    booking = create_room_booking(
        room=_ROOM,
        booking_date=date(2030, 1, 2),
        start_time=time(11, 0),
        end_time=time(12, 0),
        user_count=2,
        member_id="STU-002",
        request_id="AC-01-new-booking",
        now=datetime(2030, 1, 2, 10, 0, tzinfo=_BANGKOK),
    )
    assert booking.member_id == "STU-002"


def test_AC_ติดตามยกเลิกห้อง_010_02_rejects_at_and_after_start(monkeypatch):
    bookings = [
        RoomBooking(
            booking_id="AC-02-EXACT",
            room_id="ROOM-A",
            booking_date=date(2030, 1, 2),
            start_time=time(10, 0),
            end_time=time(11, 0),
            member_id="STU-001",
        ),
        RoomBooking(
            booking_id="AC-02-AFTER",
            room_id="ROOM-A",
            booking_date=date(2030, 1, 2),
            start_time=time(9, 0),
            end_time=time(10, 0),
            member_id="STU-001",
        ),
    ]
    monkeypatch.setattr(room_store, "ROOM_BOOKINGS", bookings)
    client = _client(monkeypatch)

    for booking_id in ("AC-02-EXACT", "AC-02-AFTER"):
        response = client.post(f"/api/me/room-reservations/{booking_id}/cancel")
        assert response.status_code == 409
        assert response.json()["message"] == "ไม่สามารถยกเลิกได้"
    assert all(booking.status == "จองแล้ว" for booking in bookings)


def test_AC_ติดตามยกเลิกห้อง_010_03_view_is_read_only_and_cancelled_has_no_cancel_action(monkeypatch):
    cancelled = RoomBooking(
        booking_id="AC-03",
        room_id="ROOM-A",
        booking_date=date(2030, 1, 2),
        start_time=time(11, 0),
        end_time=time(12, 0),
        member_id="STU-001",
        status="ยกเลิกแล้ว",
    )
    other = RoomBooking(
        booking_id="AC-03-OTHER",
        room_id="ROOM-A",
        booking_date=date(2030, 1, 2),
        start_time=time(12, 0),
        end_time=time(13, 0),
        member_id="OTHER-001",
    )
    bookings = [cancelled, other]
    monkeypatch.setattr(room_store, "ROOM_BOOKINGS", bookings)
    client = _client(monkeypatch)

    detail = client.get("/api/me/room-reservations/AC-03")
    list_response = client.get("/api/me/room-reservations")
    other_detail = client.get("/api/me/room-reservations/AC-03-OTHER")
    missing_detail = client.get("/api/me/room-reservations/AC-03-MISSING")

    assert detail.status_code == 200
    assert detail.json()["booking"]["status"] == "ยกเลิกแล้ว"
    assert [item["booking_id"] for item in list_response.json()["bookings"]] == ["AC-03"]
    assert other_detail.status_code == 404
    assert missing_detail.status_code == 404
    assert bookings == [cancelled, other]


def test_AC_ติดตามยกเลิกห้อง_010_03_view_requires_session(monkeypatch):
    monkeypatch.setattr(room_store, "ROOM_BOOKINGS", [])
    client = TestClient(app)

    list_response = client.get("/api/me/room-reservations")
    detail_response = client.get("/api/me/room-reservations/AC-03")
    cancel_response = client.post("/api/me/room-reservations/AC-03/cancel")

    assert list_response.status_code == 401
    assert detail_response.status_code == 401
    assert cancel_response.status_code == 401
