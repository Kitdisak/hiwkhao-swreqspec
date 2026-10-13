from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_AC_สมัครสมาชิก_เข้าสู่ระบบ_02():
    response = client.post("/api/auth/login", json={"username": "s12345", "password": "wrong-password"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert payload["message"] == "รหัสผ่านหรือชื่อผู้ใช้ไม่ถูกต้อง"
