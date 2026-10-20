"""v171 D7: the index tape, Yahoo levels with labelled change-%-only ETF proxies."""
import contextlib
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.marketdata.shared import layer, tape
from swingbot.core.marketdata.shared.kinds import PROVIDER_YF, Asker, DataKind, Entry, QuoteDetail

NOW = datetime(2026, 10, 16, 15, 0, tzinfo=timezone.utc)


def _yahoo(closes: dict) -> pd.DataFrame:
    idx = pd.bdate_range("2026-10-15", periods=2)
    return pd.DataFrame({(s, "Close"): v for s, v in closes.items()}, index=idx)


@pytest.fixture(autouse=True)
def proxies(monkeypatch):
    monkeypatch.setattr(config, "TAPE_PROXY_SYMBOLS", "^GSPC=SPY,^NDX=QQQ,^DJI=DIA,^VIX=VIXY,SI=F=SLV")
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "on")


def test_proxy_map_splits_on_the_last_equals_sign(monkeypatch):
    assert tape.proxy_map() == {"^GSPC": "SPY", "^NDX": "QQQ", "^DJI": "DIA", "^VIX": "VIXY", "SI=F": "SLV"}
    monkeypatch.setattr(config, "TAPE_PROXY_SYMBOLS", "^gspc=spy,broken,,")
    assert tape.proxy_map() == {"^GSPC": "SPY"}


def test_tape_symbols_are_the_fixed_tape_and_the_proxy_map():
    assert all(tape.is_tape_symbol(s) for s in ("^GSPC", "^VIX", "SI=F"))
    assert not tape.is_tape_symbol("NVDA") and not tape.is_tape_symbol("^RUT")


def test_yahoo_rows_carry_level_and_change(monkeypatch):
    monkeypatch.setattr(tape.yf_safe, "download", lambda *a, **k: _yahoo({"^GSPC": [100.0, 102.0]}))
    assert tape._fetch_tape(["^GSPC"]) == {"^GSPC": {"symbol": "^GSPC", "price": 102.0, "change_pct": 2.0,
                                                     "is_proxy": False, "proxy_symbol": None}}


def test_a_blank_yahoo_symbol_shows_its_proxy_change_only(monkeypatch):
    monkeypatch.setattr(tape.yf_safe, "download",
                        lambda *a, **k: _yahoo({"^GSPC": [float("nan"), float("nan")]}))
    monkeypatch.setattr(tape, "market_today", lambda: date(2026, 10, 16))
    q = QuoteDetail("SPY", 505.0, NOW, None, None, None, "alpaca-iex")
    monkeypatch.setattr(tape.data, "get_quote_batch", lambda t, *, asker, **k: {"SPY": q})
    bars = pd.DataFrame({"Close": [500.0, 503.0]}, index=pd.to_datetime(["2026-10-15", "2026-10-16"]))
    monkeypatch.setattr(tape.data, "get_daily_data_batch", lambda t, period: {"SPY": bars})
    row = tape._fetch_tape(["^GSPC"])["^GSPC"]
    assert row == {"symbol": "^GSPC", "price": None, "change_pct": 1.0, "is_proxy": True, "proxy_symbol": "SPY"}


def test_blank_everywhere_is_a_miss_so_the_last_good_value_stays(monkeypatch):
    def busy(*a, **k):
        raise tape.yf_safe.DownloadBusy("busy")
    monkeypatch.setattr(tape.yf_safe, "download", busy)
    monkeypatch.setattr(tape.data, "get_quote_batch", lambda t, *, asker, **k: {})
    monkeypatch.setattr(tape.data, "get_daily_data_batch", lambda t, period: {})
    assert tape._fetch_tape(["^VIX"]) == {"^VIX": None}


def test_a_short_budget_propagates_to_the_layer(monkeypatch):
    def deferred(*a, **k):
        raise tape.yf_safe.BudgetDeferred("tier 5")
    monkeypatch.setattr(tape.yf_safe, "download", deferred)
    with pytest.raises(tape.yf_safe.BudgetDeferred):
        tape._fetch_tape(["^GSPC"])


def test_refresh_is_one_index_layer_call_for_tape_symbols_only(monkeypatch):
    calls = []

    def fake_get(kind, symbols, fetch, **kw):
        calls.append((kind, list(symbols), kw["asker"], kw["provider"], kw["max_age_s"]))
        return {s: Entry({"symbol": s, "price": 1.0, "change_pct": 0.5, "is_proxy": False,
                          "proxy_symbol": None}, NOW, "yfinance", "fetched") for s in symbols}
    monkeypatch.setattr(layer, "get", fake_get)
    out = tape.refresh_tape(["^GSPC", "NVDA", "SI=F"], max_age_s=30.0)
    assert calls == [(DataKind.INDEX_QUOTE, ["^GSPC", "SI=F"], Asker.BACKGROUND, PROVIDER_YF, 30.0)]
    assert out["^GSPC"].as_of == NOW and out["^GSPC"].change_pct == 0.5


def test_read_tape_returns_the_last_good_value_with_its_time(monkeypatch):
    doc = {"symbol": "^VIX", "price": None, "change_pct": -3.1, "is_proxy": True, "proxy_symbol": "VIXY"}
    monkeypatch.setattr(layer, "last_cached", lambda kind, syms, params="": {"^VIX": Entry(doc, NOW, "yfinance", "hit")})
    entry = tape.read_tape(["^VIX"])["^VIX"]
    assert entry == tape.TapeEntry("^VIX", None, -3.1, True, "VIXY", NOW)


@pytest.fixture
def demand_store(monkeypatch):
    rows = {}

    class Repo:
        def read_entries(self, keys, *, conn):
            return {k: rows[k] for k in keys if k in rows}

        def write_entries(self, new, *, conn):
            rows.update({r["key"]: r for r in new})
    monkeypatch.setattr(tape, "market_shared_repo", lambda: Repo())
    monkeypatch.setattr(tape, "side_connection", contextlib.nullcontext)
    return rows


def test_demand_is_recorded_for_proxy_symbols_and_expires(demand_store, monkeypatch):
    monkeypatch.setattr(tape, "_now", lambda: NOW)
    tape.record_demand(["SI=F", "NVDA", "^GSPC"])
    assert list(demand_store[tape.DEMAND_KEY]["value"]) == ["SI=F"]
    assert tape.demanded_symbols(NOW + timedelta(minutes=5)) == [*tape.TAPE_FIXED, "SI=F"]
    assert tape.demanded_symbols(NOW + timedelta(minutes=16)) == list(tape.TAPE_FIXED)


def test_a_recent_demand_is_not_rewritten_every_poll(demand_store, monkeypatch):
    monkeypatch.setattr(tape, "_now", lambda: NOW)
    tape.record_demand(["SI=F"])
    stamp = demand_store[tape.DEMAND_KEY]["fetched_at"]
    monkeypatch.setattr(tape, "_now", lambda: NOW + timedelta(seconds=20))
    tape.record_demand(["SI=F"])
    assert demand_store[tape.DEMAND_KEY]["fetched_at"] == stamp


def test_a_down_demand_store_fails_open(monkeypatch):
    def broken():
        raise RuntimeError("db down")
    monkeypatch.setattr(tape, "side_connection", broken)
    tape.record_demand(["SI=F"])
    assert tape.demanded_symbols(NOW) == list(tape.TAPE_FIXED)
