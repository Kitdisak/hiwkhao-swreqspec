from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta
from threading import Barrier
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from app.auth import session as auth_session
from app.auth.session import SESSION_COOKIE, create_session
from app import main as app_main
from app.main import app
from app.rooms import store as room_store
from app.rooms.booking import (
    BookingValidationError,
    RoomBookingConflict,
    create_room_booking,
    validate_booking_input,
)
from app.rooms.models import Room, RoomBooking

_BANGKOK = ZoneInfo("Asia/Bangkok")
_TODAY = date(2030, 1, 2)
_NOW = datetime(2030, 1, 2, 14, 10, tzinfo=_BANGKOK)
_ROOM = Room("ROOM-A", "ห้องอ่านหนังสือ", 6)


class _FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return _NOW.astimezone(tz) if tz is not None else _NOW.replace(tzinfo=None)


def _validate(
    booking_date: date = _TODAY,
    start_time: time = time(15, 0),
    end_time: time = time(15, 30),
    user_count: object = 1,
    room: Room = _ROOM,
) -> None:
    validate_booking_input(
        room=room,
        booking_date=booking_date,
        start_time=start_time,
        end_time=end_time,
        user_count=user_count,
        now=_NOW,
    )


def test_AC_จองห้องอ่านหนังสือ_ห้องประชุม_01_accepts_30_minute_and_4_hour_boundaries():
    _validate(
        booking_date=date(2030, 1, 3),
        start_time=time(8, 0),
        end_time=time(8, 30),
        user_count=6,
    )
    _validate(
        booking_date=date(2030, 1, 3),
        start_time=time(16, 0),
        end_time=time(20, 0),
        user_count=6,
    )


@pytest.mark.parametrize(
    (
        "booking_date",
        "start_time",
        "end_time",
        "expected_code",
        "expected_message",
    ),
    [
        (
            date(2030, 1, 1),
            time(15, 0),
            time(15, 30),
            "date_before_today",
            "กรุณาเลือกวันที่ตั้งแต่วันนี้เป็นต้นไป",
        ),
        (
            _TODAY,
            time(9, 10),
            time(10, 0),
            "invalid_booking_time",
            "เลือกเวลาได้ช่วงละ 30 นาที ระหว่าง 08:00–20:00",
        ),
        (
            _TODAY,
            time(19, 30),
            time(20, 30),
            "invalid_booking_time",
            "เลือกเวลาได้ช่วงละ 30 นาที ระหว่าง 08:00–20:00",
        ),
        (
            _TODAY,
            time(8, 0),
            time(13, 0),
            "booking_too_long",
            "จองได้ไม่เกิน 4 ชั่วโมง",
        ),
        (
            _TODAY,
            time(11, 0),
            time(10, 0),
            "invalid_time_order",
            "เวลาเริ่มต้องก่อนเวลาสิ้นสุด",
        ),
        (
            _TODAY,
            time(14, 0),
            time(14, 30),
            "booking_start_in_past",
            "ไม่สามารถจองช่วงเวลาที่ผ่านไปแล้ว",
        ),
    ],
)
def test_AC_จองห้องอ่านหนังสือ_ห้องประชุม_01_rejects_invalid_date_or_time(
    booking_date, start_time, end_time, expected_code, expected_message
):
    with pytest.raises(BookingValidationError) as error:
        _validate(
            booking_date=booking_date,
            start_time=start_time,
            end_time=end_time,
        )

    assert error.value.code == expected_code
    assert error.value.message == expected_message


@pytest.mark.parametrize("user_count", [0, -1, 2.5, "abc", None, True])
def test_AC_จองห้องอ่านหนังสือ_ห้องประชุม_01_rejects_non_positive_integer_count(
    user_count,
):
    with pytest.raises(BookingValidationError) as error:
        _validate(user_count=user_count)

    assert error.value.code == "invalid_user_count"
    assert error.value.message == "กรุณาระบุจำนวนผู้ใช้งานเป็นจำนวนเต็มตั้งแต่ 1 ขึ้นไป"


def test_AC_จองห้องอ่านหนังสือ_ห้องประชุม_01_rejects_count_over_capacity():
    with pytest.raises(BookingValidationError) as error:
        _validate(user_count=7)

    assert error.value.code == "user_count_exceeds_capacity"
    assert error.value.message == "ห้องนี้รองรับได้สูงสุด 6 คน"


