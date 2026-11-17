from datetime import datetime, time
from zoneinfo import ZoneInfo

from .models import Room, RoomBooking

_BANGKOK = ZoneInfo("Asia/Bangkok")
_demo_date = datetime.now(_BANGKOK).date()

# ข้อมูล demo ไม่ใช่ข้อมูลจริงของห้องสมุด — ทีมเลือกเอง ไม่ได้มาจาก spec
# ข้อมูลตัวอย่างรองรับการตรวจห้องและตารางจอง (FR-ตรวจสอบห้องว่าง-01, FR-ตรวจสอบห้องว่าง-02).
ROOMS: list[Room] = [
    Room(room_id="ROOM-READING-01", room_type="ห้องอ่านหนังสือ", capacity=6),
    Room(room_id="ROOM-MEETING-01", room_type="ห้องประชุม", capacity=10),
]
ROOM_BOOKINGS: list[RoomBooking] = [
    RoomBooking(
        booking_id="DEMO-ROOM-BOOKING-01",
        room_id="ROOM-READING-01",
        booking_date=_demo_date,
        start_time=time(8, 0),
        end_time=time(9, 0),
    ),
]


def get_rooms() -> list[Room]:
    """อ่านข้อมูลห้องจาก store เดียวที่ UC-09 จะใช้ร่วมกันภายหลัง (FR-ตรวจสอบห้องว่าง-01)."""
    return list(ROOMS)


def get_room_bookings() -> list[RoomBooking]:
    """อ่านรายการจองห้องที่มีอยู่โดยไม่เขียนหรือแก้ไขรายการ (FR-ตรวจสอบห้องว่าง-02)."""
    return list(ROOM_BOOKINGS)