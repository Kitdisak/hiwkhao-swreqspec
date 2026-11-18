from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time


@dataclass(frozen=True)
class Room:
    """Room data used for search and optional capacity filtering (FR-ตรวจสอบห้องว่าง-01, FR-ตรวจสอบห้องว่าง-03)."""

    room_id: str
    room_type: str
    capacity: int | None


@dataclass(frozen=True)
class RoomBooking:
    """Room booking shared by availability and reservation flows (SPEC-008/009)."""

    booking_id: str
    room_id: str
    booking_date: date
    start_time: time
    end_time: time
    request_id: str | None = None
    member_id: str | None = None
    user_count: int | None = None
    status: str = "จองแล้ว"


@dataclass(frozen=True)
class AvailabilitySlot:
    """One free time interval for a room (FR-ตรวจสอบห้องว่าง-02)."""

    start_time: time
    end_time: time


@dataclass(frozen=True)
class AvailableRoom:
    """A room with at least one free slot (FR-ตรวจสอบห้องว่าง-02, FR-ตรวจสอบห้องว่าง-04)."""

    room_id: str
    room_type: str
    capacity: int | None
    available_slots: tuple[AvailabilitySlot, ...]