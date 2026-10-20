"""v171 D3/D4 daily_delta units: paths, sidecar, window, triggers, writer, batching."""
import contextlib
import logging
import os
from datetime import date

import pandas as pd
import pytest

from swingbot import config
from swingbot.core.marketdata import daily_delta as dd, data_store
from swingbot.core.marketdata.shared.kinds import Asker
from tests.marketdata.daily_fakes import Market

T0, T1 = date(2026, 9, 30), date(2026, 10, 16)


@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config, "ALPACA_ANCHOR_DATE", "2026-01-05")
    monkeypatch.setattr(config, "DELTA_WINDOW_MAX_DAYS", 30)
    monkeypatch.setattr(config, "MARKETDATA_LAYER", "off")
    data_store.clear_normalized_frame_cache()


def _meta(**kw):
    base = dict(basis=dd.BASIS_ALPACA, last_full_fetch="2026-09-30", last_verified="2026-10-09",
                anchor_date="2026-01-05", anchor_close=100.0, anchor_checked=None)
    return dd.DailyMeta(**{**base, **kw})


def test_basis_for_routes_by_eligibility_and_the_alpaca_switch(monkeypatch):
    monkeypatch.setattr(config, "ALPACA_ENABLED", True)
    assert dd.basis_for("AAPL") == dd.BASIS_ALPACA
    assert dd.basis_for("SAP.DE") == dd.BASIS_YF and dd.basis_for("^GSPC") == dd.BASIS_YF
    monkeypatch.setattr(config, "ALPACA_ENABLED", False)
    assert dd.basis_for("AAPL") == dd.BASIS_YF


def test_one_file_and_one_sidecar_per_basis():
    assert dd.cache_file("aapl", dd.BASIS_ALPACA) == os.path.join("market_data", "daily_alpaca", "AAPL_daily.csv")
    assert dd.cache_file("AAPL", dd.BASIS_YF) == data_store.cache_path("AAPL", "daily")
    assert dd.meta_path("AAPL", dd.BASIS_ALPACA).endswith(os.path.join("daily_alpaca", "AAPL_daily.meta.json"))
    assert dd.meta_path("AAPL", dd.BASIS_YF).endswith(os.path.join("daily", "AAPL.meta.json"))


def test_sidecar_round_trips_and_unreadable_reads_as_none():
    assert dd.read_meta("AAPL", dd.BASIS_ALPACA) is None
    dd._write_meta("AAPL", dd.BASIS_ALPACA, _meta())
    assert dd.read_meta("AAPL", dd.BASIS_ALPACA) == _meta()
    with open(dd.meta_path("AAPL", dd.BASIS_ALPACA), "w") as f:
        f.write("{not json")
    assert dd.read_meta("AAPL", dd.BASIS_ALPACA) is None


def test_delta_window_starts_five_business_days_back_and_caps():
    assert dd.delta_window(_meta(), T1) == (date(2026, 10, 2), T1)
    assert dd.delta_window(_meta(last_verified="2026-09-10"), T1) is None   # 43 days > 30


def _bars(closes, start="2026-10-01"):
    idx = pd.bdate_range(start, periods=len(closes))
    return pd.DataFrame({"Open": closes, "High": closes, "Low": closes, "Close": closes,
                         "Volume": [1.0] * len(closes)}, index=idx)


def test_needs_full_refetch_reasons():
    cached = _bars([100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0])      # Oct 1..9
    window = cached.iloc[1:].copy()
    meta = _meta()
    assert dd.needs_full_refetch(cached, window, meta) is None
    off = window.copy(); off.loc[off.index[0], "Close"] *= 1 + 2e-4
    assert dd.needs_full_refetch(cached, off, meta) == "overlap-mismatch"
    tiny = window.copy(); tiny.loc[tiny.index[0], "Close"] *= 1 + 5e-5
    assert dd.needs_full_refetch(cached, tiny, meta) is None
    assert dd.needs_full_refetch(cached, window.iloc[-2:], meta) == "overlap-short"
    last = window.copy(); last.loc[last.index[-1], "Close"] *= 1.05        # Oct 9 == last_verified: compared
    assert dd.needs_full_refetch(cached, last, meta) == "overlap-mismatch"
    assert dd.needs_full_refetch(cached, window, meta, anchor_close=100.02) == "anchor"
    assert dd.needs_full_refetch(cached, window, meta, anchor_close=100.005) is None


