from __future__ import annotations

import json
from datetime import date, datetime, timezone
from typing import Callable, Literal

from sqlalchemy import select
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from app.database import DATABASE_URL
from app.ingestion.logging import get_logger
from app.ingestion.providers import (
    EquityBarProvider,
    EquityBarRecord,
    ProviderResponse,
    YFINANCE_BACKFILL_START,
    YieldProvider,
    YieldRecord,
)
from app.ingestion.repository import (
    record_raw_ingestion,
    upsert_equity_bars,
    upsert_yield_observations,
)
from app.ingestion.quality import (
    check_nyse_expected_dates,
    check_stale_feed,
    check_zscore_outliers,
)
from app.ingestion.storage import RawArchive
from app.models import EquityBar, Instrument, YieldObservation

LOGGER = get_logger(__name__)

FRED_SERIES_BY_TENOR = {
    "1M": "DGS1MO",
    "3M": "DGS3MO",
    "6M": "DGS6MO",
    "1Y": "DGS1",
    "2Y": "DGS2",
    "5Y": "DGS5",
    "10Y": "DGS10",
    "30Y": "DGS30",
}


class IngestionService:
    def __init__(self, session: Session, archive: RawArchive | None = None) -> None:
        self.session = session
        self.archive = archive or RawArchive()

    def persist(
        self, source: str, response: ProviderResponse, kind: Literal["yield", "equity"]
    ) -> int:
        requested_at = datetime.now(timezone.utc)
        payload_path, payload_sha256 = self.archive.store(
            source, response.resource, response.payload, requested_at
        )
        if kind == "yield":
            count = upsert_yield_observations(
                self.session, [record for record in response.records if isinstance(record, YieldRecord)]
            )
        else:
            count = upsert_equity_bars(
                self.session,
                [record for record in response.records if isinstance(record, EquityBarRecord)],
            )
        record_raw_ingestion(
            self.session,
            source=source,
            resource=response.resource,
            requested_at=requested_at,
            status_code=response.status_code,
            payload_path=payload_path,
            payload_sha256=payload_sha256,
            record_count=count,
        )
        self.session.commit()
        LOGGER.info(
            "ingestion_persisted",
            extra={"source": source, "resource": response.resource, "record_count": count},
        )
        return count

    def run_quality_checks(self, *, kind: Literal["yield", "equity"], resource: str) -> None:
        """Persist feed quality issues using date-over-date changes as outlier inputs."""
        if not hasattr(self.session, "scalar"):
            return

        instrument = self.session.scalar(
            select(Instrument).where(
                Instrument.symbol == resource,
                Instrument.asset_class == ("treasury_yield" if kind == "yield" else "equity_etf"),
            )
        )
        instrument_id = instrument.id if instrument else None
        if kind == "yield":
            observations = self.session.scalars(
                select(YieldObservation)
                .where(YieldObservation.tenor == resource, YieldObservation.value.is_not(None))
                .order_by(YieldObservation.observation_date)
            ).all()
            dates = [row.observation_date for row in observations]
            timestamps_and_values = [
                (
                    datetime.combine(row.observation_date, datetime.min.time(), tzinfo=timezone.utc),
                    float(row.value),
                )
                for row in observations
            ]
        else:
            observations = self.session.scalars(
                select(EquityBar)
                .where(EquityBar.symbol == resource, EquityBar.interval == "1d")
                .order_by(EquityBar.timestamp)
            ).all()
            dates = [row.timestamp.date() for row in observations]
            timestamps_and_values = [(row.timestamp, float(row.close)) for row in observations]

        now = datetime.now(timezone.utc)
        check_nyse_expected_dates(
            self.session,
            instrument_id=instrument_id,
            symbol=resource,
            observed_dates=dates,
            start=dates[0] if dates else now.date(),
            end=now.date(),
        )
        check_stale_feed(
            self.session,
            instrument_id=instrument_id,
            resource=resource,
            latest_at=timestamps_and_values[-1][0] if timestamps_and_values else None,
            as_of=now,
        )
        changes = [
            (timestamp, value - previous_value)
            for (_, previous_value), (timestamp, value) in zip(
                timestamps_and_values, timestamps_and_values[1:]
            )
        ]
        check_zscore_outliers(
            self.session,
            instrument_id=instrument_id,
            resource=resource,
            values=changes,
        )
        self.session.commit()

    def ingest_yields(
        self, provider: YieldProvider, *, series_id: str, tenor: str, start: date
    ) -> int:
        try:
            count = self.persist(provider.source, provider.fetch(series_id, tenor, start), "yield")
            self.run_quality_checks(kind="yield", resource=tenor)
            return count
        except Exception as error:
            self.record_failure(provider.source, series_id, error)
            raise

    def ingest_equity_bars(
        self,
        provider: EquityBarProvider,
        *,
        symbol: str,
        start: date = YFINANCE_BACKFILL_START,
    ) -> int:
        try:
            count = self.persist(provider.source, provider.fetch(symbol, start), "equity")
            self.run_quality_checks(kind="equity", resource=symbol)
            return count
        except Exception as error:
            self.record_failure(provider.source, symbol, error)
            raise

    def record_failure(self, source: str, resource: str, error: Exception) -> None:
        requested_at = datetime.now(timezone.utc)
        payload = json.dumps({"error": str(error)}).encode()
        payload_path, payload_sha256 = self.archive.store(source, resource, payload, requested_at)
        record_raw_ingestion(
            self.session,
            source=source,
            resource=resource,
            requested_at=requested_at,
            status_code=None,
            payload_path=payload_path,
            payload_sha256=payload_sha256,
            record_count=None,
            error_message=str(error),
        )
        self.session.commit()
        LOGGER.error("ingestion_failed", extra={"source": source, "resource": resource})


def run_ingestion(
    *,
    start: date = YFINANCE_BACKFILL_START,
    session_factory: Callable[[], Session] | None = None,
) -> None:
    """Run the scheduled Treasury and active-equity daily backfill."""

    if session_factory is None:
        engine = create_engine(DATABASE_URL)
        session_factory = sessionmaker(bind=engine)

    from app.ingestion.providers import FredClient, YFinanceClient

    with session_factory() as session:
        service = IngestionService(session)
        fred = FredClient()
        for tenor, series_id in FRED_SERIES_BY_TENOR.items():
            service.ingest_yields(fred, series_id=series_id, tenor=tenor, start=start)

        yfinance = YFinanceClient()
        symbols = session.scalars(
            select(Instrument.symbol).where(
                Instrument.asset_class == "equity_etf", Instrument.active.is_(True)
            )
        )
        for symbol in symbols:
            service.ingest_equity_bars(yfinance, symbol=symbol, start=start)
