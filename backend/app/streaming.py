import asyncio
import json
import logging
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

import httpx
import websockets
from sqlalchemy.dialects.postgresql import insert

from app.main import SessionLocal, prices
from app.models import EquityBar


logger = logging.getLogger(__name__)
SYMBOLS = ("SPY", "QQQ", "VTI", "AGG", "TLT")


@dataclass
class MinuteBar:
    timestamp: datetime
    symbol: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int

    def update(self, price: Decimal, volume: int) -> None:
        self.high = max(self.high, price)
        self.low = min(self.low, price)
        self.close = price
        self.volume += volume


class TradeAggregator:
    def __init__(self) -> None:
        self.bars: dict[tuple[str, datetime], MinuteBar] = {}

    def add(self, symbol: str, price: float, volume: float, milliseconds: int) -> MinuteBar:
        timestamp = datetime.fromtimestamp(milliseconds / 1000, tz=timezone.utc).replace(
            second=0, microsecond=0
        )
        key = (symbol, timestamp)
        decimal_price = Decimal(str(price))
        if key not in self.bars:
            self.bars[key] = MinuteBar(
                timestamp, symbol, decimal_price, decimal_price, decimal_price, decimal_price, int(volume)
            )
        else:
            self.bars[key].update(decimal_price, int(volume))
        return self.bars[key]

    def pop_completed(self, now: datetime) -> list[MinuteBar]:
        cutoff = now.replace(second=0, microsecond=0)
        keys = [key for key in self.bars if key[1] < cutoff]
        return [self.bars.pop(key) for key in keys]


def persist_bars(bars: list[MinuteBar]) -> None:
    if not bars:
        return
    with SessionLocal.begin() as session:
        for bar in bars:
            statement = insert(EquityBar).values(
                timestamp=bar.timestamp,
                symbol=bar.symbol,
                interval="1m",
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
            )
            session.execute(
                statement.on_conflict_do_update(
                    index_elements=["timestamp", "symbol", "interval"],
                    set_={
                        "high": statement.excluded.high,
                        "low": statement.excluded.low,
                        "close": statement.excluded.close,
                        "volume": statement.excluded.volume,
                    },
                )
            )


async def latest_quotes(token: str) -> None:
    async with httpx.AsyncClient(timeout=10) as client:
        for symbol in SYMBOLS:
            response = await client.get(
                "https://finnhub.io/api/v1/quote", params={"symbol": symbol, "token": token}
            )
            response.raise_for_status()
            quote = response.json()
            await prices.broadcast({"symbol": symbol, "price": quote["c"], "source": "quote"})


async def stream_trades() -> None:
    token = os.environ["FINNHUB_API_KEY"]
    aggregator = TradeAggregator()
    backoff = 1
    while True:
        try:
            async with websockets.connect(
                f"wss://ws.finnhub.io?token={token}", ping_interval=20, ping_timeout=20
            ) as socket:
                for symbol in SYMBOLS:
                    await socket.send(json.dumps({"type": "subscribe", "symbol": symbol}))
                backoff = 1
                async for message in socket:
                    payload = json.loads(message)
                    for trade in payload.get("data", []):
                        bar = aggregator.add(trade["s"], trade["p"], trade["v"], trade["t"])
                        await prices.broadcast(
                            {"symbol": bar.symbol, "price": float(bar.close), "source": "trade"}
                        )
                    persist_bars(aggregator.pop_completed(datetime.now(timezone.utc)))
        except (websockets.WebSocketException, httpx.HTTPError, OSError) as error:
            logger.warning("market stream disconnected", extra={"error": str(error), "retry": backoff})
            try:
                await latest_quotes(token)
            except httpx.HTTPError:
                logger.exception("quote fallback failed")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)