def test_bars_after_last_verified_are_never_compared():
    cached = _bars([100.0, 101.0, 102.0, 103.0, 104.0, 999.0])             # Oct 1..8, last = a legacy forming bar
    window = _bars([100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0])
    assert dd.needs_full_refetch(cached, window, _meta(last_verified="2026-10-07")) is None


def test_yfinance_actions_after_the_last_full_fetch_trigger():
    cached = _bars([100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0])
    window = cached.assign(Dividends=0.0, **{"Stock Splits": 0.0})
    meta = _meta(basis=dd.BASIS_YF, last_full_fetch="2026-10-05")
    assert dd.needs_full_refetch(cached, window, meta) is None
    window.loc[pd.Timestamp("2026-10-02"), "Dividends"] = 0.3                # before last_full_fetch
    assert dd.needs_full_refetch(cached, window, meta) is None
    window.loc[pd.Timestamp("2026-10-07"), "Stock Splits"] = 2.0
    assert dd.needs_full_refetch(cached, window, meta) == "event"


def test_write_daily_persists_closed_bars_only():
    m = Market()
    out = dd.write_daily("AAPL", m.frame(dd.BASIS_ALPACA, T1), basis=dd.BASIS_ALPACA, full=True, today=T1)
    assert out.index.max() < pd.Timestamp(T1)
    assert dd.read_daily("AAPL", dd.BASIS_ALPACA).index.max() == pd.Timestamp("2026-10-15")
    meta = dd.read_meta("AAPL", dd.BASIS_ALPACA)
    assert (meta.last_full_fetch, meta.last_verified, meta.anchor_date) == ("2026-10-16", "2026-10-15", "2026-01-05")
    assert meta.anchor_close == pytest.approx(float(out.loc["2026-01-05", "Close"]))


def test_write_daily_still_writes_when_the_lease_is_not_held(monkeypatch):
    warned = []

    @contextlib.contextmanager
    def no_lease(kind, symbol, *, asker, deadline_s=30.0):
        yield False
    monkeypatch.setattr(dd.layer, "lease", no_lease)
    monkeypatch.setattr(dd.counters, "warn_fail_open", lambda op, exc: warned.append(op))
    dd.write_daily("AAPL", Market().frame(dd.BASIS_ALPACA, T0), basis=dd.BASIS_ALPACA, full=True, today=T0)
    assert os.path.exists(dd.cache_file("AAPL", dd.BASIS_ALPACA)) and warned == ["daily-write"]


def test_full_write_is_never_shallower_than_the_file():
    m = Market()
    deep = m.frame(dd.BASIS_ALPACA, T0)
    older = deep.iloc[:20].copy()
    older.index = older.index - pd.DateOffset(years=12)
    data_store.atomic_write_csv(pd.concat([older, deep])[["Open", "High", "Low", "Close", "Volume"]],
                                dd.cache_file("AAPL", dd.BASIS_ALPACA))
    fresh = Market(divs=[("2026-06-01", 0.5, T0)]).frame(dd.BASIS_ALPACA, T0)
    out = dd.write_daily("AAPL", fresh, basis=dd.BASIS_ALPACA, full=True, today=T0)
    assert out.index[0] == older.index[0]
    ratio = fresh["Close"].iloc[0] / deep["Close"].iloc[0]
    assert out["Close"].iloc[0] == pytest.approx(older["Close"].iloc[0] * ratio, rel=1e-9)


