from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from pathlib import Path
from typing import Any

from .models import User


def _member_database_path() -> Path:
    configured = os.environ.get("LIBRARY_RESERVATION_DB")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[2] / "data" / "reservations.sqlite3"


def _member_connection() -> sqlite3.Connection:
    path = _member_database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 10000")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS managed_accounts (
            username TEXT PRIMARY KEY,
            email TEXT NOT NULL,
            student_id TEXT,
            user_type TEXT NOT NULL,
            role TEXT NOT NULL,
            permissions_json TEXT NOT NULL,
            account_status TEXT NOT NULL DEFAULT 'Active'
                CHECK (account_status IN ('Active', 'Suspended')),
            first_name TEXT NOT NULL DEFAULT '',
            last_name TEXT NOT NULL DEFAULT '',
            phone TEXT NOT NULL DEFAULT ''
        );
        CREATE UNIQUE INDEX IF NOT EXISTS unique_managed_account_email
            ON managed_accounts(email);
        """
    )
    for user in USERS:
        import json
        connection.execute(
            """
            INSERT INTO managed_accounts (
                username, email, student_id, user_type, role, permissions_json,
                account_status, first_name, last_name, phone
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(username) DO NOTHING
            """,
            (
                user.username,
                user.email,
                user.student_id,
                user.user_type,
                user.role,
                json.dumps(list(user.permissions)),
                user.account_status,
                user.first_name,
                user.last_name,
                user.phone,
            ),
        )
    return connection


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
        user_type="student",
        role="student",
        permissions=("view_profile", "borrow_book"),
    ),
    User(
        username="admin",
        email="admin@university.ac.th",
        student_id="ADM-001",
        password_hash=hash_password("admin123"),
        user_type="staff",
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
        if (
            user.username.lower() == key
            or user.email.lower() == key
            or (user.student_id is not None and user.student_id.lower() == key)
        ):
            return user
    return None


def find_user_by_username(username: str) -> User | None:
    user = next((item for item in USERS if item.username == username), None)
    if user is None:
        return None
    connection = _member_connection()
    try:
        row = connection.execute(
            """
            SELECT email, role, permissions_json, account_status,
                   first_name, last_name, phone
            FROM managed_accounts
            WHERE username = ?
            """,
            (username,),
        ).fetchone()
    finally:
        connection.close()
    if row is not None:
        persisted_permissions = tuple(json.loads(row["permissions_json"]))
        updated = User(
            username=user.username,
            email=row["email"],
            student_id=user.student_id,
            password_hash=user.password_hash,
            user_type=user.user_type,
            role=row["role"],
            permissions=persisted_permissions,
            account_status=row["account_status"],
            overdue_count=user.overdue_count,
            unpaid_fine_count=user.unpaid_fine_count,
            first_name=row["first_name"],
            last_name=row["last_name"],
            phone=row["phone"],
        )
        for index, current in enumerate(USERS):
            if current.username == username:
                USERS[index] = updated
                break
        return updated
    return user


def search_managed_accounts(query: str | None) -> list[dict[str, Any]]:
    key = (query or "").strip().casefold()
    if not key:
        return []
    results: list[dict[str, Any]] = []
    for user in USERS:
        if user.student_id and user.student_id.casefold() == key:
            matched = True
        else:
            matched = key in " ".join(
                (user.first_name, user.last_name, user.email)
            ).casefold()
        if matched:
            results.append(
                {
                    "username": user.username,
                    "name": " ".join((user.first_name, user.last_name)).strip()
                    or user.username,
                    "email": user.email,
                    "phone": user.phone,
                    "student_id": user.student_id,
                    "user_type": user.user_type,
                    "role": user.role,
                    "permissions": list(user.permissions),
                    "account_status": user.account_status,
                }
            )
        if len(results) == 50:
            break
    return results


def get_managed_account(username: str) -> dict[str, Any] | None:
    user = find_user_by_username(username)
    if user is None:
        return None
    return {
        "username": user.username,
        "name": " ".join((user.first_name, user.last_name)).strip() or user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "phone": user.phone,
        "student_id": user.student_id,
        "user_type": user.user_type,
        "role": user.role,
        "permissions": list(user.permissions),
        "account_status": user.account_status,
    }


def update_managed_account(
    username: str,
    *,
    first_name: str,
    last_name: str,
    email: str,
    phone: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    user = find_user_by_username(username)
    if user is None:
        return None, {"code": "account_not_found", "message": "ไม่พบบัญชีผู้ใช้"}

    normalized_email = email.strip()
    if not normalized_email:
        if user.user_type == "external":
            return None, {"code": "email_required", "message": "อีเมลห้ามว่างสำหรับบุคคลภายนอก"}
    for existing in USERS:
        if existing.username != username and existing.email.strip().casefold() == normalized_email.casefold():
            return None, {"code": "email_duplicate", "message": "อีเมลซ้ำกับบัญชีอื่น"}

    updated = User(
        username=user.username,
        email=normalized_email,
        student_id=user.student_id,
        password_hash=user.password_hash,
        user_type=user.user_type,
        role=user.role,
        permissions=user.permissions,
        account_status=user.account_status,
        overdue_count=user.overdue_count,
        unpaid_fine_count=user.unpaid_fine_count,
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        phone=phone.strip(),
    )
    connection = _member_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """
            UPDATE managed_accounts
            SET email = ?, first_name = ?, last_name = ?, phone = ?
            WHERE username = ?
            """,
            (normalized_email, updated.first_name, updated.last_name, updated.phone, username),
        )
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()
    for index, current in enumerate(USERS):
        if current.username == username:
            USERS[index] = updated
            break
    return get_managed_account(username), None


ROLE_PERMISSIONS = {
    "member": ("view_profile", "borrow_book"),
    "librarian": ("view_profile", "borrow_book", "manage_books"),
    "admin": ("view_profile", "borrow_book", "manage_users", "manage_books"),
}


def change_managed_role_permissions(
    username: str,
    *,
    role: str,
    permissions: list[str],
    actor_username: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if username == actor_username:
        return None, {"code": "permission_required", "message": "คุณไม่มีสิทธิ์ดำเนินการนี้"}
    user = find_user_by_username(username)
    actor = find_user_by_username(actor_username)
    if user is None:
        return None, {"code": "account_not_found", "message": "ไม่พบบัญชีผู้ใช้"}
    if actor is None or "manage_users" not in actor.permissions:
        return None, {"code": "permission_required", "message": "คุณไม่มีสิทธิ์ดำเนินการนี้"}

    normalized_role = role.strip().casefold()
    if normalized_role not in ROLE_PERMISSIONS:
        return None, {"code": "invalid_role", "message": "Role ไม่ถูกต้อง"}
    if any(permission not in ROLE_PERMISSIONS[normalized_role] for permission in permissions):
        return None, {"code": "permission_required", "message": "คุณไม่มีสิทธิ์ดำเนินการนี้"}
    if any(permission not in actor.permissions for permission in permissions):
        return None, {"code": "permission_required", "message": "คุณไม่มีสิทธิ์ดำเนินการนี้"}

    if user.role == "admin" and normalized_role != "admin":
        active_admin_count = sum(
            1
            for item in USERS
            if item.role == "admin"
            and item.account_status == "Active"
        )
        if active_admin_count <= 1:
            return None, {"code": "permission_required", "message": "คุณไม่มีสิทธิ์ดำเนินการนี้"}

    updated = User(
        username=user.username,
        email=user.email,
        student_id=user.student_id,
        password_hash=user.password_hash,
        user_type=user.user_type,
        role=normalized_role,
        permissions=tuple(dict.fromkeys(permissions)),
        account_status=user.account_status,
        overdue_count=user.overdue_count,
        unpaid_fine_count=user.unpaid_fine_count,
        first_name=user.first_name,
        last_name=user.last_name,
        phone=user.phone,
    )
    connection = _member_connection()
    try:
        import json
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """
            UPDATE managed_accounts
            SET role = ?, permissions_json = ?
            WHERE username = ?
            """,
            (normalized_role, json.dumps(list(updated.permissions)), username),
        )
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()
    for index, current in enumerate(USERS):
        if current.username == username:
            USERS[index] = updated
            break
    return get_managed_account(username), None


def set_managed_account_status(
    username: str,
    status: str,
    actor_username: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if status not in ("Active", "Suspended"):
        return None, {"code": "invalid_status", "message": "สถานะบัญชีไม่ถูกต้อง"}
    if username == actor_username:
        return None, {"code": "permission_required", "message": "คุณไม่มีสิทธิ์ดำเนินการนี้"}
    user = find_user_by_username(username)
    if user is None:
        return None, {"code": "account_not_found", "message": "ไม่พบบัญชีผู้ใช้"}

    if status == "Suspended":
        active_admin_count = sum(
            1
            for item in USERS
            if item.role == "admin"
            and item.account_status == "Active"
        )
        if user.role == "admin" and user.account_status == "Active" and active_admin_count <= 1:
            return None, {"code": "permission_required", "message": "คุณไม่มีสิทธิ์ดำเนินการนี้"}

    updated = User(
        username=user.username,
        email=user.email,
        student_id=user.student_id,
        password_hash=user.password_hash,
        user_type=user.user_type,
        role=user.role,
        permissions=user.permissions,
        account_status=status,
        overdue_count=user.overdue_count,
        unpaid_fine_count=user.unpaid_fine_count,
        first_name=user.first_name,
        last_name=user.last_name,
        phone=user.phone,
    )
    connection = _member_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "UPDATE managed_accounts SET account_status = ? WHERE username = ?",
            (status, username),
        )
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()
    for index, current in enumerate(USERS):
        if current.username == username:
            USERS[index] = updated
            break
    return get_managed_account(username), None


def find_borrow_member(identifier: str | None) -> User | None:
    """ค้นหาสมาชิกสำหรับการยืมด้วยรหัสนักศึกษาหรืออีเมลบุคลากร (FR-01, ASM-19)."""
    if not identifier:
        return None
    key = identifier.strip().casefold()
    return next(
        (
            user
            for user in USERS
            if (
                user.user_type == "student"
                and user.student_id
                and user.student_id.casefold() == key
            )
            or (user.user_type == "staff" and user.email.casefold() == key)
        ),
        None,
    )


def _find_login_user(identifier: str | None) -> User | None:
    if not identifier:
        return None
    key = identifier.strip().lower()
    for user in USERS:
        if user.username.lower() == key or user.email.lower() == key:
            return user
        if user.user_type == "student" and user.student_id and user.student_id.lower() == key:
            return user
    return None


def login_user(username: str | None = None, password: str | None = None, email: str | None = None) -> dict[str, Any]:
    identifier = (username or email or "").strip()
    user = _find_login_user(identifier)
    if not user or not password or not verify_password(password, user.password_hash):
        return {
            "success": False,
            "message": "รหัสผ่านหรือชื่อผู้ใช้ไม่ถูกต้อง",
            "session_timeout_seconds": 600,
        }
    persisted_user = find_user_by_username(user.username)
    if persisted_user is not None:
        user = persisted_user
    if user.account_status == "Suspended":
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
            user_type=user.user_type,
            role=user.role,
            permissions=user.permissions,
            account_status=user.account_status,
            overdue_count=user.overdue_count,
            unpaid_fine_count=user.unpaid_fine_count,
            first_name=user.first_name,
            last_name=user.last_name,
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
