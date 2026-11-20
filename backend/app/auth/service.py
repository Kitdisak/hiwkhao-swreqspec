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
from datetime import date, datetime
from zoneinfo import ZoneInfo

from . import registry

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
    table_exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'managed_accounts'"
    ).fetchone()
    if table_exists:
        email_column = next(
            (
                row
                for row in connection.execute("PRAGMA table_info(managed_accounts)")
                if row["name"] == "email"
            ),
            None,
        )
        if email_column is not None and email_column["notnull"]:
            connection.execute("DROP INDEX IF EXISTS unique_managed_account_email")
            connection.execute(
                "ALTER TABLE managed_accounts RENAME TO managed_accounts_legacy"
            )
            table_exists = None
    if table_exists is None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS managed_accounts (
                username TEXT PRIMARY KEY,
                email TEXT,
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
                ON managed_accounts(email)
                WHERE email IS NOT NULL AND TRIM(email) <> '';
            CREATE TABLE IF NOT EXISTS managed_account_audit (
                audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor_account_id TEXT NOT NULL,
                target_account_id TEXT NOT NULL,
                timestamp_bangkok TEXT NOT NULL,
                field TEXT NOT NULL,
                old_value TEXT,
                new_value TEXT
            );
            """
        )
        legacy_exists = connection.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type = 'table' AND name = 'managed_accounts_legacy'"
        ).fetchone()
        if legacy_exists:
            connection.execute(
                """
                INSERT OR IGNORE INTO managed_accounts (
                    username, email, student_id, user_type, role, permissions_json,
                    account_status, first_name, last_name, phone
                )
                SELECT
                    username,
                    NULLIF(TRIM(email), ''),
                    student_id,
                    user_type,
                    role,
                    permissions_json,
                    account_status,
                    first_name,
                    last_name,
                    phone
                FROM managed_accounts_legacy
                """
            )
            connection.execute("DROP TABLE managed_accounts_legacy")
    else:
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS unique_managed_account_email
                ON managed_accounts(email)
                WHERE email IS NOT NULL AND TRIM(email) <> ''
            """
        )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS managed_account_audit (
            audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor_account_id TEXT NOT NULL,
            target_account_id TEXT NOT NULL,
            timestamp_bangkok TEXT NOT NULL,
            field TEXT NOT NULL,
            old_value TEXT,
            new_value TEXT
        )
        """
    )

    for role_name in ("admin", "librarian"):
        rows = connection.execute(
            "SELECT username, permissions_json FROM managed_accounts WHERE role = ?",
            (role_name,),
        ).fetchall()
        for row in rows:
            permissions = json.loads(row["permissions_json"])
            if "view_reports" not in permissions:
                permissions.append("view_reports")
                connection.execute(
                    "UPDATE managed_accounts SET permissions_json = ? WHERE username = ?",
                    (json.dumps(permissions), row["username"]),
                )

    member_rows = connection.execute(
        "SELECT username, permissions_json FROM managed_accounts WHERE role = ?",
        ("member",),
    ).fetchall()
    for row in member_rows:
        permissions = [
            permission
            for permission in json.loads(row["permissions_json"])
            if permission not in ("view_reports", "ดูรายงาน")
        ]
        connection.execute(
            "UPDATE managed_accounts SET permissions_json = ? WHERE username = ?",
            (json.dumps(permissions), row["username"]),
        )

    seeded_emails: set[str] = set()
    for user in USERS:
        normalized_email = (user.email or "").strip()
        normalized_email_key = normalized_email.casefold()
        if normalized_email_key:
            if normalized_email_key in seeded_emails:
                persisted_email = None
            else:
                persisted_email = normalized_email
                seeded_emails.add(normalized_email_key)
        else:
            persisted_email = None
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
                persisted_email,
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


def validate_password(password: str | None) -> bool:
    """ตรวจรหัสผ่านตาม NFR-SEC-01."""
    if not password or len(password) < 5:
        return False
    return any(character.isalpha() for character in password) and any(
        character.isdigit() for character in password
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
        permissions=("manage_users", "manage_books", "view_reports"),
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
    return next((item for item in USERS if item.username == username), None)


def _append_audit(
    connection: sqlite3.Connection,
    *,
    actor_username: str,
    target_username: str,
    field: str,
    old_value: str | None,
    new_value: str | None,
) -> None:
    timestamp = datetime.now(ZoneInfo("Asia/Bangkok")).isoformat()
    connection.execute(
        """
        INSERT INTO managed_account_audit (
            actor_account_id, target_account_id, timestamp_bangkok,
            field, old_value, new_value
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            actor_username,
            target_username,
            timestamp,
            field,
            old_value,
            new_value,
        ),
    )


