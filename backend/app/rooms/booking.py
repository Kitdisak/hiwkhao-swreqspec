from __future__ import annotations

from datetime import date, datetime, time
from uuid import uuid4
from zoneinfo import ZoneInfo

from .config import AvailabilityConfig, DEFAULT_AVAILABILITY_CONFIG
from . import store as room_store
from .models import Room, RoomBooking

_BANGKOK = ZoneInfo("Asia/Bangkok")
_MIN_BOOKING_MINUTES = 30
_MAX_BOOKING_MINUTES = 4 * 60


class BookingValidationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class RoomBookingConflict(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _invalid_time_message(config: AvailabilityConfig) -> str:
    opening = config.opening_time.strftime("%H:%M")
    closing = config.closing_time.strftime("%H:%M")
    return (
        f"เลือกเวลาได้ช่วงละ {config.slot_minutes} นาที "
        f"ระหว่าง {opening}–{closing}"
    )


def validate_booking_input(
    room: Room,
    booking_date: date,
    start_time: time,
    end_time: time,
    user_count: object,
    now: datetime,
    config: AvailabilityConfig = DEFAULT_AVAILABILITY_CONFIG,
) -> None:
    """Validate booking input before availability checks (FR-จองห้องอ่านหนังสือ-/-ห้องประชุม-01)."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")

    if not isinstance(booking_date, date) or isinstance(booking_date, datetime):
        raise BookingValidationError(
            "invalid_booking_date", "กรุณาเลือกวันที่ตั้งแต่วันนี้เป็นต้นไป"
        )

    local_now = now.astimezone(_BANGKOK)
    if booking_date < local_now.date():
        raise BookingValidationError(
            "date_before_today", "กรุณาเลือกวันที่ตั้งแต่วันนี้เป็นต้นไป"
        )

    invalid_time_message = _invalid_time_message(config)
    if (
        not isinstance(start_time, time)
        or not isinstance(end_time, time)
        or start_time.tzinfo is not None
        or end_time.tzinfo is not None
    ):
        raise BookingValidationError("invalid_booking_time", invalid_time_message)

    if start_time >= end_time:
        raise BookingValidationError(
            "invalid_time_order", "เวลาเริ่มต้องก่อนเวลาสิ้นสุด"
        )

    if start_time < config.opening_time or end_time > config.closing_time:
        raise BookingValidationError("invalid_booking_time", invalid_time_message)

    opening_minutes = config.opening_time.hour * 60 + config.opening_time.minute
    start_minutes = start_time.hour * 60 + start_time.minute
    end_minutes = end_time.hour * 60 + end_time.minute
    if (
        start_time.second
        or start_time.microsecond
        or end_time.second
        or end_time.microsecond
        or (start_minutes - opening_minutes) % config.slot_minutes
        or (end_minutes - opening_minutes) % config.slot_minutes
    ):
        raise BookingValidationError("invalid_booking_time", invalid_time_message)

    duration_minutes = end_minutes - start_minutes
    if duration_minutes < _MIN_BOOKING_MINUTES:
        raise BookingValidationError(
            "booking_too_short", "จองได้อย่างน้อย 30 นาที"
        )
    if duration_minutes > _MAX_BOOKING_MINUTES:
        raise BookingValidationError(
            "booking_too_long", "จองได้ไม่เกิน 4 ชั่วโมง"
        )

    if (
        booking_date == local_now.date()
        and start_time < local_now.timetz().replace(tzinfo=None)
    ):
        raise BookingValidationError(
            "booking_start_in_past", "ไม่สามารถจองช่วงเวลาที่ผ่านไปแล้ว"
        )

    capacity = room.capacity
    if isinstance(capacity, bool) or not isinstance(capacity, int):
        raise BookingValidationError(
            "room_capacity_unavailable",
            "ห้องนี้ไม่สามารถจองได้เนื่องจากไม่มีข้อมูลความจุ",
        )

    if (
        isinstance(user_count, bool)
        or not isinstance(user_count, int)
        or user_count < 1
    ):
        raise BookingValidationError(
            "invalid_user_count",
            "กรุณาระบุจำนวนผู้ใช้งานเป็นจำนวนเต็มตั้งแต่ 1 ขึ้นไป",
        )
    if user_count > capacity:
        raise BookingValidationError(
            "user_count_exceeds_capacity",
            f"ห้องนี้รองรับได้สูงสุด {capacity} คน",
        )


def create_room_booking(
    room: Room,
    booking_date: date,
    start_time: time,
    end_time: time,
    user_count: int,
    member_id: str,
    request_id: str,
    now: datetime,
    config: AvailabilityConfig = DEFAULT_AVAILABILITY_CONFIG,
) -> RoomBooking:
    """Atomically check and add a booking under the room lock.

    Supports FR-จองห้องอ่านหนังสือ-/-ห้องประชุม-02 and FR-จองห้องอ่านหนังสือ-/-ห้องประชุม-03.
    """
    with room_store.lock_room(room.room_id):
        bookings = room_store.get_room_bookings()
        existing_request = next(
            (booking for booking in bookings if booking.request_id == request_id),
            None,
        )
        if existing_request is not None:
            same_request = (
                existing_request.room_id == room.room_id
                and existing_request.booking_date == booking_date
                and existing_request.start_time == start_time
                and existing_request.end_time == end_time
                and existing_request.user_count == user_count
                and existing_request.member_id == member_id
            )
            if same_request:
                return existing_request
            raise RoomBookingConflict(
                "request_id_conflict", "ตัวระบุคำขอนี้ถูกใช้แล้ว"
            )

        validate_booking_input(
            room=room,
            booking_date=booking_date,
            start_time=start_time,
            end_time=end_time,
            user_count=user_count,
            now=now,
            config=config,
        )

        overlaps_existing_booking = any(
            booking.room_id == room.room_id
            and booking.booking_date == booking_date
            and start_time < booking.end_time
            and end_time > booking.start_time
            for booking in bookings
        )
        if overlaps_existing_booking:
            raise RoomBookingConflict(
                "room_unavailable", "ช่วงเวลานี้ไม่ว่าง กรุณาเลือกเวลาใหม่"
            )

        booking = RoomBooking(
            booking_id=f"ROOM-{uuid4().hex}",
            room_id=room.room_id,
            booking_date=booking_date,
            start_time=start_time,
            end_time=end_time,
            request_id=request_id,
            member_id=member_id,
            user_count=user_count,
        )
        room_store.add_room_booking(booking)
        return booking