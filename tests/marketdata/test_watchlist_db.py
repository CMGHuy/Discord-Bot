"""Watchlist stages and the explicit-path escape hatch."""
import os

import pytest

from swingbot import config
from swingbot.core.db.repositories.watchlist import WatchlistRepository
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


def test_json_stage_is_unchanged(data_dir, monkeypatch, db_conn):
    monkeypatch.setattr(config, "DB_STORES", "")
    wl.add_ticker("AAPL")
    assert "AAPL" in wl.load_watchlist()
    assert WatchlistRepository().count(conn=db_conn) == 0


def test_dual_stage_writes_both(data_dir, monkeypatch, db_committed, db_url):
    monkeypatch.setattr(config, "DB_STORES", "watchlist:dual")
    wl.add_ticker("AAPL")
    assert os.path.exists(os.path.join(data_dir, "watchlist.json"))
    assert "AAPL" in WatchlistRepository().tickers(conn=db_committed)


def test_db_stage_crud_and_no_file(data_dir, monkeypatch, db_committed, db_url):
    monkeypatch.setattr(config, "DB_STORES", "watchlist:db")
    wl.add_ticker("MSFT")
    wl.add_ticker("AAPL")
    wl.add_ticker("AAPL")
    assert wl.load_watchlist() == ["AAPL", "MSFT"]
    assert wl.remove_ticker("AAPL") == ["MSFT"]
    assert wl.remove_ticker("NOPE") == ["MSFT"]
    assert wl.clear_watchlist() == []
    assert not os.path.exists(os.path.join(data_dir, "watchlist.json"))


def test_save_replaces_whole_db_set(data_dir, monkeypatch, db_committed, db_url):
    monkeypatch.setattr(config, "DB_STORES", "watchlist:db")
    wl.save_watchlist(["AAPL", "MSFT"])
    wl.save_watchlist(["NVDA"])
    assert wl.load_watchlist() == ["NVDA"]


def test_an_explicit_path_always_uses_the_file(data_dir, monkeypatch, db_committed, db_url):
    monkeypatch.setattr(config, "DB_STORES", "watchlist:db")
    path = os.path.join(data_dir, "other.json")
    wl.save_watchlist(["ONLYFILE"], path=path)
    assert wl.load_watchlist(path=path) == ["ONLYFILE"]
    assert WatchlistRepository().tickers(conn=db_committed) == []
