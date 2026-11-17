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
    """Existing room booking used to calculate unavailable slots (FR-ตรวจสอบห้องว่าง-02)."""

    booking_id: str
    room_id: str
    booking_date: date
    start_time: time
    end_time: time


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