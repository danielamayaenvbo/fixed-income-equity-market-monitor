"""Create initial market-monitor schema.

Revision ID: 20261025_01
Revises:
Create Date: 2026-10-25 15:30:30
"""

from alembic import op
import sqlalchemy as sa


revision = "20261025_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "instruments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("asset_class", sa.String(length=20), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "asset_class IN ('equity_etf', 'treasury_yield')",
            name=op.f("ck_instruments_instrument_asset_class"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_instruments")),
        sa.UniqueConstraint(
            "symbol",
            "asset_class",
            name=op.f("uq_instruments_instrument_symbol_asset_class"),
        ),
    )
    op.create_table(
        "yield_observations",
        sa.Column("observation_date", sa.Date(), nullable=False),
        sa.Column("tenor", sa.String(length=4), nullable=False),
        sa.Column("value", sa.Numeric(precision=8, scale=5), nullable=True),
        sa.Column("source_series_id", sa.String(length=20), nullable=False),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "tenor IN ('1M', '3M', '6M', '1Y', '2Y', '5Y', '10Y', '30Y')",
            name=op.f("ck_yield_observations_yield_tenor"),
        ),
        sa.PrimaryKeyConstraint("observation_date", "tenor", name=op.f("pk_yield_observations")),
    )
    op.create_index(
        "ix_yield_observations_tenor_date",
        "yield_observations",
        ["tenor", "observation_date"],
        unique=False,
    )
    op.create_table(
        "equity_bars",
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("interval", sa.String(length=2), nullable=False),
        sa.Column("open", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("high", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("low", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("close", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("volume", sa.Integer(), nullable=False),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "interval IN ('1d', '1m')", name=op.f("ck_equity_bars_equity_bar_interval")
        ),
        sa.CheckConstraint(
            '"high" >= GREATEST("open", "low", "close") AND '
            '"low" <= LEAST("open", "high", "close")',
            name=op.f("ck_equity_bars_equity_bar_ohlc_range"),
        ),
        sa.CheckConstraint("volume >= 0", name=op.f("ck_equity_bars_equity_bar_volume")),
        sa.PrimaryKeyConstraint(
            "timestamp", "symbol", "interval", name=op.f("pk_equity_bars")
        ),
    )
    op.create_index(
        "ix_equity_bars_symbol_timestamp",
        "equity_bars",
        ["symbol", "timestamp"],
        unique=False,
    )
    op.create_table(
        "raw_ingestion_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("resource", sa.String(length=100), nullable=False),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("payload_path", sa.Text(), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "source IN ('fred', 'finnhub', 'yfinance')",
            name=op.f("ck_raw_ingestion_log_raw_ingestion_source"),
        ),
        sa.CheckConstraint(
            "record_count IS NULL OR record_count >= 0",
            name=op.f("ck_raw_ingestion_log_raw_ingestion_count"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_raw_ingestion_log")),
    )
    op.create_table(
        "data_quality_issues",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("issue_type", sa.String(length=30), nullable=False),
        sa.Column("severity", sa.String(length=10), nullable=False),
        sa.Column("instrument_id", sa.Integer(), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("details", sa.Text(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "issue_type IN ('missing_dates', 'stale_feed', 'outlier')",
            name=op.f("ck_data_quality_issues_quality_issue_type"),
        ),
        sa.CheckConstraint(
            "severity IN ('info', 'warning', 'error', 'critical')",
            name=op.f("ck_data_quality_issues_quality_issue_severity"),
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instruments.id"],
            name=op.f("fk_data_quality_issues_instrument_id_instruments"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_data_quality_issues")),
    )
    op.create_index(
        "ix_data_quality_issues_open_created",
        "data_quality_issues",
        ["resolved_at", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_data_quality_issues_open_created", table_name="data_quality_issues")
    op.drop_table("data_quality_issues")
    op.drop_table("raw_ingestion_log")
    op.drop_index("ix_equity_bars_symbol_timestamp", table_name="equity_bars")
    op.drop_table("equity_bars")
    op.drop_index("ix_yield_observations_tenor_date", table_name="yield_observations")
    op.drop_table("yield_observations")
    op.drop_table("instruments")
