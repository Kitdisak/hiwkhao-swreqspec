from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.main import app
from app.rooms import store
from app.rooms.availability import (
    InvalidUserCount,
    calculate_availability,
    parse_user_count,
)
from app.rooms.models import Room

client = TestClient(app)
BANGKOK = ZoneInfo("Asia/Bangkok")
SELECTED_DATE = date(2030, 1, 2)
ROOMS = [
    Room("ROOM-4", "ห้องอ่านหนังสือ", 4),
    Room("ROOM-6", "ห้องอ่านหนังสือ", 6),
    Room("ROOM-10", "ห้องอ่านหนังสือ", 10),
    Room("ROOM-UNKNOWN", "ห้องอ่านหนังสือ", None),
]


def _search(user_count: int | None):
    return calculate_availability(
        rooms=ROOMS,
        bookings=[],
        selected_date=SELECTED_DATE,
        room_type="ห้องอ่านหนังสือ",
        user_count=user_count,
        now=datetime(2030, 1, 2, 7, 0, tzinfo=BANGKOK),
    )


def test_AC_ตรวจสอบห้องว่าง_02_กรองความจุและรองรับตัวกรองที่ไม่ระบุ():
    assert [room.room_id for room in _search(6)] == ["ROOM-6", "ROOM-10"]
    assert [room.room_id for room in _search(None)] == [
        "ROOM-4",
        "ROOM-6",
        "ROOM-10",
        "ROOM-UNKNOWN",
    ]


def test_AC_ตรวจสอบห้องว่าง_02_ไม่มีห้องที่รองรับจำนวนที่ระบุ():
    assert _search(12) == []


@pytest.mark.parametrize("value", ["0", "-1", "2.5", "invalid"])
def test_AC_ตรวจสอบห้องว่าง_02_ปฏิเสธจำนวนที่ไม่ใช่จำนวนเต็มบวก(value):
    with pytest.raises(InvalidUserCount):
        parse_user_count(value)


def test_AC_ตรวจสอบห้องว่าง_02_endpoint_อินพุตไม่ถูกต้องไม่ค้นหา(monkeypatch):
    class UnexpectedDateTime:
        @classmethod
        def now(cls, tz=None):
            raise AssertionError("The search should not read the clock for invalid input")

    monkeypatch.setattr(main_module, "datetime", UnexpectedDateTime)
    monkeypatch.setattr(
        store,
        "get_rooms",
        lambda: (_ for _ in ()).throw(AssertionError("The search should not read rooms")),
    )

    response = client.get(
        "/api/rooms/availability",
        params={
            "date": "2030-01-02",
            "room_type": "ห้องอ่านหนังสือ",
            "user_count": "2.5",
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_user_count"
    assert response.json()["message"] == "กรุณาระบุจำนวนผู้ใช้งานเป็นจำนวนเต็มตั้งแต่ 1 ขึ้นไป"


@pytest.mark.parametrize(
    ("user_count", "expected_room_ids", "expected_message"),
    [
        ("6", ["ROOM-6", "ROOM-10"], None),
        (None, ["ROOM-4", "ROOM-6", "ROOM-10", "ROOM-UNKNOWN"], None),
        ("12", [], "ไม่มีห้องว่าง"),
    ],
)
def test_AC_ตรวจสอบห้องว่าง_02_endpoint_กรองความจุและแจ้งกรณีไม่มีห้อง(
    monkeypatch, user_count, expected_room_ids, expected_message
):
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            current = datetime(2030, 1, 2, 7, 0, tzinfo=BANGKOK)
            return current.astimezone(tz) if tz else current.replace(tzinfo=None)

    monkeypatch.setattr(main_module, "datetime", FixedDateTime)
    monkeypatch.setattr(store, "get_rooms", lambda: ROOMS)
    monkeypatch.setattr(store, "get_room_bookings", lambda: [])
    params = {
        "date": SELECTED_DATE.isoformat(),
        "room_type": "ห้องอ่านหนังสือ",
    }
    if user_count is not None:
        params["user_count"] = user_count

    response = client.get("/api/rooms/availability", params=params)

    assert response.status_code == 200
    payload = response.json()
    assert [room["room_id"] for room in payload["rooms"]] == expected_room_ids
    assert payload["message"] == expected_message
    if user_count == "12":
        assert payload == {"rooms": [], "message": "ไม่มีห้องว่าง"}