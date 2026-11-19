from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import app.auth.service as auth_service
from app.auth.models import User
from app.auth.service import hash_password
from app.auth.session import SESSION_COOKIE, create_session
from app.main import app


@pytest.fixture
def member_admin(monkeypatch, tmp_path):
    monkeypatch.setenv(
        "LIBRARY_RESERVATION_DB",
        str(tmp_path / "member-management.sqlite3"),
    )
    admin = User(
        username="admin",
        email="admin@example.com",
        student_id="ADM-001",
        password_hash=hash_password("admin123"),
        user_type="staff",
        role="admin",
        permissions=("manage_users", "manage_books"),
        account_status="Active",
        first_name="ผู้",
        last_name="ดูแล",
        phone="0800000001",
    )
    member = User(
        username="student",
        email="student@example.com",
        student_id="STU-001",
        password_hash=hash_password("pass1234"),
        user_type="student",
        role="member",
        permissions=("borrow_book",),
        account_status="Active",
        first_name="สมชาย",
        last_name="ใจดี",
        phone="0800000002",
    )
    librarian = User(
        username="librarian",
        email="librarian@example.com",
        student_id="LIB-001",
        password_hash=hash_password("lib123"),
        user_type="staff",
        role="librarian",
        permissions=("manage_books",),
        account_status="Active",
        first_name="บรรณ",
        last_name="รักษ์",
        phone="0800000003",
    )
    monkeypatch.setattr(auth_service, "USERS", [admin, member, librarian])
    client = TestClient(app)
    return client, admin, member, librarian


def test_AC_จัดการสมาชิกและสิทธิ์ผู้ใช้_search_detail_and_update(member_admin):
    client, _, _, _ = member_admin
    client.cookies.set(SESSION_COOKIE, create_session("admin"))

    empty = client.get("/api/admin/users", params={"q": ""})
    assert empty.status_code == 200
    assert empty.json()["code"] == "query_required"

    found = client.get("/api/admin/users", params={"q": "สมชาย"})
    assert found.status_code == 200
    assert found.json()["results"][0]["username"] == "student"
    assert "national_id" not in found.json()["results"][0]

    detail = client.get("/api/admin/users/student")
    assert detail.status_code == 200
    assert detail.json()["account"]["phone"] == "0800000002"
    assert "national_id" not in detail.json()["account"]

    updated = client.patch(
        "/api/admin/users/student",
        json={
            "first_name": "สมศักดิ์",
            "last_name": "รักเรียน",
            "email": "new-student@example.com",
            "phone": "0811111111",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["account"]["first_name"] == "สมศักดิ์"
    assert updated.json()["account"]["phone"] == "0811111111"


def test_AC_จัดการสมาชิกและสิทธิ์ผู้ใช้_permission_rules(member_admin):
    client, _, _, librarian = member_admin

    unauthenticated = client.get("/api/admin/users", params={"q": "student"})
    assert unauthenticated.status_code == 401

    client.cookies.set(SESSION_COOKIE, create_session("librarian"))
    forbidden = client.get("/api/admin/users", params={"q": "student"})
    assert forbidden.status_code == 403
    assert forbidden.json()["message"] == "คุณไม่มีสิทธิ์ดำเนินการนี้"

    client.cookies.set(SESSION_COOKIE, create_session("admin"))
    self_update = client.patch(
        "/api/admin/users/admin",
        json={
            "first_name": "ห้าม",
            "last_name": "แก้",
            "email": "admin@example.com",
            "phone": "000",
        },
    )
    assert self_update.status_code == 403

    invalid_role = client.patch(
        "/api/admin/users/student/role",
        json={"role": "member", "permissions": ["manage_users"]},
    )
    assert invalid_role.status_code == 403
    assert invalid_role.json()["message"] == "คุณไม่มีสิทธิ์ดำเนินการนี้"


def test_AC_จัดการสมาชิกและสิทธิ์ผู้ใช้_status_rules(member_admin):
    client, _, _, _ = member_admin
    client.cookies.set(SESSION_COOKIE, create_session("admin"))

    self_suspend = client.patch(
        "/api/admin/users/admin/status",
        json={"status": "Suspended"},
    )
    assert self_suspend.status_code == 403

    suspend_member = client.patch(
        "/api/admin/users/student/status",
        json={"status": "Suspended"},
    )
    assert suspend_member.status_code == 200
    assert suspend_member.json()["account"]["account_status"] == "Suspended"

    login = client.post(
        "/api/auth/login",
        json={"username": "student", "password": "pass1234"},
    )
    assert login.json()["success"] is False
    assert login.json()["message"] == "รหัสผ่านหรือชื่อผู้ใช้ไม่ถูกต้อง"

    activate = client.patch(
        "/api/admin/users/student/status",
        json={"status": "Active"},
    )
    assert activate.status_code == 200
    assert activate.json()["account"]["account_status"] == "Active"
