"""v171 D8: admin chart, risk, watchlist and earnings warm-ups through the layer."""
import contextlib
import os
import threading
import time

import pandas as pd
import pytest

from swingbot import config
from swingbot.admin import freshness, watchlist_rows
from swingbot.core.marketdata import daily_delta, data, data_refresh, data_store
from swingbot.core.marketdata.providers import router
from swingbot.core.marketdata.shared import kinds, layer
from swingbot.core.marketdata.shared.kinds import Asker, DataKind
from tests.helpers import make_ohlcv


@pytest.fixture
def env(monkeypatch):
    """on mode; files/staleness/refresh/lease all observable."""
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    st = {"files": {}, "stale": set(), "refreshed": [], "leases": [], "held": True}

    def read(t, basis=None):
        assert basis == daily_delta.BASIS_YF
        return st["files"].get(t)

    def refresh(t, asker):
        st["refreshed"].append((t, asker))
        st["files"][t] = make_ohlcv([100.0 + i for i in range(10)])
        st["stale"].discard(t)

    @contextlib.contextmanager
    def lease(kind, symbol, *, asker, deadline_s=30.0):
        st["leases"].append((kind, symbol, asker))
        yield st["held"]

    monkeypatch.setattr(daily_delta, "read_daily", read)
    monkeypatch.setattr(freshness, "_daily_stale", lambda t: t in st["stale"] or t not in st["files"])
    monkeypatch.setattr(freshness, "_refresh_yf_daily", refresh)
    monkeypatch.setattr(layer, "lease", lease)
    return st


def test_a_fresh_yfinance_file_is_read_with_no_fetch_and_no_lease(env):
    env["files"]["AAPL"] = make_ohlcv([1.0, 2.0])
    assert len(freshness.page_daily(["aapl"])["AAPL"]) == 2
    assert env["refreshed"] == [] and env["leases"] == []


def test_a_missing_file_is_fetched_once_under_the_daily_lease_at_admin_page(env):
    out = freshness.page_daily(["AAPL"])
    assert "AAPL" in out
    assert env["leases"] == [(DataKind.DAILY_BARS, "AAPL", Asker.ADMIN_PAGE)]
    assert env["refreshed"] == [("AAPL", Asker.ADMIN_PAGE)]


def test_a_lost_lease_serves_the_file_on_disk_without_fetching(env):
    env["files"]["AAPL"] = make_ohlcv([1.0, 2.0])
    env["stale"].add("AAPL")
    env["held"] = False
    assert len(freshness.page_daily(["AAPL"])["AAPL"]) == 2 and env["refreshed"] == []


def test_a_lost_lease_with_no_file_still_fetches(env):
    env["held"] = False                                   # failed open, or a holder that wrote nothing
    assert "AAPL" in freshness.page_daily(["AAPL"]) and len(env["refreshed"]) == 1


def test_period_trims_to_todays_span(env):
    env["files"]["AAPL"] = make_ohlcv([100.0] * 600)
    out = freshness.page_daily(["AAPL"], period="6mo")["AAPL"]
    assert out.index[-1] == env["files"]["AAPL"].index[-1]
    assert (out.index[-1] - out.index[0]).days <= 183


def test_spot_keeps_todays_batch_path(env, monkeypatch):
    seen = []
    monkeypatch.setattr(data, "get_daily_data_batch",
                        lambda t, period="2y": seen.append((list(t), period)) or {})
    freshness.page_daily(["XAUUSD"], period="6mo")
    assert seen == [(["XAUUSD"], "6mo")] and env["leases"] == []


