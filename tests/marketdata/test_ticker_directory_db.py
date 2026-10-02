"""A regenerable cache: reads may fall back, writes still go where the stage
says."""
import pytest

from swingbot import config
from swingbot.core.db.repositories.ticker_directory import TickerDirectoryRepository
from swingbot.core.marketdata import ticker_directory as td


@pytest.fixture
def db_stage(tmp_path, monkeypatch, db_committed):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    from swingbot.core.db.engine import reset_engine
    monkeypatch.setattr(
        config, "DATABASE_URL",
        db_committed.engine.url.render_as_string(hide_password=False))
    reset_engine()
    monkeypatch.setattr(td, "_directory", None)
    monkeypatch.setattr(td, "_symbol_map", {})
    monkeypatch.setattr(td, "_loaded_at", 0.0)
    yield
    reset_engine()


ROWS = [{"symbol": "AAPL", "name": "Apple Inc."},
        {"symbol": "MSFT", "name": "Microsoft Corporation"},
        {"symbol": "MSTR", "name": "MicroStrategy Inc."}]


def test_replace_then_read_back(db_stage):
    repo = TickerDirectoryRepository()
    repo.replace(ROWS)
    assert {r["symbol"] for r in repo.all_rows()} == {"AAPL", "MSFT", "MSTR"}


def test_replace_removes_delisted_symbols(db_stage):
    repo = TickerDirectoryRepository()
    repo.replace(ROWS)
    repo.replace([{"symbol": "AAPL", "name": "Apple Inc."}])
    assert [r["symbol"] for r in repo.all_rows()] == ["AAPL"]


def test_lookup_name_reads_rows(db_stage):
    TickerDirectoryRepository().replace(ROWS)
    assert td.lookup_name("AAPL") == "Apple Inc."


def test_lookup_name_is_none_for_an_unknown_symbol(db_stage):
    TickerDirectoryRepository().replace(ROWS)
    assert td.lookup_name("NOTREAL") is None


def test_search_matches_symbol_prefix(db_stage):
    TickerDirectoryRepository().replace(ROWS)
    hits = {h["symbol"] for h in td.search_tickers("MS", limit=10)}
    assert {"MSFT", "MSTR"} <= hits


def test_search_matches_company_name(db_stage):
    TickerDirectoryRepository().replace(ROWS)
    hits = {h["symbol"] for h in td.search_tickers("Apple", limit=10)}
    assert "AAPL" in hits


def test_search_honours_the_limit(db_stage):
    TickerDirectoryRepository().replace(ROWS)
    assert len(td.search_tickers("M", limit=1)) == 1


def test_an_unreachable_database_degrades_to_a_refetch_not_a_crash(
        db_stage, monkeypatch):
    """The spec's one read-side exemption: a regenerable cache may fall back to
    recomputation. Trading state may not."""
    monkeypatch.setattr(config, "DATABASE_URL", "")
    from swingbot.core.db import engine as dbengine
    dbengine.reset_engine()
    monkeypatch.setattr(td, "_build_directory", lambda: ROWS)
    assert td.lookup_name("AAPL") == "Apple Inc."
    dbengine.reset_engine()
