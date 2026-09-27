"""v106 characterization: with ALPACA_ENABLED off, every live-path fetch
returns exactly what it did before the provider router existed, and asks
yfinance for exactly the same thing. Written against the pre-router code."""
import time

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.marketdata import data as data_mod
from swingbot.core.marketdata import data_store

_FIELDS = ["Open", "High", "Low", "Close", "Volume"]
_DAYS = pd.DatetimeIndex(["2026-09-24", "2026-09-25"])


@pytest.fixture(autouse=True)
def _off(monkeypatch):
    monkeypatch.setattr(config, "ALPACA_ENABLED", False)
    monkeypatch.setattr(data_mod, "_price_cache", {})
    monkeypatch.setattr(data_mod, "_last_good_batch_price", {})


def _yf_batch_frame(tickers):
    cols = pd.MultiIndex.from_product([tickers, _FIELDS])
    return pd.DataFrame(1.0, index=_DAYS, columns=cols)


def _single_frame():
    return pd.DataFrame({"Open": [1.0, 2.0], "High": [2.0, 3.0], "Low": [0.5, 1.5],
                         "Close": [1.5, 2.5], "Volume": [100.0, 200.0]}, index=_DAYS)


def test_daily_batch_unchanged_when_disabled(monkeypatch):
    seen = {}

    def fake(*a, **k):
        seen.update(k); seen["arg"] = a[0]
        return _yf_batch_frame(["AAPL", "SAP.DE"])
    monkeypatch.setattr(data_mod.yf, "download", fake)
    out = data_mod.get_daily_data_batch(["aapl", "SAP.DE"])
    assert seen["arg"] == "AAPL SAP.DE" and seen["group_by"] == "ticker"
    assert seen["auto_adjust"] is True and seen["period"] == "2y"
    assert set(out) == {"AAPL", "SAP.DE"}
    expected = pd.DataFrame(1.0, index=_DAYS, columns=pd.Index(_FIELDS))
    for t in ("AAPL", "SAP.DE"):
        pd.testing.assert_frame_equal(out[t], expected, check_names=False)


def test_daily_single_unchanged_when_disabled(monkeypatch):
    calls = []

    def fake(sym, **k):
        calls.append((sym, k["period"], k["interval"], k["auto_adjust"]))
        return _single_frame()
    monkeypatch.setattr(data_mod.yf, "download", fake)
    out = data_mod.get_daily_data("AAPL")
    assert calls == [("AAPL", "2y", "1d", True)]
    pd.testing.assert_frame_equal(out, _single_frame())


def _minute_batch(tickers, closes):
    idx = pd.DatetimeIndex(["2026-09-25 15:58", "2026-09-25 15:59"], tz="America/New_York")
    cols = pd.MultiIndex.from_product([tickers, _FIELDS])
    df = pd.DataFrame(1.0, index=idx, columns=cols)
    for t in tickers:
        df[(t, "Close")] = closes
    return df


def test_price_batch_unchanged_when_disabled(monkeypatch):
    seen = {}

    def fake(*a, **k):
        seen.update(k); seen["arg"] = a[0]
        return _minute_batch(["AAPL"], [189.5, float("nan")])
    monkeypatch.setattr(data_mod.yf, "download", fake)
    out = data_mod.get_current_price_batch(["AAPL"], allow_stale=False)
    assert out == {"AAPL": 189.5}
    assert seen["arg"] == "AAPL" and seen["period"] == "1d" and seen["interval"] == "1m"
    assert seen["group_by"] == "ticker" and seen["prepost"] is True
    assert data_mod._last_good_batch_price["AAPL"][0] == 189.5


def test_price_detail_unchanged_when_disabled(monkeypatch):
    asked = []

    class FakeTicker:
        def __init__(self, sym):
            asked.append(sym)

        def history(self, **k):
            assert k == {"period": "1d", "interval": "1m", "prepost": True}
            return pd.DataFrame({"Close": [188.0, 190.25]})
    monkeypatch.setattr(data_mod.yf, "Ticker", FakeTicker)
    assert data_mod.get_current_price_detail("aapl", allow_stale=False) == \
        data_mod.PriceQuote(190.25, False)
    assert asked == ["AAPL"]
    assert data_mod._price_cache["AAPL"][0] == 190.25


def _hourly_frame():
    idx = pd.DatetimeIndex(["2026-09-25 09:30", "2026-09-25 10:30"], tz="America/New_York")
    return pd.DataFrame({"Open": [1.0, 2.0], "High": [2.0, 3.0], "Low": [0.5, 1.5],
                         "Close": [1.5, 2.5], "Volume": [100.0, 200.0]}, index=idx)


def test_intraday_unchanged_when_disabled(monkeypatch, tmp_path):
    calls = []

    def fake(sym, **k):
        calls.append((sym, k["period"], k["interval"], k["auto_adjust"]))
        return _hourly_frame()
    monkeypatch.setattr(data_mod.yf, "download", fake)
    out = data_store.get_intraday("AAPL", base_dir=str(tmp_path))
    assert calls == [("AAPL", "700d", "1h", True)]
    pd.testing.assert_frame_equal(out, _hourly_frame(), check_freq=False)
