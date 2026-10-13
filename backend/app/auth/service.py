from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from typing import Any

from .models import User


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
    return (
        f"pbkdf2_sha256${100_000}$"
        f"{base64.b64encode(salt).decode('ascii')}$"
        f"{base64.b64encode(digest).decode('ascii')}"
    )


USERS: list[User] = [
    User(
        username="s12345",
        email="s12345@university.ac.th",
        student_id="STU-001",
        password_hash=hash_password("pass1234"),
        role="student",
        permissions=("view_profile", "borrow_book"),
    ),
    User(
        username="admin",
        email="admin@university.ac.th",
        student_id="ADM-001",
        password_hash=hash_password("admin123"),
        role="admin",
        permissions=("manage_users", "manage_books"),
    ),
]


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algo, iterations, salt_b64, digest_b64 = stored_hash.split("$")
        if algo != "pbkdf2_sha256":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        computed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
        return hmac.compare_digest(computed, expected)
    except (ValueError, TypeError):
        return False


def _find_user(identifier: str | None) -> User | None:
    if not identifier:
        return None
    key = identifier.strip().lower()
    for user in USERS:
        if user.username.lower() == key or user.email.lower() == key or user.student_id.lower() == key:
            return user
    return None


def login_user(username: str | None = None, password: str | None = None, email: str | None = None) -> dict[str, Any]:
    identifier = (username or email or "").strip()
    user = _find_user(identifier)
    if not user or not password or not verify_password(password, user.password_hash):
        return {
            "success": False,
            "message": "รหัสผ่านหรือชื่อผู้ใช้ไม่ถูกต้อง",
            "session_timeout_seconds": 600,
        }

    return {
        "success": True,
        "message": "เข้าสู่ระบบสำเร็จ",
        "redirect": "/",
        "session_timeout_seconds": 600,
        "user": user.to_dict(),
    }


def reset_password(student_id: str | None = None, new_password: str | None = None) -> dict[str, Any]:
    if not student_id:
        return {"success": False, "message": "ข้อมูลนักศึกษาไม่ถูกต้อง", "can_reset": False}

    user = _find_user(student_id)
    if not user:
        return {"success": False, "message": "ข้อมูลนักศึกษาไม่ถูกต้อง", "can_reset": False}

    if new_password:
        updated = User(
            username=user.username,
            email=user.email,
            student_id=user.student_id,
            password_hash=hash_password(new_password),
            role=user.role,
            permissions=user.permissions,
        )
        for index, current in enumerate(USERS):
            if current.username == user.username:
                USERS[index] = updated
                break
        return {
            "success": True,
            "message": "เปลี่ยนรหัสผ่านสำเร็จ",
            "can_reset": True,
            "user": updated.to_dict(),
        }

    return {
        "success": True,
        "message": "ยืนยันตัวตนสำเร็จ สามารถเปลี่ยนรหัสผ่านได้",
        "can_reset": True,
        "user": user.to_dict(),
    }
