from fastapi.testclient import TestClient

from app.api.main import app

client = TestClient(app)


def test_root_returns_ok_status() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_returns_healthy_status() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}
