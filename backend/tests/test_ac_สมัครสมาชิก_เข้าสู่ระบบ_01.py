from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_AC_สมัครสมาชิก_เข้าสู่ระบบ_01():
    response = client.post("/api/auth/login", json={"username": "s12345", "password": "pass1234"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["message"] == "เข้าสู่ระบบสำเร็จ"
    assert payload["redirect"] == "/"
    assert payload["user"]["role"] == "student"
