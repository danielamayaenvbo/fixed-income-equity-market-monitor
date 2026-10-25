from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from datetime import date, datetime, time, timedelta, timezone
from statistics import mean, pstdev

import pandas_market_calendars as mcal
from sqlalchemy.orm import Session

from app.models import DataQualityIssue


def _persist(
    session: Session,
    *,
    issue_type: str,
    severity: str,
    instrument_id: int | None,
    observed_at: datetime,
    details: dict[str, object],
) -> DataQualityIssue:
    issue = DataQualityIssue(
        issue_type=issue_type,
        severity=severity,
        instrument_id=instrument_id,
        observed_at=observed_at,
        details=json.dumps(details, sort_keys=True, default=str),
        created_at=observed_at,
    )
    session.add(issue)
    return issue


def check_nyse_expected_dates(
    session: Session,
    *,
    instrument_id: int | None,
    symbol: str,
    observed_dates: Iterable[date],
    start: date,
    end: date,
    calendar: object | None = None,
) -> list[DataQualityIssue]:
    """Persist one missing-date issue for a daily equity feed over NYSE sessions."""

    nyse = calendar or mcal.get_calendar("NYSE")
    expected = {timestamp.date() for timestamp in nyse.valid_days(start_date=start, end_date=end)}
    missing = sorted(expected - set(observed_dates))
    if not missing:
        return []
    return [
        _persist(
            session,
            issue_type="missing_dates",
            severity="warning",
            instrument_id=instrument_id,
            observed_at=datetime.combine(end, time.min, tzinfo=timezone.utc),
            details={"symbol": symbol, "missing_dates": [value.isoformat() for value in missing]},
        )
    ]


def check_stale_feed(
    session: Session,
    *,
    instrument_id: int | None,
    resource: str,
    latest_at: datetime | None,
    as_of: datetime,
    max_age: timedelta = timedelta(days=2),
) -> list[DataQualityIssue]:
    if latest_at is not None and latest_at.tzinfo is None:
        latest_at = latest_at.replace(tzinfo=timezone.utc)
    if latest_at is not None and as_of - latest_at <= max_age:
        return []
    return [
        _persist(
            session,
            issue_type="stale_feed",
            severity="error",
            instrument_id=instrument_id,
            observed_at=as_of,
            details={
                "resource": resource,
                "latest_at": latest_at.isoformat() if latest_at else None,
                "max_age_seconds": int(max_age.total_seconds()),
            },
        )
    ]


def check_zscore_outliers(
    session: Session,
    *,
    instrument_id: int | None,
    resource: str,
    values: Sequence[tuple[datetime, float]],
    threshold: float = 4.0,
) -> list[DataQualityIssue]:
    """Flag values whose population z-score meets the supplied absolute threshold."""

    if len(values) < 2:
        return []
    numbers = [value for _, value in values]
    standard_deviation = pstdev(numbers)
    if standard_deviation == 0:
        return []
    average = mean(numbers)
    issues = []
    for observed_at, value in values:
        z_score = (value - average) / standard_deviation
        if abs(z_score) >= threshold:
            issues.append(
                _persist(
                    session,
                    issue_type="outlier",
                    severity="warning",
                    instrument_id=instrument_id,
                    observed_at=observed_at,
                    details={
                        "resource": resource,
                        "value": value,
                        "mean": average,
                        "z_score": z_score,
                        "threshold": threshold,
                    },
                )
            )
    return issues
