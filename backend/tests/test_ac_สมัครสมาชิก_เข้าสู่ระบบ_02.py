import pytest
from fastapi.testclient import TestClient

import app.auth.service as auth_service
import app.auth.session as auth_session
from app.auth.models import User
from app.auth.service import hash_password
from app.main import app

client = TestClient(app)


@pytest.mark.parametrize(
    ("field", "identifier"),
    [
        ("username", "s12345"),
        ("email", "s12345@university.ac.th"),
        ("student_id", "STU-001"),
    ],
)
def test_AC_สมัครสมาชิก_เข้าสู่ระบบ_02_student_identifiers(field, identifier):
    response = client.post(
        "/api/auth/login",
        json={field: identifier, "password": "pass1234"},
    )
    assert response.status_code == 200
    assert response.json()["success"] is True


@pytest.fixture
def external_account(monkeypatch):
    account = User(
        username="external member",
        email="external@example.com",
        student_id=None,
        password_hash=hash_password("external-pass"),
        user_type="external",
        role="",
    )
    monkeypatch.setattr(auth_service, "USERS", [*auth_service.USERS, account])
    return account


@pytest.mark.parametrize(
    ("field", "identifier", "password"),
    [
        ("username", "admin", "admin123"),
        ("email", "admin@university.ac.th", "admin123"),
        ("username", "external member", "external-pass"),
        ("email", "external@example.com", "external-pass"),
    ],
)
def test_AC_สมัครสมาชิก_เข้าสู่ระบบ_02_non_student_identifiers(
    external_account, field, identifier, password
):
    response = client.post(
        "/api/auth/login",
        json={field: identifier, "password": password},
    )
    assert response.status_code == 200
    assert response.json()["success"] is True


@pytest.mark.parametrize(
    ("field", "identifier", "password"),
    [
        ("student_id", "ADM-001", "admin123"),
        ("student_id", "EXT-001", "external-pass"),
    ],
)
def test_AC_สมัครสมาชิก_เข้าสู่ระบบ_02_non_student_cannot_login_by_student_id(
    external_account, field, identifier, password
):
    response = client.post(
        "/api/auth/login",
        json={field: identifier, "password": password},
    )
    assert response.status_code == 200
    assert response.json()["success"] is False


def test_AC_สมัครสมาชิก_เข้าสู่ระบบ_02():
    response = client.post("/api/auth/login", json={"username": "s12345", "password": "wrong-password"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert payload["message"] == "รหัสผ่านหรือชื่อผู้ใช้ไม่ถูกต้อง"


def test_AC_สมัครสมาชิก_เข้าสู่ระบบ_01_external_registration():
    response = client.post(
        "/api/auth/register",
        json={
            "first_name": "External",
            "last_name": "Member",
            "date_of_birth": "1995-05-20",
            "national_id": "9900000000001",
            "phone": "0800000000",
            "email": "new.external@example.com",
            "password": "newpass123",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["display_name"] == "External Member"

    login = client.post(
        "/api/auth/login",
        json={"email": "new.external@example.com", "password": "newpass123"},
    )
    assert login.status_code == 200
    assert login.json()["success"] is True


@pytest.mark.parametrize("password", ["short", "1234567", "abcdef"])
def test_AC_สมัครสมาชิก_เข้าสู่ระบบ_01_password_policy(password):
    response = client.post(
        "/api/auth/register",
        json={
            "first_name": "Invalid",
            "last_name": "Password",
            "date_of_birth": "1995-05-20",
            "national_id": "9900000000002",
            "phone": "0800000001",
            "email": "invalid.password@example.com",
            "password": password,
        },
    )
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_password"


def test_AC_สมัครสมาชิก_เข้าสู่ระบบ_01_registry_timeout(monkeypatch):
    monkeypatch.setenv("LIBRARY_REGISTRY_MODE", "timeout")
    response = client.post(
        "/api/auth/register",
        json={
            "first_name": "Student",
            "last_name": "Test",
            "date_of_birth": "2000-01-01",
            "national_id": "1100000000001",
            "phone": "0800000002",
            "student_id": "STU-001",
            "password": "student123",
        },
    )
    assert response.status_code == 503
    assert response.json()["code"] == "registry_unavailable"


def test_AC_สมัครสมาชิก_เข้าสู่ระบบ_02_idle_timeout(monkeypatch):
    login = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert login.status_code == 200

    original_monotonic = auth_session.time.monotonic
    monotonic_calls = {"value": original_monotonic()}
    monkeypatch.setattr(auth_session.time, "monotonic", lambda: monotonic_calls["value"])
    monotonic_calls["value"] += auth_session.SESSION_TIMEOUT_SECONDS + 1

    response = client.get("/api/manage/books")
    assert response.status_code == 401
