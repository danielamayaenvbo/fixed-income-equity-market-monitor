from contextlib import asynccontextmanager
import asyncio
from datetime import date, datetime, timedelta, timezone
import os

from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.database import DATABASE_URL
from app.models import DataQualityIssue, EquityBar, YieldObservation
from sqlalchemy import create_engine


engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


def get_session():
    with SessionLocal() as session:
        yield session


class YieldPoint(BaseModel):
    tenor: str
    value: float | None


class YieldHistoryPoint(YieldPoint):
    date: date


class EquityBarPoint(BaseModel):
    timestamp: datetime
    symbol: str
    interval: str
    open: float
    high: float
    low: float
    close: float
    volume: int


class QualityIssuePoint(BaseModel):
    id: int
    issue_type: str
    severity: str
    observed_at: datetime
    details: str
    resolved_at: datetime | None


class ConnectionManager:
    def __init__(self) -> None:
        self.connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self.connections.discard(websocket)

    async def broadcast(self, payload: dict) -> None:
        for connection in list(self.connections):
            try:
                await connection.send_json(payload)
            except WebSocketDisconnect:
                self.disconnect(connection)


prices = ConnectionManager()


@asynccontextmanager
async def lifespan(_: FastAPI):
    stream_task = None
    if os.getenv("FINNHUB_API_KEY"):
        from app.streaming import stream_trades

        stream_task = asyncio.create_task(stream_trades())
    try:
        yield
    finally:
        if stream_task:
            stream_task.cancel()
        engine.dispose()


app = FastAPI(title="Fixed Income & Equity Market Monitor", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/yields/curve", response_model=list[YieldPoint])
def yield_curve(
    observation_date: date = Query(alias="date"), session: Session = Depends(get_session)
) -> list[YieldPoint]:
    rows = session.scalars(
        select(YieldObservation)
        .where(YieldObservation.observation_date == observation_date)
        .order_by(YieldObservation.tenor)
    ).all()
    return [YieldPoint(tenor=row.tenor, value=float(row.value) if row.value is not None else None) for row in rows]


@app.get("/yields/history", response_model=list[YieldHistoryPoint])
def yield_history(
    tenor: str, start: date, end: date, session: Session = Depends(get_session)
) -> list[YieldHistoryPoint]:
    if start > end:
        raise HTTPException(422, "start must not be after end")
    rows = session.scalars(
        select(YieldObservation)
        .where(
            YieldObservation.tenor == tenor,
            YieldObservation.observation_date.between(start, end),
        )
        .order_by(YieldObservation.observation_date)
    ).all()
    return [
        YieldHistoryPoint(
            date=row.observation_date,
            tenor=row.tenor,
            value=float(row.value) if row.value is not None else None,
        )
        for row in rows
    ]


@app.get("/spreads/2s10s")
def two_ten_spread(start: date, end: date, session: Session = Depends(get_session)) -> list[dict]:
    if start > end:
        raise HTTPException(422, "start must not be after end")
    two_year = YieldObservation.__table__.alias("two_year")
    ten_year = YieldObservation.__table__.alias("ten_year")
    rows = session.execute(
        select(
            ten_year.c.observation_date.label("date"),
            (ten_year.c.value - two_year.c.value).label("spread"),
        )
        .join(two_year, two_year.c.observation_date == ten_year.c.observation_date)
        .where(
            ten_year.c.tenor == "10Y",
            two_year.c.tenor == "2Y",
            ten_year.c.observation_date.between(start, end),
        )
        .order_by(ten_year.c.observation_date)
    )
    return [{"date": row.date, "spread": float(row.spread)} for row in rows]


@app.get("/equities/{symbol}/history", response_model=list[EquityBarPoint])
def equity_history(
    symbol: str,
    interval: str = Query(pattern="^(1d|1m)$"),
    start: datetime | None = None,
    end: datetime | None = None,
    session: Session = Depends(get_session),
) -> list[EquityBarPoint]:
    statement: Select = select(EquityBar).where(
        EquityBar.symbol == symbol.upper(), EquityBar.interval == interval
    )
    if start:
        statement = statement.where(EquityBar.timestamp >= start)
    if end:
        statement = statement.where(EquityBar.timestamp <= end)
    rows = session.scalars(statement.order_by(EquityBar.timestamp)).all()
    return [
        EquityBarPoint(
            timestamp=row.timestamp,
            symbol=row.symbol,
            interval=row.interval,
            open=float(row.open),
            high=float(row.high),
            low=float(row.low),
            close=float(row.close),
            volume=row.volume,
        )
        for row in rows
    ]


@app.get("/analytics/volatility")
def volatility(
    symbol: str,
    window: int = Query(60, ge=2, le=252),
    session: Session = Depends(get_session),
) -> list[dict]:
    rows = session.scalars(
        select(EquityBar)
        .where(EquityBar.symbol == symbol.upper(), EquityBar.interval == "1d")
        .order_by(EquityBar.timestamp)
    ).all()
    values = [float(row.close) for row in rows]
    result = []
    for index in range(window, len(values)):
        returns = [values[i] / values[i - 1] - 1 for i in range(index - window + 1, index + 1)]
        mean = sum(returns) / len(returns)
        variance = sum((item - mean) ** 2 for item in returns) / (len(returns) - 1)
        result.append({"date": rows[index].timestamp.date(), "volatility": (variance**0.5) * (252**0.5)})
    return result


@app.get("/analytics/correlation")
def correlation(
    window: int = Query(60, ge=2, le=252), symbol: str = "SPY", session: Session = Depends(get_session)
) -> list[dict]:
    equity = session.scalars(
        select(EquityBar)
        .where(EquityBar.symbol == symbol.upper(), EquityBar.interval == "1d")
        .order_by(EquityBar.timestamp)
    ).all()
    yields = {
        row.observation_date: float(row.value)
        for row in session.scalars(
            select(YieldObservation).where(YieldObservation.tenor == "10Y")
        )
        if row.value is not None
    }
    paired = []
    previous_close = None
    previous_yield = None
    for row in equity:
        current_yield = yields.get(row.timestamp.date())
        if previous_close is not None and current_yield is not None and previous_yield is not None:
            paired.append((row.timestamp.date(), float(row.close) / previous_close - 1, current_yield - previous_yield))
        previous_close = float(row.close)
        if current_yield is not None:
            previous_yield = current_yield
    result = []
    for index in range(window, len(paired) + 1):
        points = paired[index - window : index]
        xs, ys = [point[1] for point in points], [point[2] for point in points]
        x_mean, y_mean = sum(xs) / window, sum(ys) / window
        denominator = (sum((x - x_mean) ** 2 for x in xs) * sum((y - y_mean) ** 2 for y in ys)) ** 0.5
        if denominator:
            result.append({"date": points[-1][0], "correlation": sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / denominator})
    return result


@app.get("/data-quality/issues", response_model=list[QualityIssuePoint])
def quality_issues(
    open_only: bool = True, session: Session = Depends(get_session)
) -> list[QualityIssuePoint]:
    statement = select(DataQualityIssue).order_by(DataQualityIssue.created_at.desc())
    if open_only:
        statement = statement.where(DataQualityIssue.resolved_at.is_(None))
    return [
        QualityIssuePoint.model_validate(row, from_attributes=True)
        for row in session.scalars(statement.limit(100))
    ]


@app.websocket("/ws/prices")
async def price_socket(websocket: WebSocket) -> None:
    await prices.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        prices.disconnect(websocket)