def test_AC_จองห้องอ่านหนังสือ_ห้องประชุม_01_rejects_room_without_capacity():
    room = Room("ROOM-UNKNOWN", "ห้องอ่านหนังสือ", None)

    with pytest.raises(BookingValidationError) as error:
        _validate(room=room)

    assert error.value.code == "room_capacity_unavailable"


def test_AC_จองห้องอ่านหนังสือ_ห้องประชุม_01_confirmation_rejects_invalid_date_and_time(
    monkeypatch, room_store_data
):
    _, bookings = room_store_data
    monkeypatch.setattr(app_main, "datetime", _FixedDateTime)
    client = _authenticated_client()
    invalid_cases = [
        (
            {"booking_date": date(2030, 1, 1).isoformat()},
            "date_before_today",
            "กรุณาเลือกวันที่ตั้งแต่วันนี้เป็นต้นไป",
        ),
        (
            {"start_time": "09:10"},
            "invalid_booking_time",
            "เลือกเวลาได้ช่วงละ 30 นาที ระหว่าง 08:00–20:00",
        ),
        (
            {"start_time": "19:30", "end_time": "20:30"},
            "invalid_booking_time",
            "เลือกเวลาได้ช่วงละ 30 นาที ระหว่าง 08:00–20:00",
        ),
        (
            {"start_time": "08:00", "end_time": "13:00"},
            "booking_too_long",
            "จองได้ไม่เกิน 4 ชั่วโมง",
        ),
        (
            {"start_time": "11:00", "end_time": "10:00"},
            "invalid_time_order",
            "เวลาเริ่มต้องก่อนเวลาสิ้นสุด",
        ),
        (
            {
                "booking_date": _TODAY.isoformat(),
                "start_time": "14:00",
                "end_time": "14:30",
            },
            "booking_start_in_past",
            "ไม่สามารถจองช่วงเวลาที่ผ่านไปแล้ว",
        ),
    ]

    for request_number, (overrides, expected_code, expected_message) in enumerate(
        invalid_cases
    ):
        payload = _check_payload(
            **{
                "booking_date": date(2030, 1, 3).isoformat(),
                **overrides,
                "request_id": f"invalid-date-time-{request_number}",
            }
        )
        response = client.post("/api/room-reservations", json=payload)

        assert response.status_code == 422
        assert response.json()["code"] == expected_code
        assert response.json()["message"] == expected_message

    assert bookings == []


@pytest.mark.parametrize(
    ("user_count", "omit_count", "expected_code", "expected_message"),
    [
        (
            0,
            False,
            "invalid_user_count",
            "กรุณาระบุจำนวนผู้ใช้งานเป็นจำนวนเต็มตั้งแต่ 1 ขึ้นไป",
        ),
        (
            -1,
            False,
            "invalid_user_count",
            "กรุณาระบุจำนวนผู้ใช้งานเป็นจำนวนเต็มตั้งแต่ 1 ขึ้นไป",
        ),
        (
            2.5,
            False,
            "invalid_user_count",
            "กรุณาระบุจำนวนผู้ใช้งานเป็นจำนวนเต็มตั้งแต่ 1 ขึ้นไป",
        ),
        (
            "abc",
            False,
            "invalid_user_count",
            "กรุณาระบุจำนวนผู้ใช้งานเป็นจำนวนเต็มตั้งแต่ 1 ขึ้นไป",
        ),
        (
            None,
            True,
            "invalid_user_count",
            "กรุณาระบุจำนวนผู้ใช้งานเป็นจำนวนเต็มตั้งแต่ 1 ขึ้นไป",
        ),
        (7, False, "user_count_exceeds_capacity", "ห้องนี้รองรับได้สูงสุด 6 คน"),
    ],
)
def test_AC_จองห้องอ่านหนังสือ_ห้องประชุม_01_confirmation_rejects_invalid_user_count(
    room_store_data,
    user_count,
    omit_count,
    expected_code,
    expected_message,
):
    _, bookings = room_store_data
    payload = _check_payload(request_id=f"invalid-user-count-{user_count}")
    if omit_count:
        payload.pop("user_count")
    else:
        payload["user_count"] = user_count

    response = _authenticated_client().post("/api/room-reservations", json=payload)

    assert response.status_code == 422
    assert response.json()["code"] == expected_code
    assert response.json()["message"] == expected_message
    assert bookings == []


