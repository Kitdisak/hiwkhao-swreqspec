import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.mark.parametrize(
    ("identifier", "password"),
    [
        ("unknown-account", "admin123"),
        ("admin", "wrong-password"),
    ],
)
def test_AC_สมัครสมาชิก_เข้าสู่ระบบ_03(identifier, password):
    response = client.post(
        "/api/auth/login",
        json={"username": identifier, "password": password},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert payload["message"] == "รหัสผ่านหรือชื่อผู้ใช้ไม่ถูกต้อง"

    retry = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert retry.status_code == 200
    assert retry.json()["success"] is True


def test_AC_สมัครสมาชิก_เข้าสู่ระบบ_04_password_reset():
    response = client.post("/api/auth/password-reset", json={"student_id": "STU-001"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["can_reset"] is True
    assert payload["message"] == "ยืนยันตัวตนสำเร็จ สามารถเปลี่ยนรหัสผ่านได้"

    reset = client.post("/api/auth/password-reset", json={"student_id": "STU-001", "new_password": "new-pass-123"})
    assert reset.status_code == 200
    assert reset.json()["success"] is True

    login = client.post("/api/auth/login", json={"username": "s12345", "password": "new-pass-123"})
    assert login.status_code == 200
    assert login.json()["success"] is True
