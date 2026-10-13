from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_AC_สมัครสมาชิก_เข้าสู่ระบบ_03():
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
