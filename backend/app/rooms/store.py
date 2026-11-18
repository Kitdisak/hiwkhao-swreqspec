from _thread import LockType
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, time
from threading import Lock
from typing import Iterator

from zoneinfo import ZoneInfo

from .models import Room, RoomBooking

_BANGKOK = ZoneInfo("Asia/Bangkok")
_demo_date = datetime.now(_BANGKOK).date()
_ROOM_LOCKS: dict[str, LockType] = {}
_ROOM_LOCKS_GUARD = Lock()
_ROOM_BOOKINGS_GUARD = Lock()

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
    with _ROOM_BOOKINGS_GUARD:
        return list(ROOM_BOOKINGS)


@contextmanager
def lock_room(room_id: str) -> Iterator[None]:
    """ล็อกการตรวจและบันทึกรายการของห้องเดียวกันใน process นี้ (NFR-CONC-01)."""
    with _ROOM_LOCKS_GUARD:
        lock = _ROOM_LOCKS.get(room_id)
        if lock is None:
            lock = Lock()
            _ROOM_LOCKS[room_id] = lock
    with lock:
        yield


def add_room_booking(booking: RoomBooking) -> None:
    """เพิ่มรายการจองลงใน store ร่วม (FR-จองห้องอ่านหนังสือ-/-ห้องประชุม-03)."""
    with _ROOM_BOOKINGS_GUARD:
        ROOM_BOOKINGS.append(booking)


def get_room_booking(booking_id: str) -> RoomBooking | None:
    """อ่านรายการจองห้องตาม booking reference โดยไม่เปลี่ยนข้อมูล."""
    with _ROOM_BOOKINGS_GUARD:
        return next(
            (booking for booking in ROOM_BOOKINGS if booking.booking_id == booking_id),
            None,
        )


def get_member_room_bookings(member_id: str) -> list[RoomBooking]:
    """อ่านรายการจองของสมาชิกตามตัวระบุจาก session เท่านั้น (FR-ติดตาม-/-ยกเลิกการจองห้อง-01)."""
    with _ROOM_BOOKINGS_GUARD:
        return [
            booking
            for booking in ROOM_BOOKINGS
            if booking.member_id == member_id
        ]


def cancel_room_booking(booking: RoomBooking) -> RoomBooking:
    """เปลี่ยนสถานะรายการเป็นยกเลิกแล้วโดยเก็บรายการไว้ใน store."""
    cancelled = replace(booking, status="ยกเลิกแล้ว")
    with _ROOM_BOOKINGS_GUARD:
        for index, stored in enumerate(ROOM_BOOKINGS):
            if stored.booking_id == booking.booking_id:
                ROOM_BOOKINGS[index] = cancelled
                break
    return cancelled