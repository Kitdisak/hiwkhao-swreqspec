from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_AC_ค้นหาหนังสือ_01():
    response = client.get("/api/books/search", params={"query": "ซอฟต์"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["message"] is None
    assert payload["results"]
    assert payload["results"][0]["title"] == "การออกแบบซอฟต์แวร์"
    assert payload["results"][0]["item_identifier"] == "BK-001"
