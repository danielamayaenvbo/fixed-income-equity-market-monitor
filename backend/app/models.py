from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Instrument(Base):
    __tablename__ = "instruments"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    asset_class: Mapped[str] = mapped_column(String(20), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    active: Mapped[bool] = mapped_column(nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint("symbol", "asset_class", name="instrument_symbol_asset_class"),
        CheckConstraint(
            "asset_class IN ('equity_etf', 'treasury_yield')", name="instrument_asset_class"
        ),
    )


class YieldObservation(Base):
    __tablename__ = "yield_observations"

    observation_date: Mapped[date] = mapped_column(Date, primary_key=True)
    tenor: Mapped[str] = mapped_column(String(4), primary_key=True)
    value: Mapped[Decimal | None] = mapped_column(Numeric(8, 5))
    source_series_id: Mapped[str] = mapped_column(String(20), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )

    __table_args__ = (
        Index("ix_yield_observations_tenor_date", "tenor", "observation_date"),
        CheckConstraint(
            "tenor IN ('1M', '3M', '6M', '1Y', '2Y', '5Y', '10Y', '30Y')",
            name="yield_tenor",
        ),
    )


class EquityBar(Base):
    __tablename__ = "equity_bars"

    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    interval: Mapped[str] = mapped_column(String(2), primary_key=True)
    open: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    volume: Mapped[int] = mapped_column(nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )

    __table_args__ = (
        Index("ix_equity_bars_symbol_timestamp", "symbol", "timestamp"),
        CheckConstraint("interval IN ('1d', '1m')", name="equity_bar_interval"),
        CheckConstraint(
            '"high" >= GREATEST("open", "low", "close") AND '
            '"low" <= LEAST("open", "high", "close")',
            name="equity_bar_ohlc_range",
        ),
        CheckConstraint("volume >= 0", name="equity_bar_volume"),
    )


class RawIngestionLog(Base):
    __tablename__ = "raw_ingestion_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    resource: Mapped[str] = mapped_column(String(100), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
    status_code: Mapped[int | None] = mapped_column(Integer)
    payload_path: Mapped[str] = mapped_column(Text, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    record_count: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint(
            "source IN ('fred', 'finnhub', 'yfinance')", name="raw_ingestion_source"
        ),
        CheckConstraint("record_count IS NULL OR record_count >= 0", name="raw_ingestion_count"),
    )


class DataQualityIssue(Base):
    __tablename__ = "data_quality_issues"

    id: Mapped[int] = mapped_column(primary_key=True)
    issue_type: Mapped[str] = mapped_column(String(30), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), nullable=False)
    instrument_id: Mapped[int | None] = mapped_column(ForeignKey("instruments.id"))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    details: Mapped[str] = mapped_column(Text, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )

    __table_args__ = (
        Index("ix_data_quality_issues_open_created", "resolved_at", "created_at"),
        CheckConstraint(
            "issue_type IN ('missing_dates', 'stale_feed', 'outlier')", name="quality_issue_type"
        ),
        CheckConstraint(
            "severity IN ('info', 'warning', 'error', 'critical')", name="quality_issue_severity"
        ),
    )
