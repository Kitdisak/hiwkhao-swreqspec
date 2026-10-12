from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_AC_ค้นหาหนังสือ_03():
    response = client.get(
        "/api/books/search",
        params={"category": "005", "author": "สมชาย"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["message"] is None
    assert len(payload["results"]) == 1
    assert payload["results"][0]["title"] == "การออกแบบซอฟต์แวร์"
    assert payload["results"][0]["ddc_category"] == "005.1"
