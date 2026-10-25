from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.ingestion.providers import EquityBarRecord, YieldRecord
from app.models import EquityBar, RawIngestionLog, YieldObservation


def upsert_yield_observations(session: Session, records: Sequence[YieldRecord]) -> int:
    if not records:
        return 0
    values = [
        {
            "observation_date": record.observation_date,
            "tenor": record.tenor,
            "value": record.value,
            "source_series_id": record.source_series_id,
        }
        for record in records
    ]
    statement = insert(YieldObservation).values(values)
    session.execute(
        statement.on_conflict_do_update(
            index_elements=["observation_date", "tenor"],
            set_={
                "value": statement.excluded.value,
                "source_series_id": statement.excluded.source_series_id,
                "ingested_at": datetime.now().astimezone(),
            },
        )
    )
    return len(values)


def upsert_equity_bars(session: Session, records: Sequence[EquityBarRecord]) -> int:
    if not records:
        return 0
    values = [
        {
            "timestamp": record.timestamp,
            "symbol": record.symbol,
            "interval": record.interval,
            "open": record.open,
            "high": record.high,
            "low": record.low,
            "close": record.close,
            "volume": record.volume,
        }
        for record in records
    ]
    statement = insert(EquityBar).values(values)
    session.execute(
        statement.on_conflict_do_update(
            index_elements=["timestamp", "symbol", "interval"],
            set_={
                column: getattr(statement.excluded, column)
                for column in ("open", "high", "low", "close", "volume")
            }
            | {"ingested_at": datetime.now().astimezone()},
        )
    )
    return len(values)


def record_raw_ingestion(
    session: Session,
    *,
    source: str,
    resource: str,
    requested_at: datetime,
    status_code: int | None,
    payload_path: str,
    payload_sha256: str,
    record_count: int | None,
    error_message: str | None = None,
) -> RawIngestionLog:
    entry = RawIngestionLog(
        source=source,
        resource=resource,
        requested_at=requested_at,
        status_code=status_code,
        payload_path=payload_path,
        payload_sha256=payload_sha256,
        record_count=record_count,
        error_message=error_message,
    )
    session.add(entry)
    return entry
