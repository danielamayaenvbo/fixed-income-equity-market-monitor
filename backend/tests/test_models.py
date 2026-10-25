from app.models import DataQualityIssue, EquityBar, Instrument, RawIngestionLog, YieldObservation


def test_phase_one_tables_and_primary_keys() -> None:
    assert set(Instrument.__table__.primary_key.columns.keys()) == {"id"}
    assert set(YieldObservation.__table__.primary_key.columns.keys()) == {
        "observation_date",
        "tenor",
    }
    assert set(EquityBar.__table__.primary_key.columns.keys()) == {
        "timestamp",
        "symbol",
        "interval",
    }
    assert DataQualityIssue.__tablename__ == "data_quality_issues"
    assert RawIngestionLog.__tablename__ == "raw_ingestion_log"


def test_phase_one_query_indexes() -> None:
    yield_indexes = {index.name for index in YieldObservation.__table__.indexes}
    equity_indexes = {index.name for index in EquityBar.__table__.indexes}

    assert "ix_yield_observations_tenor_date" in yield_indexes
    assert "ix_equity_bars_symbol_timestamp" in equity_indexes
