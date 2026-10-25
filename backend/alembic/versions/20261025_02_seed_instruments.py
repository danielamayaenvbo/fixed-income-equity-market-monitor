"""Seed supported market instruments.

Revision ID: 20261025_02
Revises: 20261025_01
Create Date: 2026-10-25 16:26:58
"""

from alembic import op
import sqlalchemy as sa


revision = "20261025_02"
down_revision = "20261025_01"
branch_labels = None
depends_on = None


instruments = sa.table(
    "instruments",
    sa.column("symbol", sa.String),
    sa.column("asset_class", sa.String),
    sa.column("display_name", sa.String),
    sa.column("currency", sa.String),
    sa.column("active", sa.Boolean),
)

EQUITY_ETFS = (
    ("SPY", "SPDR S&P 500 ETF Trust"),
    ("QQQ", "Invesco QQQ Trust"),
    ("VTI", "Vanguard Total Stock Market ETF"),
    ("AGG", "iShares Core U.S. Aggregate Bond ETF"),
    ("TLT", "iShares 20+ Year Treasury Bond ETF"),
)
TREASURY_TENORS = (
    ("1M", "1-Month Treasury Yield"),
    ("3M", "3-Month Treasury Yield"),
    ("6M", "6-Month Treasury Yield"),
    ("1Y", "1-Year Treasury Yield"),
    ("2Y", "2-Year Treasury Yield"),
    ("5Y", "5-Year Treasury Yield"),
    ("10Y", "10-Year Treasury Yield"),
    ("30Y", "30-Year Treasury Yield"),
)


def upgrade() -> None:
    op.bulk_insert(
        instruments,
        [
            {
                "symbol": symbol,
                "asset_class": "equity_etf",
                "display_name": display_name,
                "currency": "USD",
                "active": True,
            }
            for symbol, display_name in EQUITY_ETFS
        ]
        + [
            {
                "symbol": tenor,
                "asset_class": "treasury_yield",
                "display_name": display_name,
                "currency": "USD",
                "active": True,
            }
            for tenor, display_name in TREASURY_TENORS
        ],
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM instruments WHERE asset_class IN ('equity_etf', 'treasury_yield') "
            "AND symbol IN ('SPY', 'QQQ', 'VTI', 'AGG', 'TLT', '1M', '3M', '6M', '1Y', "
            "'2Y', '5Y', '10Y', '30Y')"
        )
    )
