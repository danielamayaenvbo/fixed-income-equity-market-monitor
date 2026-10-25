from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pandas as pd

from app.ingestion.providers import (
    EquityBarRecord,
    FredClient,
    ProviderResponse,
    YFINANCE_BACKFILL_START,
    YFinanceClient,
    YieldRecord,
)
from app.ingestion.quality import (
    check_nyse_expected_dates,
    check_stale_feed,
    check_zscore_outliers,
)
from app.ingestion.service import IngestionService


class FakeSession:
    def __init__(self) -> None:
        self.added = []
        self.statements = []
        self.commits = 0

    def add(self, value) -> None:
        self.added.append(value)

    def execute(self, statement) -> None:
        self.statements.append(statement)

    def commit(self) -> None:
        self.commits += 1


class FakeArchive:
    def __init__(self) -> None:
        self.stored = []

    def store(self, source, resource, payload, requested_at):
        self.stored.append((source, resource, payload))
        return f"data/raw/{source}/payload.json", "a" * 64


def test_fred_client_parses_missing_values_without_network() -> None:
    payload = b'{"observations":[{"date":"2024-01-02","value":"4.25"},{"date":"2024-01-03","value":"."}]}'
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, content=payload)))

    response = FredClient(api_key="test-key", client=client).fetch("DGS10", "10Y", date(2024, 1, 1))

    assert response.resource == "DGS10"
    assert [(record.observation_date, record.value) for record in response.records] == [
        (date(2024, 1, 2), Decimal("4.25")),
        (date(2024, 1, 3), None),
    ]


def test_yfinance_daily_backfill_normalizes_bars_without_network() -> None:
    frame = pd.DataFrame(
        {
            "Open": [100.0],
            "High": [102.0],
            "Low": [99.0],
            "Close": [101.0],
            "Volume": [1000],
        },
        index=pd.DatetimeIndex(["2024-01-02"], tz="America/New_York"),
    )

    class Ticker:
        def __init__(self, symbol):
            self.symbol = symbol

        def history(self, **kwargs):
            assert kwargs["start"] == YFINANCE_BACKFILL_START.isoformat()
            assert kwargs["interval"] == "1d"
            return frame

    response = YFinanceClient(ticker_factory=Ticker).fetch("SPY")

    assert response.records == [
        EquityBarRecord(
            timestamp=datetime(2024, 1, 2, 5, tzinfo=timezone.utc),
            symbol="SPY",
            interval="1d",
            open=Decimal("100.0"),
            high=Decimal("102.0"),
            low=Decimal("99.0"),
            close=Decimal("101.0"),
            volume=1000,
        )
    ]
    assert b'"columns"' in response.payload


def test_ingestion_persists_raw_log_and_postgres_upsert() -> None:
    session = FakeSession()
    archive = FakeArchive()
    service = IngestionService(session, archive)
    response = ProviderResponse(
        resource="DGS10",
        status_code=200,
        payload=b'{"observations":[]}',
        records=[YieldRecord(date(2024, 1, 2), "10Y", Decimal("4.1"), "DGS10")],
    )

    assert service.persist("fred", response, "yield") == 1
    assert archive.stored == [("fred", "DGS10", b'{"observations":[]}')]
    assert len(session.statements) == 1
    assert "ON CONFLICT" in str(session.statements[0])
    assert session.added[0].record_count == 1
    assert session.commits == 1


def test_ingestion_uses_provider_interface() -> None:
    session = FakeSession()
    response = ProviderResponse(
        resource="DGS10",
        status_code=200,
        payload=b'{"observations":[]}',
        records=[YieldRecord(date(2024, 1, 2), "10Y", Decimal("4.1"), "DGS10")],
    )

    class Provider:
        source = "fred"

        def fetch(self, series_id, tenor, start):
            assert (series_id, tenor, start) == ("DGS10", "10Y", date(2015, 1, 1))
            return response

    assert IngestionService(session, FakeArchive()).ingest_yields(
        Provider(), series_id="DGS10", tenor="10Y", start=date(2015, 1, 1)
    ) == 1


def test_quality_checks_persist_expected_issues() -> None:
    session = FakeSession()

    class Calendar:
        def valid_days(self, start_date, end_date):
            return pd.DatetimeIndex(["2024-01-02", "2024-01-03"], tz="UTC")

    missing = check_nyse_expected_dates(
        session,
        instrument_id=1,
        symbol="SPY",
        observed_dates=[date(2024, 1, 2)],
        start=date(2024, 1, 2),
        end=date(2024, 1, 3),
        calendar=Calendar(),
    )
    stale = check_stale_feed(
        session,
        instrument_id=1,
        resource="SPY",
        latest_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        as_of=datetime(2024, 1, 5, tzinfo=timezone.utc),
        max_age=timedelta(days=1),
    )
    outliers = check_zscore_outliers(
        session,
        instrument_id=1,
        resource="SPY",
        values=[
            (datetime(2024, 1, 1, tzinfo=timezone.utc), 1.0),
            (datetime(2024, 1, 2, tzinfo=timezone.utc), 1.0),
            (datetime(2024, 1, 3, tzinfo=timezone.utc), 10.0),
        ],
        threshold=1.0,
    )

    assert len(missing) == len(stale) == len(outliers) == 1
    assert [issue.issue_type for issue in session.added] == [
        "missing_dates",
        "stale_feed",
        "outlier",
    ]
