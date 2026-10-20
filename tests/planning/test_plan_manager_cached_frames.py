"""v171 D3/D8: the plan manager's daily frames come from the shared cache plus
one forming-bar refresh per ticker per 60 s tick, not per-plan 2y downloads."""
import pandas as pd
import pytest

from swingbot import config
from swingbot.core.marketdata import daily_delta, data
from swingbot.core.marketdata.shared.kinds import Asker
from swingbot.core.planning import plan_manager as pm
from tests.helpers import make_ohlcv


@pytest.fixture
def calls(monkeypatch):
    rec = {"delta": [], "legacy": []}
    frame = make_ohlcv([100.0 + i for i in range(40)], start="2026-08-20")

    def delta(tickers, *, asker, **kw):
        rec["delta"].append((list(tickers), asker))
        return {t.upper(): frame.copy() for t in tickers if t != "XAUUSD"}

    def legacy(ticker, period="2y"):
        rec["legacy"].append(ticker)
        return frame.copy()
    monkeypatch.setattr(daily_delta, "delta_update", delta)
    monkeypatch.setattr(data, "get_daily_data", legacy)
    monkeypatch.setattr(pm, "_SHARED_DAILY", {})
    rec["now"] = [1000.0]
    monkeypatch.setattr(pm, "_clock", lambda: rec["now"][0])
    rec["frame"] = frame
    return rec


def test_flag_off_keeps_the_per_call_download(monkeypatch, calls):
    monkeypatch.setattr(config, "DAILY_DELTA_FETCH", False)
    pm._daily_frame("AAPL"); pm._live_atr("AAPL"); pm._bars_since("AAPL", "2026-09-01T14:00:00+00:00")
    assert calls["legacy"] == ["AAPL", "AAPL", "AAPL"] and calls["delta"] == []


def test_one_refresh_per_ticker_per_tick_serves_all_three_helpers(monkeypatch, calls):
    monkeypatch.setattr(config, "DAILY_DELTA_FETCH", True)
    df = pm._daily_frame("AAPL")
    atr = pm._live_atr("AAPL")
    bars = pm._bars_since("AAPL", "2026-09-01T14:00:00+00:00")
    assert calls["delta"] == [(["AAPL"], Asker.STOP_MONITOR)] and calls["legacy"] == []
    assert df.equals(calls["frame"]) and atr > 0
    assert bars == int((calls["frame"].index > pd.Timestamp("2026-09-01 10:00")).sum())
    calls["now"][0] += 61.0
    pm._daily_frame("AAPL")
    assert len(calls["delta"]) == 2                                       # next tick refreshes


def test_the_memo_hands_out_copies(monkeypatch, calls):
    monkeypatch.setattr(config, "DAILY_DELTA_FETCH", True)
    pm._daily_frame("AAPL")["Close"] = 0.0
    assert pm._daily_frame("AAPL")["Close"].iloc[-1] == calls["frame"]["Close"].iloc[-1]


def test_spot_and_misses_fall_back_to_todays_download(monkeypatch, calls):
    monkeypatch.setattr(config, "DAILY_DELTA_FETCH", True)
    pm._daily_frame("XAUUSD")
    assert calls["legacy"] == ["XAUUSD"]


def test_a_delta_error_reads_the_cache_without_memoising(monkeypatch, calls):
    monkeypatch.setattr(config, "DAILY_DELTA_FETCH", True)
    monkeypatch.setattr(daily_delta, "delta_update", lambda *a, **k: (_ for _ in ()).throw(OSError("x")))
    cached = make_ohlcv([5.0, 6.0, 7.0])
    monkeypatch.setattr(daily_delta, "read_daily", lambda t, basis=None: cached)
    assert pm._daily_frame("AAPL").equals(cached) and pm._SHARED_DAILY == {}
