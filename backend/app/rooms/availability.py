from __future__ import annotations

from datetime import date, datetime, time
from typing import Iterable
from zoneinfo import ZoneInfo

from .config import AvailabilityConfig, DEFAULT_AVAILABILITY_CONFIG
from .models import AvailableRoom, AvailabilitySlot, Room, RoomBooking

_BANGKOK = ZoneInfo("Asia/Bangkok")


class InvalidAvailabilityInput(ValueError):
    pass


class InvalidUserCount(InvalidAvailabilityInput):
    """Invalid optional count filter (FR-ตรวจสอบห้องว่าง-03)."""

    pass


class InvalidSearchDate(InvalidAvailabilityInput):
    """A search date before today (FR-ตรวจสอบห้องว่าง-01)."""

    pass


def parse_user_count(value: str | None) -> int | None:
    """Validate an optional positive integer count filter (FR-ตรวจสอบห้องว่าง-03)."""
    if value is None or not value.strip():
        return None

    try:
        user_count = int(value.strip())
    except ValueError as error:
        raise InvalidUserCount from error

    if user_count < 1:
        raise InvalidUserCount
    return user_count


def validate_search_date(selected_date: date, now: datetime) -> None:
    """Reject dates before the supplied Bangkok-local current date (FR-ตรวจสอบห้องว่าง-01)."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    if selected_date < now.astimezone(_BANGKOK).date():
        raise InvalidSearchDate("วันที่ค้นหาต้องเป็นวันนี้หรือหลังจากวันนี้")


def calculate_availability(
    rooms: Iterable[Room],
    bookings: Iterable[RoomBooking],
    selected_date: date,
    room_type: str,
    user_count: int | None,
    now: datetime,
    config: AvailabilityConfig = DEFAULT_AVAILABILITY_CONFIG,
) -> list[AvailableRoom]:
    """คำนวณช่วงว่างจาก input ที่รับมาเท่านั้น (FR-ตรวจสอบห้องว่าง-01 ถึง FR-ตรวจสอบห้องว่าง-04)."""
    validate_search_date(selected_date, now)
    local_now = now.astimezone(_BANGKOK)
    if user_count is not None and (
        isinstance(user_count, bool)
        or not isinstance(user_count, int)
        or user_count < 1
    ):
        raise InvalidUserCount

    room_candidates = [
        room
        for room in rooms
        if room.room_type == room_type
        and (
            user_count is None
            or (room.capacity is not None and room.capacity >= user_count)
        )
    ]
    day_bookings = [
        booking for booking in bookings if booking.booking_date == selected_date
    ]

    available_rooms: list[AvailableRoom] = []
    for room in room_candidates:
        available_slots = tuple(
            slot
            for slot in _daily_slots(config)
            if not (
                selected_date == local_now.date()
                and slot.start_time < local_now.time().replace(tzinfo=None)
            )
            and not any(
                booking.room_id == room.room_id
                and booking.start_time < slot.end_time
                and booking.end_time > slot.start_time
                for booking in day_bookings
            )
        )
        if available_slots:
            available_rooms.append(
                AvailableRoom(
                    room_id=room.room_id,
                    room_type=room.room_type,
                    capacity=room.capacity,
                    available_slots=available_slots,
                )
            )

    return available_rooms


def _daily_slots(config: AvailabilityConfig) -> tuple[AvailabilitySlot, ...]:
    """Build slots from the configured opening interval (FR-ตรวจสอบห้องว่าง-02, ASM-03)."""
    opening_minutes = config.opening_time.hour * 60 + config.opening_time.minute
    closing_minutes = config.closing_time.hour * 60 + config.closing_time.minute
    slots: list[AvailabilitySlot] = []

    for start_minutes in range(
        opening_minutes, closing_minutes, config.slot_minutes
    ):
        end_minutes = start_minutes + config.slot_minutes
        slots.append(
            AvailabilitySlot(
                start_time=time(start_minutes // 60, start_minutes % 60),
                end_time=time(end_minutes // 60, end_minutes % 60),
            )
        )

    return tuple(slots)