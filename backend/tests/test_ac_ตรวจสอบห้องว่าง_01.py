from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.main import app
from app.rooms import store
from app.rooms.availability import InvalidSearchDate, calculate_availability
from app.rooms.config import AvailabilityConfig, load_availability_config
from app.rooms.models import Room, RoomBooking

client = TestClient(app)
BANGKOK = ZoneInfo("Asia/Bangkok")


def test_AC_ตรวจสอบห้องว่าง_01_แสดงช่วงว่างและซ่อนห้องที่ถูกจองเต็ม():
    selected_date = date(2030, 1, 2)
    rooms = [
        Room("ROOM-A", "ห้องอ่านหนังสือ", 6),
        Room("ROOM-B", "ห้องอ่านหนังสือ", 8),
    ]
    bookings = [
        RoomBooking("BOOKING-A", "ROOM-A", selected_date, time(8), time(12)),
        RoomBooking("BOOKING-B", "ROOM-B", selected_date, time(8), time(20)),
    ]

    results = calculate_availability(
        rooms=rooms,
        bookings=bookings,
        selected_date=selected_date,
        room_type="ห้องอ่านหนังสือ",
        user_count=None,
        now=datetime(2030, 1, 2, 7, 0, tzinfo=BANGKOK),
    )

    assert [room.room_id for room in results] == ["ROOM-A"]
    assert results[0].available_slots[0].start_time == time(12)
    assert results[0].available_slots[-1].end_time == time(20)
    assert len(results[0].available_slots) == 16
    expected_starts = [
        time(hour, minute)
        for hour in range(12, 20)
        for minute in (0, 30)
    ]
    assert [slot.start_time for slot in results[0].available_slots] == expected_starts
    assert all(
        (slot.end_time.hour * 60 + slot.end_time.minute)
        - (slot.start_time.hour * 60 + slot.start_time.minute)
        == 30
        for slot in results[0].available_slots
    )


def test_AC_ตรวจสอบห้องว่าง_01_ตัดช่วงที่เริ่มผ่านไปแล้วและช่วงจองที่ทับบางส่วน():
    selected_date = date(2030, 1, 2)
    rooms = [Room("ROOM-A", "ห้องอ่านหนังสือ", 6)]
    bookings = [
        RoomBooking("BOOKING-PARTIAL", "ROOM-A", selected_date, time(9, 10), time(9, 15))
    ]

    results = calculate_availability(
        rooms=rooms,
        bookings=bookings,
        selected_date=selected_date,
        room_type="ห้องอ่านหนังสือ",
        user_count=None,
        now=datetime(2030, 1, 2, 7, 0, tzinfo=BANGKOK),
    )

    starts = [slot.start_time for slot in results[0].available_slots]
    assert time(9, 0) not in starts
    assert time(9, 30) in starts

    today_results = calculate_availability(
        rooms=rooms,
        bookings=bookings,
        selected_date=selected_date,
        room_type="ห้องอ่านหนังสือ",
        user_count=None,
        now=datetime(2030, 1, 2, 14, 10, tzinfo=BANGKOK),
    )
    today_starts = [slot.start_time for slot in today_results[0].available_slots]
    assert time(14, 0) not in today_starts
    assert time(14, 30) in today_starts
    assert all(start >= time(14, 10) for start in today_starts)


def test_AC_ตรวจสอบห้องว่าง_01_ใช้ค่ากำหนดช่วงเวลาที่ส่งเข้ามา():
    selected_date = date(2030, 1, 2)

    results = calculate_availability(
        rooms=[Room("ROOM-A", "ห้องอ่านหนังสือ", 6)],
        bookings=[],
        selected_date=selected_date,
        room_type="ห้องอ่านหนังสือ",
        user_count=None,
        now=datetime(2030, 1, 2, 8, 0, tzinfo=BANGKOK),
        config=AvailabilityConfig(
            opening_time=time(9, 0),
            closing_time=time(10, 0),
            slot_minutes=30,
        ),
    )

    assert [slot.start_time for slot in results[0].available_slots] == [
        time(9, 0),
        time(9, 30),
    ]


def test_AC_ตรวจสอบห้องว่าง_01_อ่านเวลาเปิดปิดและหน่วยจากค่ากำหนดระบบ(monkeypatch):
    monkeypatch.setenv("ROOMS_OPENING_TIME", "09:30")
    monkeypatch.setenv("ROOMS_CLOSING_TIME", "11:00")
    monkeypatch.setenv("ROOMS_SLOT_MINUTES", "30")

    config = load_availability_config()

    assert config == AvailabilityConfig(
        opening_time=time(9, 30),
        closing_time=time(11, 0),
        slot_minutes=30,
    )


def test_AC_ตรวจสอบห้องว่าง_01_ปฏิเสธวันที่ก่อนวันนี้():
    selected_date = date(2030, 1, 1)

    with pytest.raises(InvalidSearchDate, match="วันที่ค้นหาต้องเป็นวันนี้หรือหลังจากวันนี้"):
        calculate_availability(
            rooms=[Room("ROOM-A", "ห้องอ่านหนังสือ", 6)],
            bookings=[],
            selected_date=selected_date,
            room_type="ห้องอ่านหนังสือ",
            user_count=None,
            now=datetime(2030, 1, 2, 7, 0, tzinfo=BANGKOK),
        )


def test_AC_ตรวจสอบห้องว่าง_01_endpoint_ใช้อินพุตข้อมูลห้องและรายการจอง(monkeypatch):
    fixed_now = datetime(2030, 1, 2, 7, 0, tzinfo=BANGKOK)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed_now.astimezone(tz) if tz else fixed_now.replace(tzinfo=None)

    monkeypatch.setattr(main_module, "datetime", FixedDateTime)
    monkeypatch.setattr(
        store,
        "get_rooms",
        lambda: [
            Room("ROOM-A", "ห้องอ่านหนังสือ", 6),
            Room("ROOM-B", "ห้องอ่านหนังสือ", 8),
        ],
    )
    monkeypatch.setattr(
        store,
        "get_room_bookings",
        lambda: [
            RoomBooking("BOOKING-A", "ROOM-A", date(2030, 1, 2), time(8), time(12)),
            RoomBooking("BOOKING-B", "ROOM-B", date(2030, 1, 2), time(8), time(20)),
        ],
    )

    response = client.get(
        "/api/rooms/availability",
        params={"date": "2030-01-02", "room_type": "ห้องอ่านหนังสือ"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["message"] is None
    assert [room["room_id"] for room in payload["rooms"]] == ["ROOM-A"]
    assert payload["rooms"][0]["available_slots"][0] == {
        "start_time": "12:00:00",
        "end_time": "12:30:00",
    }


def test_AC_ตรวจสอบห้องว่าง_01_endpoint_ไม่อ่านข้อมูลเมื่อเลือกวันที่ย้อนหลัง(monkeypatch):
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            current = datetime(2030, 1, 2, 7, 0, tzinfo=BANGKOK)
            return current.astimezone(tz) if tz else current.replace(tzinfo=None)

    monkeypatch.setattr(main_module, "datetime", FixedDateTime)
    monkeypatch.setattr(
        store,
        "get_rooms",
        lambda: (_ for _ in ()).throw(AssertionError("Past date must not search rooms")),
    )

    response = client.get(
        "/api/rooms/availability",
        params={"date": "2030-01-01", "room_type": "ห้องอ่านหนังสือ"},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "date_before_today"