def test_spot_metals_are_refused():
    window, full = Market().providers(T0)
    assert dd.delta_update(["XAUUSD"], asker=Asker.SCAN, today=T0, fetch_window=window, fetch_full=full) == {}
    with pytest.raises(ValueError):
        dd.write_daily("XAUUSD", Market().frame(dd.BASIS_YF, T0), basis=dd.BASIS_YF, full=True, today=T0)
    assert not os.path.exists(os.path.join("market_data", "daily", "XAUUSD.csv"))


def _warm(monkeypatch, m, symbols, as_of=T0):
    monkeypatch.setattr(dd, "basis_for", lambda t: dd.BASIS_YF if "." in t else dd.BASIS_ALPACA)
    window, full = m.providers(as_of)
    return dd.delta_update(symbols, asker=Asker.SCAN, today=as_of, fetch_window=window, fetch_full=full)


def test_one_window_call_per_basis_and_the_anchor_once_per_day(monkeypatch):
    m = Market()
    _warm(monkeypatch, m, ["AAPL", "MSFT", "SAP.DE"])
    m.calls.clear()
    _warm(monkeypatch, m, ["AAPL", "MSFT", "SAP.DE"], as_of=T1)
    windows = [(c[1], c[2]) for c in m.calls if c[0] == "window"]
    assert sorted(b for b, _ in windows) == sorted([dd.BASIS_ALPACA, dd.BASIS_ALPACA, dd.BASIS_YF, dd.BASIS_YF])
    assert (dd.BASIS_ALPACA, date(2026, 1, 5)) in windows                  # the batched anchor call
    m.calls.clear()
    _warm(monkeypatch, m, ["AAPL", "MSFT", "SAP.DE"], as_of=T1)
    assert len([c for c in m.calls if c[0] == "window"]) == 2              # anchor not due again today
    assert not [c for c in m.calls if c[0] == "full"]


def test_window_miss_serves_the_cached_frame_unchanged(monkeypatch):
    m = Market()
    _warm(monkeypatch, m, ["AAPL"])
    before = os.stat(dd.cache_file("AAPL", dd.BASIS_ALPACA)).st_mtime_ns
    m.missing.add(("window", dd.BASIS_ALPACA))
    got = _warm(monkeypatch, m, ["AAPL"], as_of=T1)["AAPL"]
    pd.testing.assert_frame_equal(got, dd.read_daily("AAPL", dd.BASIS_ALPACA), check_freq=False)
    assert os.stat(dd.cache_file("AAPL", dd.BASIS_ALPACA)).st_mtime_ns == before


def test_a_second_delta_the_same_day_rewrites_nothing(monkeypatch):
    m = Market()
    _warm(monkeypatch, m, ["AAPL"])
    _warm(monkeypatch, m, ["AAPL"], as_of=T1)
    before = os.stat(dd.cache_file("AAPL", dd.BASIS_ALPACA)).st_mtime_ns
    got = _warm(monkeypatch, m, ["AAPL"], as_of=T1)["AAPL"]
    assert os.stat(dd.cache_file("AAPL", dd.BASIS_ALPACA)).st_mtime_ns == before
    assert got.index[-1] == pd.Timestamp(T1) and got.attrs == {}            # forming bar in memory only


def test_full_refetch_logs_anchor_drift(monkeypatch, caplog):
    monkeypatch.setattr(dd, "basis_for", lambda t: dd.BASIS_ALPACA)
    _warm(monkeypatch, Market(), ["AAPL"])
    m = Market(divs=[("2026-09-15", 0.30, T0)])
    monkeypatch.setattr(dd, "provider_full", m.providers(T0)[1])
    monkeypatch.setattr(dd, "_today_ny", lambda: T0)
    with caplog.at_level(logging.INFO, logger=dd.log.name):
        out = dd.full_refetch(["AAPL"], asker=Asker.BACKGROUND)
    assert "AAPL" in out and "anchor_close" in caplog.text and "drift" in caplog.text
