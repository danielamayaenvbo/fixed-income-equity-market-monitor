from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Protocol, Sequence

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.ingestion.logging import get_logger

YFINANCE_BACKFILL_START = date(2015, 1, 1)
LOGGER = get_logger(__name__)


class ProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class YieldRecord:
    observation_date: date
    tenor: str
    value: Decimal | None
    source_series_id: str


@dataclass(frozen=True)
class EquityBarRecord:
    timestamp: datetime
    symbol: str
    interval: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int


@dataclass(frozen=True)
class ProviderResponse:
    resource: str
    status_code: int
    payload: bytes
    records: Sequence[YieldRecord | EquityBarRecord]


class YieldProvider(Protocol):
    source: str

    def fetch(self, series_id: str, tenor: str, start: date) -> ProviderResponse: ...


class EquityBarProvider(Protocol):
    source: str

    def fetch(self, symbol: str, start: date = YFINANCE_BACKFILL_START) -> ProviderResponse: ...


class FredClient:
    """FRED observations client. The API key is obtained only from the process environment."""

    source = "fred"
    endpoint = "https://api.stlouisfed.org/fred/series/observations"

    def __init__(self, api_key: str | None = None, client: httpx.Client | None = None) -> None:
        self.api_key = api_key if api_key is not None else os.environ.get("FRED_API_KEY")
        self.client = client or httpx.Client(timeout=30.0)

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, ProviderError)),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def fetch(self, series_id: str, tenor: str, start: date) -> ProviderResponse:
        if not self.api_key:
            raise ProviderError("FRED_API_KEY is not configured")
        try:
            response = self.client.get(
                self.endpoint,
                params={
                    "series_id": series_id,
                    "api_key": self.api_key,
                    "file_type": "json",
                    "observation_start": start.isoformat(),
                },
            )
            response.raise_for_status()
        except httpx.HTTPError:
            LOGGER.warning("fred_request_failed", extra={"series_id": series_id})
            raise

        try:
            data = response.json()
            observations = data["observations"]
        except (KeyError, ValueError, TypeError) as error:
            raise ProviderError(f"FRED response for {series_id} was malformed") from error
        records = [
            YieldRecord(
                observation_date=date.fromisoformat(item["date"]),
                tenor=tenor,
                value=None if item["value"] == "." else Decimal(item["value"]),
                source_series_id=series_id,
            )
            for item in observations
        ]
        return ProviderResponse(
            resource=series_id,
            status_code=response.status_code,
            payload=response.content,
            records=records,
        )


class YFinanceClient:
    """Daily Yahoo Finance history provider isolated behind the equity provider protocol."""

    source = "yfinance"

    def __init__(self, ticker_factory: object | None = None) -> None:
        self._ticker_factory = ticker_factory

    @retry(
        retry=retry_if_exception_type(ProviderError),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    def fetch(self, symbol: str, start: date = YFINANCE_BACKFILL_START) -> ProviderResponse:
        ticker_factory = self._ticker_factory
        if ticker_factory is None:
            import yfinance

            ticker_factory = yfinance.Ticker
        try:
            frame = ticker_factory(symbol).history(
                start=start.isoformat(), interval="1d", auto_adjust=False, actions=False
            )
        except Exception as error:
            raise ProviderError(f"yfinance request failed for {symbol}") from error
        if frame.empty:
            raise ProviderError(f"yfinance returned no daily bars for {symbol}")
        payload = frame.to_json(orient="split", date_format="iso").encode()
        records: list[EquityBarRecord] = []
        for timestamp, row in frame.iterrows():
            timestamp = timestamp.to_pydatetime()
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            else:
                timestamp = timestamp.astimezone(timezone.utc)
            records.append(
                EquityBarRecord(
                    timestamp=timestamp,
                    symbol=symbol,
                    interval="1d",
                    open=Decimal(str(row["Open"])),
                    high=Decimal(str(row["High"])),
                    low=Decimal(str(row["Low"])),
                    close=Decimal(str(row["Close"])),
                    volume=int(row["Volume"]),
                )
            )
        return ProviderResponse(
            resource=symbol,
            status_code=200,
            payload=payload,
            records=records,
        )
