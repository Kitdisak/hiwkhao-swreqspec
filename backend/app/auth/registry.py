from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class StudentRecord:
    student_id: str
    national_id: str
    first_name: str
    last_name: str
    date_of_birth: date
    phone: str
    status: str = "Active"


@dataclass(frozen=True)
class StaffRecord:
    national_id: str
    first_name: str
    last_name: str
    date_of_birth: date
    phone: str
    email: str


STUDENT_REGISTRY: dict[str, StudentRecord] = {
    "STU-001": StudentRecord(
        student_id="STU-001",
        national_id="1100000000001",
        first_name="",
        last_name="",
        date_of_birth=date(2000, 1, 1),
        phone="",
        status="Active",
    ),
}

STAFF_REGISTRY: dict[str, StaffRecord] = {
    "1000000000001": StaffRecord(
        national_id="1000000000001",
        first_name="",
        last_name="",
        date_of_birth=date(1980, 1, 1),
        phone="",
        email="admin@university.ac.th",
    ),
}


def _registry_timeout() -> bool:
    return os.environ.get("LIBRARY_REGISTRY_MODE", "").casefold() == "timeout"


def lookup_student(student_id: str, national_id: str) -> str:
    if _registry_timeout():
        return "timeout"
    record = STUDENT_REGISTRY.get(student_id.strip())
    if record is None or record.national_id != national_id.strip():
        return "not_found"
    return "found"


def lookup_staff(national_id: str) -> str:
    if _registry_timeout():
        return "timeout"
    return "found" if national_id.strip() in STAFF_REGISTRY else "not_found"


def get_student(student_id: str) -> StudentRecord | None:
    return STUDENT_REGISTRY.get(student_id.strip())


def get_staff(national_id: str) -> StaffRecord | None:
    return STAFF_REGISTRY.get(national_id.strip())
