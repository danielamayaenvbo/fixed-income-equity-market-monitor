from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_history_rejects_invalid_interval() -> None:
    response = TestClient(app).get("/equities/SPY/history?interval=5m")

    assert response.status_code == 422
