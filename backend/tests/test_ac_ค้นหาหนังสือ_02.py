from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_AC_ค้นหาหนังสือ_02():
    response = client.get("/api/books/search", params={"query": "คำค้นที่ไม่มีผลลัพธ์"})
    assert response.status_code == 200
    payload = response.json()
    assert payload == {"results": [], "message": "ไม่พบหนังสือที่ค้นหา"}
