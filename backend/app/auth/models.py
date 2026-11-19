from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal


@dataclass(frozen=True)
class Account:
    account_id: str
    user_type: str
    display_name: str
    password_hash: str
    email: str | None = None
    role_id: str | None = None


@dataclass(frozen=True)
class IdentityProfile:
    account_id: str
    first_name: str
    last_name: str
    birth_year: int
    national_id: str
    phone: str
    student_id: str | None = None
    date_of_birth: date | None = None


@dataclass(frozen=True)
class AuthSession:
    account_id: str
    last_activity_at: datetime
    is_active: bool


@dataclass(frozen=True)
class User:
    username: str
    email: str
    student_id: str | None
    password_hash: str
    user_type: Literal["student", "staff", "external"]
    role: str = "student"
    permissions: tuple[str, ...] = field(default_factory=tuple)
    account_status: Literal["Active", "Suspended"] = "Active"
    overdue_count: int = 0
    unpaid_fine_count: int = 0
    first_name: str = ""
    last_name: str = ""
    phone: str = ""

    def to_dict(self) -> dict[str, str | tuple[str, ...] | None]:
        return {
            "username": self.username,
            "email": self.email,
            "student_id": self.student_id,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "phone": self.phone,
            "user_type": self.user_type,
            "role": self.role,
            "permissions": self.permissions,
            "account_status": self.account_status,
        }
