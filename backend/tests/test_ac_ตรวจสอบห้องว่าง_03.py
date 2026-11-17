from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.main import app
from app.rooms import store
from app.rooms.availability import calculate_availability
from app.rooms.models import Room

client = TestClient(app)
BANGKOK = ZoneInfo("Asia/Bangkok")


def test_AC_ตรวจสอบห้องว่าง_03_ค้นหาประเภทที่ไม่มีห้องว่าง():
    results = calculate_availability(
        rooms=[Room("ROOM-READING", "ห้องอ่านหนังสือ", 6)],
        bookings=[],
        selected_date=date(2030, 1, 2),
        room_type="ห้องประชุม",
        user_count=None,
        now=datetime(2030, 1, 2, 7, 0, tzinfo=BANGKOK),
    )

    assert results == []


@pytest.mark.parametrize(
    ("room_type", "user_count"),
    [
        ("ห้องประชุม", None),
        ("ห้องอ่านหนังสือ", "12"),
    ],
)
def test_AC_ตรวจสอบห้องว่าง_03_endpoint_แสดงเฉพาะข้อความไม่มีห้องว่าง(
    monkeypatch, room_type, user_count
):
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            current = datetime(2030, 1, 2, 7, 0, tzinfo=BANGKOK)
            return current.astimezone(tz) if tz else current.replace(tzinfo=None)

    monkeypatch.setattr(main_module, "datetime", FixedDateTime)
    monkeypatch.setattr(
        store,
        "get_rooms",
        lambda: [Room("ROOM-READING", "ห้องอ่านหนังสือ", 6)],
    )
    monkeypatch.setattr(store, "get_room_bookings", lambda: [])

    params = {"date": "2030-01-02", "room_type": room_type}
    if user_count is not None:
        params["user_count"] = user_count
    response = client.get("/api/rooms/availability", params=params)

    assert response.status_code == 200
    assert response.json() == {"rooms": [], "message": "ไม่มีห้องว่าง"}