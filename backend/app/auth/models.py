from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class User:
    username: str
    email: str
    student_id: str
    password_hash: str
    role: str = "student"
    permissions: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, str | tuple[str, ...]]:
        return {
            "username": self.username,
            "email": self.email,
            "student_id": self.student_id,
            "role": self.role,
            "permissions": self.permissions,
        }
