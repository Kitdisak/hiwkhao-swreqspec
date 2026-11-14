import pytest
from fastapi.testclient import TestClient

import app.auth.service as auth_service
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
