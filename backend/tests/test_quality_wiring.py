from datetime import date, datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.ingestion.service import IngestionService
from app.models import DataQualityIssue, Instrument, YieldObservation


def test_quality_checks_persist_issues_for_an_ingested_series() -> None:
    engine = create_engine("sqlite://")
    Instrument.__table__.create(engine)
    YieldObservation.__table__.create(engine)
    DataQualityIssue.__table__.create(engine)
    with Session(engine) as session:
        session.add(
            Instrument(
                symbol="10Y",
                asset_class="treasury_yield",
                display_name="10-Year Treasury Yield",
                currency="USD",
                active=True,
            )
        )
        session.add_all(
            [
                YieldObservation(
                    observation_date=date(2020, 1, day),
                    tenor="10Y",
                    value=value,
                    source_series_id="DGS10",
                    ingested_at=datetime.now(timezone.utc),
                )
                for day, value in enumerate((1, 1, 1, 1, 1, 1, 1, 10), start=2)
            ]
        )
        session.commit()

        IngestionService(session).run_quality_checks(kind="yield", resource="10Y")

        issues = session.query(DataQualityIssue).all()
        assert issues
        assert {issue.issue_type for issue in issues} <= {"missing_dates", "stale_feed", "outlier"}