def test_AC_จองห้องอ่านหนังสือ_ห้องประชุม_01_confirmation_rejects_room_without_capacity(
    monkeypatch, room_store_data
):
    _, bookings = room_store_data
    monkeypatch.setattr(
        room_store,
        "ROOMS",
        [Room("ROOM-UNKNOWN", "ห้องอ่านหนังสือ", None)],
    )

    response = _authenticated_client().post(
        "/api/room-reservations",
        json=_check_payload(
            room_id="ROOM-UNKNOWN",
            request_id="room-without-capacity",
        ),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "room_capacity_unavailable"
    assert bookings == []


@pytest.mark.parametrize(
    ("start_time", "end_time"),
    [("08:00", "08:30"), ("16:00", "20:00")],
)
def test_AC_จองห้องอ่านหนังสือ_ห้องประชุม_01_confirmation_accepts_duration_boundaries(
    monkeypatch, room_store_data, start_time, end_time
):
    room, bookings = room_store_data
    monkeypatch.setattr(app_main, "datetime", _FixedDateTime)
    payload = _check_payload(
        booking_date=date(2030, 1, 3).isoformat(),
        start_time=start_time,
        end_time=end_time,
        user_count=6,
        request_id=f"boundary-{start_time}-{end_time}",
    )

    response = _authenticated_client().post("/api/room-reservations", json=payload)

    assert response.status_code == 200
    assert response.json()["booking"]["room_id"] == room.room_id
    assert response.json()["booking"]["user_count"] == 6
    assert len(bookings) == 1


@pytest.fixture
def room_store_data(monkeypatch):
    rooms = [Room("ROOM-A", "ห้องอ่านหนังสือ", 6)]
    bookings: list[RoomBooking] = []
    monkeypatch.setattr(room_store, "ROOMS", rooms)
    monkeypatch.setattr(room_store, "ROOM_BOOKINGS", bookings)
    return rooms[0], bookings


def _check_payload(**overrides):
    payload = {
        "room_id": "ROOM-A",
        "booking_date": (datetime.now(_BANGKOK).date() + timedelta(days=1)).isoformat(),
        "start_time": "09:00",
        "end_time": "10:00",
        "user_count": 2,
    }
    return {**payload, **overrides}


def _authenticated_client() -> TestClient:
    client = TestClient(app)
    client.cookies.set(SESSION_COOKIE, create_session("s12345"))
    return client


def _create_room_booking(
    room, booking_date, start_time, end_time, request_id, now=None
):
    return create_room_booking(
        room=room,
        booking_date=booking_date,
        start_time=start_time,
        end_time=end_time,
        user_count=2,
        member_id="member-A",
        request_id=request_id,
        now=now or datetime.now(_BANGKOK),
    )


def _assert_no_overlapping_bookings(bookings):
    for index, first in enumerate(bookings):
        for second in bookings[index + 1 :]:
            if first.room_id == second.room_id:
                assert not (
                    first.booking_date == second.booking_date
                    and first.start_time < second.end_time
                    and first.end_time > second.start_time
                )


def test_AC_จองห้องอ่านหนังสือ_ห้องประชุม_01_02_requires_session_before_room_lookup(
    monkeypatch,
):
    monkeypatch.setattr(
        room_store,
        "get_rooms",
        lambda: pytest.fail("Room lookup must not run without an authenticated session"),
    )
    client = TestClient(app)

    response = client.post(
        "/api/room-reservations/check",
        content="{",
    )

    assert response.status_code == 401
    assert response.json() == {
        "available": False,
        "code": "authentication_required",
        "message": "กรุณาเข้าสู่ระบบก่อนจองห้อง",
    }


def test_AC_จองห้องอ่านหนังสือ_ห้องประชุม_01_02_expired_session_is_unauthorized(
    monkeypatch,
):
    token = "expired-test-session"
    monkeypatch.setitem(auth_session._sessions, token, ("s12345", 0.0))
    monkeypatch.setattr(
        room_store,
        "get_rooms",
        lambda: pytest.fail("Room lookup must not run with an expired session"),
    )
    client = TestClient(app)
    client.cookies.set(SESSION_COOKIE, token)

    response = client.post(
        "/api/room-reservations/check",
        json=_check_payload(),
    )

    assert response.status_code == 401
    assert response.json()["code"] == "authentication_required"


def test_AC_จองห้องอ่านหนังสือ_ห้องประชุม_01_02_invalid_count_fails_before_availability(
    monkeypatch, room_store_data
):
    monkeypatch.setattr(
        room_store,
        "get_room_bookings",
        lambda: pytest.fail("Availability must not be checked for invalid input"),
    )
    client = _authenticated_client()

    response = client.post(
        "/api/room-reservations/check",
        json=_check_payload(user_count=2.5),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_user_count"
    assert response.json()["message"] == (
        "กรุณาระบุจำนวนผู้ใช้งานเป็นจำนวนเต็มตั้งแต่ 1 ขึ้นไป"
    )


def test_AC_จองห้องอ่านหนังสือ_ห้องประชุม_03_check_shows_summary_without_creating_booking(
    room_store_data,
):
    room, bookings = room_store_data
    client = _authenticated_client()
    payload = _check_payload(member_id="member-B")

    response = client.post(
        "/api/room-reservations/check",
        json=payload,
    )

    assert response.status_code == 200
    assert response.json() == {
        "available": True,
        "message": None,
        "summary": {
            "room_id": room.room_id,
            "room_type": room.room_type,
            "booking_date": payload["booking_date"],
            "start_time": "09:00",
            "end_time": "10:00",
            "user_count": 2,
        },
    }
    assert bookings == []
    payload["request_id"] = "check-then-confirm"

    confirm_response = client.post("/api/room-reservations", json=payload)

    assert confirm_response.status_code == 200
    assert confirm_response.json()["booking"]["room_id"] == room.room_id
    assert len(bookings) == 1


def test_AC_จองห้องอ่านหนังสือ_ห้องประชุม_03_check_returns_remaining_slots(
    room_store_data,
):
    room, bookings = room_store_data
    booking_date = datetime.now(_BANGKOK).date() + timedelta(days=1)
    bookings.append(
        RoomBooking(
            booking_id="EXISTING",
            room_id=room.room_id,
            booking_date=booking_date,
            start_time=time(9, 30),
            end_time=time(10, 0),
        )
    )
    client = _authenticated_client()

    response = client.post(
        "/api/room-reservations/check",
        json=_check_payload(),
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload["available"] is False
    assert payload["message"] == "ช่วงเวลานี้ไม่ว่าง กรุณาเลือกเวลาใหม่"
    assert {
        "start_time": "09:00",
        "end_time": "09:30",
    } in payload["available_slots"]
    assert not any(
        slot["start_time"] == "09:30" for slot in payload["available_slots"]
    )
    assert len(bookings) == 1


def test_AC_จองห้องอ่านหนังสือ_ห้องประชุม_03_check_reports_no_remaining_slots(
    room_store_data,
):
    room, bookings = room_store_data
    booking_date = datetime.now(_BANGKOK).date() + timedelta(days=1)
    bookings.append(
        RoomBooking(
            booking_id="FULL-DAY",
            room_id=room.room_id,
            booking_date=booking_date,
            start_time=time(8, 0),
            end_time=time(20, 0),
        )
    )
    client = _authenticated_client()

    response = client.post(
        "/api/room-reservations/check",
        json=_check_payload(),
    )

    assert response.status_code == 200
    assert response.json() == {
        "available": False,
        "message": "ห้องนี้ไม่มีช่วงว่างในวันที่เลือก",
        "available_slots": [],
    }
    assert len(bookings) == 1


def test_AC_จองห้องอ่านหนังสือ_ห้องประชุม_01_confirm_requires_session_before_room_lookup(
    monkeypatch,
):
    monkeypatch.setattr(
        room_store,
        "get_rooms",
        lambda: pytest.fail("Room lookup must not run without an authenticated session"),
    )
    client = TestClient(app)

    response = client.post(
        "/api/room-reservations",
        content="{",
    )

    assert response.status_code == 401
    assert response.json()["code"] == "authentication_required"


def test_AC_จองห้องอ่านหนังสือ_ห้องประชุม_01_confirm_rejects_expired_session(
    monkeypatch,
):
    token = "expired-confirm-session"
    monkeypatch.setitem(auth_session._sessions, token, ("s12345", 0.0))
    monkeypatch.setattr(
        room_store,
        "get_rooms",
        lambda: pytest.fail("Room lookup must not run with an expired session"),
    )
    client = TestClient(app)
    client.cookies.set(SESSION_COOKIE, token)

    response = client.post(
        "/api/room-reservations",
        json={**_check_payload(), "request_id": "expired-confirm"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "authentication_required"


def test_AC_จองห้องอ่านหนังสือ_ห้องประชุม_01_confirm_uses_session_member_and_creates_booking(
    room_store_data,
):
    room, bookings = room_store_data
    client = _authenticated_client()
    payload = _check_payload(member_id="member-B", user_count=6)
    payload["request_id"] = "confirm-request-1"

    response = client.post("/api/room-reservations", json=payload)

    assert response.status_code == 200
    result = response.json()
    member = auth_session.get_session_user(client.cookies.get(SESSION_COOKIE))
    assert member is not None
    assert result["success"] is True
    assert result["booking"] == {
        "booking_id": bookings[0].booking_id,
        "room_id": room.room_id,
        "booking_date": payload["booking_date"],
        "start_time": "09:00",
        "end_time": "10:00",
        "request_id": "confirm-request-1",
        "member_id": member.student_id or member.username,
        "user_count": 6,
    }
    assert len(bookings) == 1
    assert bookings[0].member_id != "member-B"


def test_AC_จองห้องอ่านหนังสือ_ห้องประชุม_01_confirm_retry_returns_existing_booking(
    room_store_data,
):
    _, bookings = room_store_data
    client = _authenticated_client()
    payload = _check_payload()
    payload["request_id"] = "confirm-request-retry"

    first_response = client.post("/api/room-reservations", json=payload)
    retry_response = client.post("/api/room-reservations", json=payload)

    assert first_response.status_code == 200
    assert retry_response.status_code == 200
    assert retry_response.json()["booking"] == first_response.json()["booking"]
    assert len(bookings) == 1


def test_AC_จองห้องอ่านหนังสือ_ห้องประชุม_02_04_and_03_04_confirm_rejects_slot_taken_after_available_check(
    room_store_data,
):
    room, bookings = room_store_data
    booking_date = datetime.now(_BANGKOK).date() + timedelta(days=1)
    client = _authenticated_client()
    payload = _check_payload()

    check_response = client.post("/api/room-reservations/check", json=payload)

    assert check_response.status_code == 200
    assert check_response.json()["available"] is True
    assert bookings == []
    bookings.append(
        RoomBooking(
            booking_id="COMPETING-BOOKING",
            room_id=room.room_id,
            booking_date=booking_date,
            start_time=time(9, 0),
            end_time=time(10, 0),
        )
    )
    payload["request_id"] = "confirm-conflict"

    response = client.post("/api/room-reservations", json=payload)

    assert response.status_code == 409
    assert response.json()["code"] == "room_unavailable"
    assert response.json()["message"] == "ช่วงเวลานี้ไม่ว่าง กรุณาเลือกเวลาใหม่"
    assert {
        "start_time": "08:00",
        "end_time": "08:30",
    } in response.json()["available_slots"]
    assert not any(
        slot["start_time"] == "09:00"
        for slot in response.json()["available_slots"]
    )
    assert len(bookings) == 1
    _assert_no_overlapping_bookings(bookings)


def test_AC_จองห้องอ่านหนังสือ_ห้องประชุม_03_confirm_reports_no_remaining_slots(
    room_store_data,
):
    room, bookings = room_store_data
    booking_date = datetime.now(_BANGKOK).date() + timedelta(days=1)
    bookings.append(
        RoomBooking(
            booking_id="FULL-DAY",
            room_id=room.room_id,
            booking_date=booking_date,
            start_time=time(8, 0),
            end_time=time(20, 0),
        )
    )
    client = _authenticated_client()
    payload = _check_payload(request_id="confirm-no-slots")

    response = client.post("/api/room-reservations", json=payload)

    assert response.status_code == 409
    assert response.json() == {
        "success": False,
        "available": False,
        "code": "room_unavailable",
        "message": "ห้องนี้ไม่มีช่วงว่างในวันที่เลือก",
        "available_slots": [],
    }
    assert len(bookings) == 1


def test_AC_จองห้องอ่านหนังสือ_ห้องประชุม_02_same_slot_requests_are_atomic(
    room_store_data,
):
    room, bookings = room_store_data
    booking_date = date(2030, 1, 3)
    with ThreadPoolExecutor(max_workers=10) as executor:
        for round_number in range(20):
            bookings.clear()
            barrier = Barrier(10)

            def submit(request_number: int) -> str | tuple[str, str]:
                barrier.wait()
                try:
                    _create_room_booking(
                        room,
                        booking_date,
                        time(9, 0),
                        time(10, 0),
                        f"request-{round_number}-{request_number}",
                        now=_NOW,
                    )
                except RoomBookingConflict as error:
                    return error.code, error.message
                return "created"

            results = list(executor.map(submit, range(10)))

            assert results.count("created") == 1
            assert results.count(
                ("room_unavailable", "ช่วงเวลานี้ไม่ว่าง กรุณาเลือกเวลาใหม่")
            ) == 9
            assert len(bookings) == results.count("created")
            _assert_no_overlapping_bookings(bookings)


def test_AC_จองห้องอ่านหนังสือ_ห้องประชุม_02_partial_overlaps_have_one_winner(
    room_store_data,
):
    room, bookings = room_store_data
    booking_date = date(2030, 1, 3)
    barrier = Barrier(2)
    requests = [
        (time(9, 0), time(10, 0), "partial-first"),
        (time(9, 30), time(10, 30), "partial-second"),
    ]

    def submit(request):
        start_time, end_time, request_id = request
        barrier.wait()
        try:
            _create_room_booking(
                room,
                booking_date,
                start_time,
                end_time,
                request_id,
                now=_NOW,
            )
        except RoomBookingConflict as error:
            return error.code, error.message
        return "created"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(submit, requests))

    assert results.count("created") == 1
    assert results.count(
        ("room_unavailable", "ช่วงเวลานี้ไม่ว่าง กรุณาเลือกเวลาใหม่")
    ) == 1
    assert len(bookings) == 1
    _assert_no_overlapping_bookings(bookings)


def test_AC_จองห้องอ่านหนังสือ_ห้องประชุม_02_adjacent_concurrent_requests_both_succeed(
    room_store_data,
):
    room, bookings = room_store_data
    booking_date = date(2030, 1, 3)
    barrier = Barrier(2)
    requests = [
        (time(9, 0), time(10, 0), "adjacent-first"),
        (time(10, 0), time(11, 0), "adjacent-second"),
    ]

    def submit(request):
        start_time, end_time, request_id = request
        barrier.wait()
        _create_room_booking(
            room,
            booking_date,
            start_time,
            end_time,
            request_id,
            now=_NOW,
        )
        return "created"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(submit, requests))

    assert results == ["created", "created"]
    assert len(bookings) == len(results)
    _assert_no_overlapping_bookings(bookings)


def test_AC_จองห้องอ่านหนังสือ_ห้องประชุม_02_adjacent_bookings_and_idempotent_retry(
    room_store_data,
):
    room, bookings = room_store_data
    booking_date = datetime.now(_BANGKOK).date() + timedelta(days=1)

    first = _create_room_booking(
        room, booking_date, time(9, 0), time(10, 0), "request-first"
    )
    retry = create_room_booking(
        room=room,
        booking_date=booking_date,
        start_time=time(9, 0),
        end_time=time(10, 0),
        user_count=2,
        member_id="member-A",
        request_id="request-first",
        now=datetime(
            booking_date.year,
            booking_date.month,
            booking_date.day,
            9,
            15,
            tzinfo=_BANGKOK,
        ),
    )
    adjacent = _create_room_booking(
        room, booking_date, time(10, 0), time(11, 0), "request-adjacent"
    )

    assert retry is first
    assert adjacent.start_time == time(10, 0)
    assert len(bookings) == 2