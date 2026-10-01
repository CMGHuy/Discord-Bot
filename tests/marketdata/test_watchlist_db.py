"""Watchlist CRUD against Postgres."""
import pytest

from swingbot import config
from swingbot.core.marketdata import watchlist as wl


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def db_url(db_engine, monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL", db_engine.url.render_as_string(hide_password=False))
    from swingbot.core.db.engine import reset_engine
    reset_engine()


def test_db_stage_crud(data_dir, monkeypatch, db_committed, db_url):
    wl.add_ticker("MSFT")
    wl.add_ticker("AAPL")
    wl.add_ticker("AAPL")
    assert wl.load_watchlist() == ["AAPL", "MSFT"]
    assert wl.remove_ticker("AAPL") == ["MSFT"]
    assert wl.remove_ticker("NOPE") == ["MSFT"]
    assert wl.clear_watchlist() == []


def test_save_replaces_whole_db_set(data_dir, monkeypatch, db_committed, db_url):
    wl.save_watchlist(["AAPL", "MSFT"])
    wl.save_watchlist(["NVDA"])
    assert wl.load_watchlist() == ["NVDA"]