def list_account_audit() -> list[dict[str, Any]]:
    connection = _member_connection()
    try:
        rows = connection.execute(
            """
            SELECT audit_id, actor_account_id, target_account_id,
                   timestamp_bangkok, field, old_value, new_value
            FROM managed_account_audit
            ORDER BY audit_id ASC
            """
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


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
    actor_username: str | None = None,
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
        if actor_username:
            if user.first_name != updated.first_name:
                _append_audit(connection, actor_username=actor_username, target_username=username, field="first_name", old_value=user.first_name, new_value=updated.first_name)
            if user.last_name != updated.last_name:
                _append_audit(connection, actor_username=actor_username, target_username=username, field="last_name", old_value=user.last_name, new_value=updated.last_name)
            if user.email != updated.email:
                _append_audit(connection, actor_username=actor_username, target_username=username, field="email", old_value=user.email or None, new_value=updated.email or None)
            if user.phone != updated.phone:
                _append_audit(connection, actor_username=actor_username, target_username=username, field="phone", old_value=user.phone, new_value=updated.phone)
        connection.execute(
            """
            UPDATE managed_accounts
            SET email = ?, first_name = ?, last_name = ?, phone = ?
            WHERE username = ?
            """,
            (normalized_email, updated.first_name, updated.last_name, updated.phone, username),
        )
        connection.commit()
    except sqlite3.OperationalError:
        connection.rollback()
        return None, {"code": "audit_failed", "message": "ไม่สามารถบันทึกการเปลี่ยนแปลงได้"}
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()
    for index, current in enumerate(USERS):
        if current.username == username:
            USERS[index] = updated
            break
    if status == "Suspended":
        from .session import revoke_sessions
        revoke_sessions(username)
    return get_managed_account(username), None


ROLE_PERMISSIONS = {
    "member": ("view_profile", "borrow_book"),
    "librarian": ("view_profile", "borrow_book", "manage_books", "view_reports"),
    "admin": ("view_profile", "borrow_book", "manage_users", "manage_books", "view_reports"),
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
        connection.execute("BEGIN IMMEDIATE")
        if user.role != updated.role:
            _append_audit(connection, actor_username=actor_username, target_username=username, field="role", old_value=user.role, new_value=updated.role)
        if tuple(user.permissions) != updated.permissions:
            _append_audit(connection, actor_username=actor_username, target_username=username, field="permissions", old_value=",".join(user.permissions), new_value=",".join(updated.permissions))
        connection.execute(
            """
            UPDATE managed_accounts
            SET role = ?, permissions_json = ?
            WHERE username = ?
            """,
            (normalized_role, json.dumps(list(updated.permissions)), username),
        )
        connection.commit()
    except sqlite3.OperationalError:
        connection.rollback()
        return None, {"code": "audit_failed", "message": "ไม่สามารถบันทึกการเปลี่ยนแปลงได้"}
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()
    for index, current in enumerate(USERS):
        if current.username == username:
            USERS[index] = updated
            break
    if updated.account_status == "Suspended":
        from .session import revoke_sessions
        revoke_sessions(username)
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
        if user.account_status != status:
            _append_audit(connection, actor_username=actor_username, target_username=username, field="account_status", old_value=user.account_status, new_value=status)
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
    if updated.account_status == "Suspended":
        from .session import revoke_sessions
        revoke_sessions(username)
    return get_managed_account(username), None


def apply_managed_account_change(
    username: str,
    *,
    actor_username: str,
    first_name: str,
    last_name: str,
    email: str,
    phone: str,
    role: str | None,
    permissions: list[str] | None,
    status: str | None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if username == actor_username:
        return None, {"code": "permission_required", "message": "คุณไม่มีสิทธิ์ดำเนินการนี้"}
    actor = find_user_by_username(actor_username)
    user = find_user_by_username(username)
    if actor is None or "manage_users" not in actor.permissions:
        return None, {"code": "permission_required", "message": "คุณไม่มีสิทธิ์ดำเนินการนี้"}
    if user is None:
        return None, {"code": "account_not_found", "message": "ไม่พบบัญชีผู้ใช้"}

    normalized_email = email.strip()
    if not normalized_email and user.user_type == "external":
        return None, {"code": "email_required", "message": "อีเมลห้ามว่างสำหรับบุคคลภายนอก"}
    if normalized_email:
        for existing in USERS:
            if existing.username != username and existing.email.strip().casefold() == normalized_email.casefold():
                return None, {"code": "email_duplicate", "message": "อีเมลซ้ำกับบัญชีอื่น"}

    normalized_role = user.role
    normalized_permissions = tuple(user.permissions)
    if role is not None:
        normalized_role = role.strip().casefold()
        if normalized_role not in ROLE_PERMISSIONS:
            return None, {"code": "invalid_role", "message": "Role ไม่ถูกต้อง"}
        normalized_permissions = tuple(dict.fromkeys(permissions or []))
        if any(permission not in ROLE_PERMISSIONS[normalized_role] for permission in normalized_permissions):
            return None, {"code": "permission_required", "message": "คุณไม่มีสิทธิ์ดำเนินการนี้"}
        if any(permission not in actor.permissions for permission in normalized_permissions):
            return None, {"code": "permission_required", "message": "คุณไม่มีสิทธิ์ดำเนินการนี้"}

    normalized_status = status or user.account_status
    if normalized_status not in ("Active", "Suspended"):
        return None, {"code": "invalid_status", "message": "สถานะบัญชีไม่ถูกต้อง"}
    active_admin_count = sum(
        1 for item in USERS
        if item.role == "admin" and item.account_status == "Active"
    )
    if normalized_status == "Suspended" and user.role == "admin" and user.account_status == "Active" and active_admin_count <= 1:
        return None, {"code": "permission_required", "message": "คุณไม่มีสิทธิ์ดำเนินการนี้"}
    if user.role == "admin" and normalized_role != "admin" and active_admin_count <= 1:
        return None, {"code": "permission_required", "message": "คุณไม่มีสิทธิ์ดำเนินการนี้"}

    updated = User(
        username=user.username,
        email=normalized_email,
        student_id=user.student_id,
        password_hash=user.password_hash,
        user_type=user.user_type,
        role=normalized_role,
        permissions=normalized_permissions,
        account_status=normalized_status,
        overdue_count=user.overdue_count,
        unpaid_fine_count=user.unpaid_fine_count,
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        phone=phone.strip(),
    )
    connection = _member_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        changes = (
            ("first_name", user.first_name, updated.first_name),
            ("last_name", user.last_name, updated.last_name),
            ("email", user.email or None, updated.email or None),
            ("phone", user.phone, updated.phone),
            ("role", user.role, updated.role),
            ("permissions", ",".join(user.permissions), ",".join(updated.permissions)),
            ("account_status", user.account_status, updated.account_status),
        )
        for field, old_value, new_value in changes:
            if old_value != new_value:
                _append_audit(
                    connection,
                    actor_username=actor_username,
                    target_username=username,
                    field=field,
                    old_value=str(old_value) if old_value is not None else None,
                    new_value=str(new_value) if new_value is not None else None,
                )
        connection.execute(
            """
            UPDATE managed_accounts
            SET email = ?, first_name = ?, last_name = ?, phone = ?,
                role = ?, permissions_json = ?, account_status = ?
            WHERE username = ?
            """,
            (
                normalized_email or None,
                updated.first_name,
                updated.last_name,
                updated.phone,
                updated.role,
                json.dumps(list(updated.permissions)),
                updated.account_status,
                username,
            ),
        )
        connection.commit()
    except sqlite3.OperationalError:
        connection.rollback()
        return None, {"code": "audit_failed", "message": "ไม่สามารถบันทึกการเปลี่ยนแปลงได้"}
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()
    for index, current in enumerate(USERS):
        if current.username == username:
            USERS[index] = updated
            break
    if updated.account_status == "Suspended":
        from .session import revoke_sessions
        revoke_sessions(username)
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


def register_user(
    *,
    first_name: str | None,
    last_name: str | None,
    date_of_birth: str | None,
    national_id: str | None,
    phone: str | None,
    email: str | None,
    password: str | None,
    student_id: str | None = None,
) -> dict[str, Any]:
    """สมัครสมาชิกตาม AC-สมัครสมาชิก-/-เข้าสู่ระบบ-01."""
    first_name = (first_name or "").strip()
    last_name = (last_name or "").strip()
    national_id = (national_id or "").strip()
    phone = (phone or "").strip()
    email = (email or "").strip() or None
    student_id = (student_id or "").strip() or None

    try:
        parsed_birth = date.fromisoformat((date_of_birth or "").strip())
    except ValueError:
        return {
            "success": False,
            "code": "invalid_birth_date",
            "message": "กรุณาระบุวันเกิดให้ถูกต้อง",
        }

    if not first_name or not last_name or not national_id or not phone:
        return {
            "success": False,
            "code": "required_fields",
            "message": "กรุณากรอกข้อมูลบังคับให้ครบ",
        }
    if not validate_password(password):
        return {
            "success": False,
            "code": "invalid_password",
            "message": "รหัสผ่านต้องยาวอย่างน้อย 5 ตัวและมีตัวอักษรกับตัวเลข",
        }

    user_type = "external"
    role = "member"
    permissions = ("view_profile",)
    username = (email or national_id)
    resolved_student_id = None

    if student_id:
        lookup_status = registry.lookup_student(student_id, national_id)
        if lookup_status == "timeout":
            return {
                "success": False,
                "code": "registry_unavailable",
                "message": "ระบบทะเบียนไม่ตอบสนอง โปรดลองใหม่ภายหลัง",
            }
        if lookup_status == "found":
            record = registry.get_student(student_id)
            if record is not None and record.status == "Active":
                user_type = "student"
                role = "student"
                permissions = ("view_profile", "borrow_book")
                resolved_student_id = student_id
                first_name = record.first_name or first_name
                last_name = record.last_name or last_name
                parsed_birth = record.date_of_birth

    if student_id is None:
        staff_status = registry.lookup_staff(national_id)
        if staff_status == "timeout":
            return {
                "success": False,
                "code": "registry_unavailable",
                "message": "ระบบทะเบียนไม่ตอบสนอง โปรดลองใหม่ภายหลัง",
            }
        if staff_status == "found":
            record = registry.get_staff(national_id)
            if record is not None:
                user_type = "staff"
                role = "librarian"
                permissions = ("view_profile", "borrow_book", "manage_books")
                email = record.email or email
                first_name = record.first_name or first_name
                last_name = record.last_name or last_name
                parsed_birth = record.date_of_birth

    if user_type == "external" and not email:
        return {
            "success": False,
            "code": "email_required",
            "message": "อีเมลห้ามว่างสำหรับบุคคลภายนอก",
        }

    normalized_username = (
        resolved_student_id
        if user_type == "student"
        else (email or national_id)
    )
    for existing in USERS:
        if existing.username.casefold() == normalized_username.casefold():
            return {
                "success": False,
                "code": "account_exists",
                "message": "บัญชีนี้มีอยู่แล้ว",
            }
        if email and existing.email.casefold() == email.casefold():
            return {
                "success": False,
                "code": "email_duplicate",
                "message": "อีเมลนี้ถูกใช้โดยบัญชีอื่นแล้ว",
            }

    display_name = f"{first_name} {last_name}".strip()
    created = User(
        username=normalized_username,
        email=email or "",
        student_id=resolved_student_id,
        password_hash=hash_password(password or ""),
        user_type=user_type,
        role=role,
        permissions=permissions,
        account_status="Active",
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        national_id=national_id,
        date_of_birth=parsed_birth,
    )
    USERS.append(created)
    return {
        "success": True,
        "message": "สมัครสมาชิกสำเร็จ กรุณาเข้าสู่ระบบ",
        "user": created.to_dict(),
        "display_name": display_name,
    }


def login_user(username: str | None = None, password: str | None = None, email: str | None = None) -> dict[str, Any]:
    identifier = (username or email or "").strip()
    user = _find_login_user(identifier)
    if not user or not password or not verify_password(password, user.password_hash):
        return {
            "success": False,
            "message": "รหัสผ่านหรือชื่อผู้ใช้ไม่ถูกต้อง",
            "session_timeout_seconds": 600,
        }
    connection = _member_connection()
    try:
        row = connection.execute(
            """
            SELECT email, role, permissions_json, account_status,
                   first_name, last_name, phone
            FROM managed_accounts
            WHERE username = ?
            """,
            (user.username,),
        ).fetchone()
    finally:
        connection.close()
    if row is not None:
        user = User(
            username=user.username,
            email=row["email"] or "",
            student_id=user.student_id,
            password_hash=user.password_hash,
            user_type=user.user_type,
            role=row["role"],
            permissions=tuple(json.loads(row["permissions_json"])),
            account_status=row["account_status"],
            overdue_count=user.overdue_count,
            unpaid_fine_count=user.unpaid_fine_count,
            first_name=row["first_name"],
            last_name=row["last_name"],
            phone=row["phone"],
        )
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


def reset_password(
    student_id: str | None = None,
    new_password: str | None = None,
    national_id: str | None = None,
    phone: str | None = None,
    date_of_birth: str | None = None,
    identifier: str | None = None,
) -> dict[str, Any]:
    """ยืนยันตัวตนและตั้งรหัสผ่านใหม่สำหรับนักศึกษา/บุคลากร/บุคคลภายนอก."""
    user = None
    if student_id:
        user = _find_user(student_id)
    elif identifier:
        user = _find_login_user(identifier)
    elif national_id:
        user = next(
            (
                item
                for item in USERS
                if item.national_id == national_id.strip()
                or item.email.casefold() == national_id.strip().casefold()
            ),
            None,
        )

    if not user:
        return {"success": False, "message": "ข้อมูลนักศึกษาไม่ถูกต้อง", "can_reset": False}

    has_verification_fields = bool(national_id or phone or date_of_birth)
    if has_verification_fields:
        if not national_id or not phone or not date_of_birth:
            return {"success": False, "message": "ข้อมูลยืนยันตัวตนไม่ครบ", "can_reset": False}
        try:
            parsed_birth = date.fromisoformat(date_of_birth)
        except ValueError:
            return {"success": False, "message": "ข้อมูลยืนยันตัวตนไม่ถูกต้อง", "can_reset": False}

        if user.user_type == "student":
            if not student_id:
                return {"success": False, "message": "ข้อมูลนักศึกษาไม่ถูกต้อง", "can_reset": False}
            lookup_status = registry.lookup_student(student_id, national_id)
            if lookup_status == "timeout":
                return {
                    "success": False,
                    "message": "ระบบทะเบียนไม่ตอบสนอง โปรดลองใหม่ภายหลัง",
                    "can_reset": False,
                }
            record = registry.get_student(student_id)
            if lookup_status != "found" or record is None:
                return {"success": False, "message": "ข้อมูลยืนยันตัวตนไม่ถูกต้อง", "can_reset": False}
            if record.phone and record.phone != phone:
                return {"success": False, "message": "ข้อมูลยืนยันตัวตนไม่ถูกต้อง", "can_reset": False}
            if record.date_of_birth != parsed_birth:
                return {"success": False, "message": "ข้อมูลยืนยันตัวตนไม่ถูกต้อง", "can_reset": False}
        elif user.user_type == "staff":
            lookup_status = registry.lookup_staff(national_id)
            if lookup_status == "timeout":
                return {
                    "success": False,
                    "message": "ระบบทะเบียนไม่ตอบสนอง โปรดลองใหม่ภายหลัง",
                    "can_reset": False,
                }
            record = registry.get_staff(national_id)
            if lookup_status != "found" or record is None:
                return {"success": False, "message": "ข้อมูลยืนยันตัวตนไม่ถูกต้อง", "can_reset": False}
            if record.phone and record.phone != phone:
                return {"success": False, "message": "ข้อมูลยืนยันตัวตนไม่ถูกต้อง", "can_reset": False}
            if record.date_of_birth != parsed_birth:
                return {"success": False, "message": "ข้อมูลยืนยันตัวตนไม่ถูกต้อง", "can_reset": False}
        else:
            if user.national_id != national_id or user.phone != phone or user.date_of_birth != parsed_birth:
                return {"success": False, "message": "ข้อมูลยืนยันตัวตนไม่ถูกต้อง", "can_reset": False}

    if new_password:
        if not validate_password(new_password):
            return {
                "success": False,
                "message": "รหัสผ่านต้องยาวอย่างน้อย 5 ตัวและมีตัวอักษรกับตัวเลข",
                "can_reset": False,
            }
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
            phone=user.phone,
            national_id=user.national_id,
            date_of_birth=user.date_of_birth,
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
