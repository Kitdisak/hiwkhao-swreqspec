import os
from dataclasses import dataclass
from datetime import time


@dataclass(frozen=True)
class AvailabilityConfig:
    """Configurable opening interval and slot size (FR-ตรวจสอบห้องว่าง-02, ASM-03)."""

    opening_time: time = time(8, 0)
    closing_time: time = time(20, 0)
    slot_minutes: int = 30

    def __post_init__(self) -> None:
        opening_minutes = self.opening_time.hour * 60 + self.opening_time.minute
        closing_minutes = self.closing_time.hour * 60 + self.closing_time.minute
        if self.slot_minutes <= 0 or closing_minutes <= opening_minutes:
            raise ValueError("Invalid availability configuration")
        if (closing_minutes - opening_minutes) % self.slot_minutes:
            raise ValueError("Slot duration must divide the configured opening period")


def _read_time_setting(name: str, default: str) -> time:
    value = os.getenv(name, default)
    try:
        return time.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{name} must use HH:MM format") from error


def _read_slot_duration() -> int:
    value = os.getenv("ROOMS_SLOT_MINUTES", "30")
    try:
        return int(value)
    except ValueError as error:
        raise ValueError("ROOMS_SLOT_MINUTES must be a positive integer") from error


def load_availability_config() -> AvailabilityConfig:
    """Read availability settings from the process environment (FR-ตรวจสอบห้องว่าง-02, ASM-03)."""
    return AvailabilityConfig(
        opening_time=_read_time_setting("ROOMS_OPENING_TIME", "08:00"),
        closing_time=_read_time_setting("ROOMS_CLOSING_TIME", "20:00"),
        slot_minutes=_read_slot_duration(),
    )


DEFAULT_AVAILABILITY_CONFIG = load_availability_config()