def test_refresh_fills_a_missing_file_at_full_depth_and_a_stale_one_incrementally(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(data_store, "cache_path", lambda t, i, base_dir=None: str(tmp_path / f"{t}.csv"))
    monkeypatch.setattr(data_refresh, "refresh_symbol",
                        lambda t, tf: calls.append(("full", t, router.current_asker())))
    monkeypatch.setattr(data_store, "update_cache",
                        lambda syms, interval: calls.append(("delta", syms, interval)))
    freshness._refresh_yf_daily("AAPL", Asker.ADMIN_PAGE)
    (tmp_path / "AAPL.csv").write_text("Date,Close\n")
    freshness._refresh_yf_daily("AAPL", Asker.ADMIN_PAGE)
    assert calls == [("full", "AAPL", Asker.ADMIN_PAGE), ("delta", ["AAPL"], "1d")]


def test_daily_staleness_follows_the_page_window(monkeypatch, tmp_path):
    path = tmp_path / "AAPL.csv"
    path.write_text("Date,Close\n")
    old = time.time() - 120
    os.utime(path, (old, old))
    monkeypatch.setattr(data_store, "cache_path", lambda t, i, base_dir=None: str(path))
    monkeypatch.setattr(config, "QUOTE_MAX_AGE_ADMIN_S", 60)
    monkeypatch.setattr(config, "SCAN_CACHE_MAX_AGE_HOURS", 6)
    monkeypatch.setattr(data, "is_us_market_active", lambda: True)
    assert freshness._daily_stale("AAPL") is True
    monkeypatch.setattr(data, "is_us_market_active", lambda: False)
    assert freshness._daily_stale("AAPL") is False
    with kinds.fresh_request():
        monkeypatch.setattr(data, "is_us_market_active", lambda: True)
        assert freshness._daily_stale("AAPL") is True


def test_chart_risk_and_watchlist_read_page_daily_when_on(admin_app, env, monkeypatch):
    from swingbot.admin import app as app_mod
    from swingbot.admin.api_v1 import risk
    asked = []
    monkeypatch.setattr(freshness, "page_daily",
                        lambda t, period="2y": asked.append((list(t), period)) or {s: make_ohlcv([1.0, 2.0]) for s in t})
    monkeypatch.setattr(data, "get_daily_data", lambda *a, **k: pytest.fail("live chart fetch"))
    monkeypatch.setattr(data, "get_daily_data_batch", lambda *a, **k: pytest.fail("live batch fetch"))
    monkeypatch.setattr(watchlist_rows, "get_daily_data_batch", lambda *a, **k: pytest.fail("live batch fetch"))
    monkeypatch.setattr(watchlist_rows, "_cached_daily", lambda t: None)
    monkeypatch.setattr(watchlist_rows, "is_us_market_active", lambda: False)
    assert len(app_mod._ohlcv_frame("AAPL")) == 2
    assert set(risk._risk_bars(["AAPL", "SPY"])) == {"AAPL", "SPY"}
    watchlist_rows.build_market_rows(["MSFT"])
    assert asked == [(["AAPL"], "2y"), (["AAPL", "SPY"], "2y"), (["MSFT"], "6mo")]


def test_off_mode_keeps_the_live_readers(admin_app, monkeypatch):
    from swingbot.admin import app as app_mod
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "off")
    monkeypatch.setattr(freshness, "page_daily", lambda *a, **k: pytest.fail("layer used"))
    monkeypatch.setattr(data, "get_daily_data", lambda t: make_ohlcv([5.0, 6.0, 7.0]))
    assert len(app_mod._ohlcv_frame("AAPL")) == 3


def test_the_watchlist_earnings_warm_up_runs_at_admin_page(admin_app, monkeypatch):
    from swingbot.admin.api_v1 import watchlist
    from swingbot.core.market import events
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")
    done, seen = threading.Event(), []

    def docs(tickers, *, asker, max_age_s=None):
        seen.append((list(tickers), asker))
        done.set()
        return {}
    monkeypatch.setattr(events, "_earnings_docs", docs)
    monkeypatch.setattr(events, "_never_reports", lambda t: False)
    events._earnings_datetime_cache.clear()
    watchlist._next_earnings(["AAPL", "MSFT"])
    assert done.wait(5) and seen == [(["AAPL", "MSFT"], Asker.ADMIN_PAGE)]
