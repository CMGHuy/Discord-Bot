"""An explicit path equal to the configured default takes the staged route
(the admin API always passes one); any other explicit path stays JSON-only."""
import os

import pytest

from swingbot import config
from swingbot.core.marketdata import watchlist
from swingbot.core.db.repositories import watchlist as repo_mod


class FakeRepo:
    def __init__(self):
        self.tickers_ = ["DBONE"]

    def tickers(self):
        return list(self.tickers_)

    def add(self, t):
        self.tickers_.append(t.upper())
        return list(self.tickers_)

    def remove(self, t):
        self.tickers_.remove(t.upper())
        return list(self.tickers_)

    def replace(self, ts):
        self.tickers_ = list(ts)
        return list(ts)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    repo = FakeRepo()
    monkeypatch.setattr(repo_mod, "watchlist_repo", lambda: repo)
    return tmp_path, repo


def test_default_path_reads_db_at_db_stage(env, monkeypatch):
    tmp_path, _ = env
    monkeypatch.setattr(config, "DB_STORES", "watchlist:db")
    assert watchlist.load_watchlist(os.path.join(tmp_path, "watchlist.json")) == ["DBONE"]


def test_default_path_add_and_remove_hit_db(env, monkeypatch):
    tmp_path, repo = env
    monkeypatch.setattr(config, "DB_STORES", "watchlist:db")
    path = os.path.join(tmp_path, "watchlist.json")
    assert watchlist.add_ticker("nvda", path) == ["DBONE", "NVDA"]
    assert watchlist.remove_ticker("DBONE", path) == ["NVDA"]
    assert repo.tickers_ == ["NVDA"]


def test_default_path_add_reaches_db_at_dual_stage(env, monkeypatch):
    tmp_path, repo = env
    monkeypatch.setattr(config, "DB_STORES", "watchlist:dual")
    watchlist.add_ticker("NVDA", os.path.join(tmp_path, "watchlist.json"))
    assert "NVDA" in repo.tickers_


def test_other_explicit_path_stays_json_only(env, monkeypatch):
    tmp_path, repo = env
    monkeypatch.setattr(config, "DB_STORES", "watchlist:db")
    other = os.path.join(tmp_path, "sub", "other.json")
    os.makedirs(os.path.dirname(other))
    watchlist.add_ticker("NVDA", other)
    assert "NVDA" in watchlist.load_watchlist(other)
    assert repo.tickers_ == ["DBONE"]
