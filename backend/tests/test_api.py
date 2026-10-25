from datetime import date, datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.main import app, get_session
from app.models import YieldObservation


def test_health_endpoint() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_history_rejects_invalid_interval() -> None:
    response = TestClient(app).get("/equities/SPY/history?interval=5m")

    assert response.status_code == 422


def test_two_ten_spread_skips_null_holiday_values() -> None:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    YieldObservation.__table__.create(engine)
    with Session(engine) as session:
        session.add_all(
            [
                YieldObservation(
                    observation_date=date(2024, 1, 1),
                    tenor="2Y",
                    value=None,
                    source_series_id="DGS2",
                    ingested_at=datetime.now(timezone.utc),
                ),
                YieldObservation(
                    observation_date=date(2024, 1, 1),
                    tenor="10Y",
                    value=4.0,
                    source_series_id="DGS10",
                    ingested_at=datetime.now(timezone.utc),
                ),
                YieldObservation(
                    observation_date=date(2024, 1, 2),
                    tenor="2Y",
                    value=4.2,
                    source_series_id="DGS2",
                    ingested_at=datetime.now(timezone.utc),
                ),
                YieldObservation(
                    observation_date=date(2024, 1, 2),
                    tenor="10Y",
                    value=4.0,
                    source_series_id="DGS10",
                    ingested_at=datetime.now(timezone.utc),
                ),
            ]
        )
        session.commit()

        def override_session():
            yield session

        app.dependency_overrides[get_session] = override_session
        try:
            response = TestClient(app).get("/spreads/2s10s?start=2024-01-01&end=2024-01-02")
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == [{"date": "2024-01-02", "spread": -0.2}]
