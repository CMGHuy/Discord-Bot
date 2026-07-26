import os

import numpy as np
import pytest

from tests.conftest import make_ohlcv
from swingbot.core.universe import liquidity_ok


def test_spy_like_passes():
    df = make_ohlcv(np.full(60, 450.0), volumes=np.full(60, 80_000_000.0))
    assert liquidity_ok(df) is True


def test_penny_stock_fails_price():
    df = make_ohlcv(np.full(60, 2.0), volumes=np.full(60, 50_000_000.0))
    assert liquidity_ok(df) is False


def test_thin_name_fails_dollar_volume():
    # $30 x 100k shares = $3M/day << $20M floor
    df = make_ohlcv(np.full(60, 30.0), volumes=np.full(60, 100_000.0))
    assert liquidity_ok(df) is False


def test_explicit_thresholds_override_config():
    df = make_ohlcv(np.full(60, 30.0), volumes=np.full(60, 100_000.0))
    assert liquidity_ok(df, min_avg_dollar_vol=1_000_000, min_price=1.0) is True


def test_load_etfs_universe():
    from swingbot.core.universe import load, universe_symbols
    rows = load("etfs")
    syms = universe_symbols("etfs")
    assert "SPY" in syms and "QQQ" in syms and "GLD" in syms and "TLT" in syms
    assert all(set(r) >= {"symbol", "name", "sector", "etf"} for r in rows)
    assert all(r["etf"] is True for r in rows)


def test_load_dedupes_and_unknown_is_empty(tmp_path, monkeypatch):
    import json
    from swingbot.core import universe
    d = tmp_path / "universe"; d.mkdir()
    (d / "dup.json").write_text(json.dumps([
        {"symbol": "AAA", "name": "A", "sector": "Energy", "etf": False},
        {"symbol": "AAA", "name": "A again", "sector": "Energy", "etf": False},
    ]))
    monkeypatch.setattr(universe, "UNIVERSE_DIR", str(d))
    assert len(universe.load("dup")) == 1
    assert universe.load("nope") == []


def test_sector_map():
    from swingbot.core.universe import sector_map
    m = sector_map("etfs")
    assert m.get("XLE") == "Energy"


def test_is_etf():
    from swingbot.core.universe import is_etf
    assert is_etf("SPY") is True
    assert is_etf("spy") is True          # case-insensitive
    assert is_etf("NVDA") is False


def test_etf_skips_earnings_lookup(monkeypatch):
    # get_next_earnings_date must return None for ETFs WITHOUT ever calling
    # yfinance. Note: the function's per-candidate loop wraps yf.Ticker(...)
    # in `except Exception`, so a monkeypatch that raises would be silently
    # swallowed and this test would pass even with the short-circuit
    # removed. Use a call-recording spy instead so the assertion on `calls`
    # is a genuine "no network call happened" proof.
    from swingbot.core import events

    calls = []

    def spy_ticker(candidate):
        calls.append(candidate)
        raise RuntimeError("should never be reached for an ETF")

    monkeypatch.setattr(events.yf, "Ticker", spy_ticker)
    assert events.get_next_earnings_date("SPY") is None
    assert calls == []
    assert events.earnings_within_window("SPY", 30) is None
    assert calls == []


def test_spy_plan_builds_end_to_end():
    from tests.conftest import make_trend_df
    from swingbot.core.plan_engine import build_strategy_plan

    df = make_trend_df(300, +0.15)
    plan = build_strategy_plan(df, len(df) - 1, ticker="SPY", strategy="MACD",
                                horizon_key="4w", direction="bullish")
    assert plan is not None and plan.stop_loss < plan.entry_price


def test_update_cache_appends_only_new_bars(tmp_path):
    import numpy as np
    import pandas as pd
    from tests.conftest import make_ohlcv
    from swingbot.core.data_store import save_to_disk, load_from_disk, update_cache

    old = make_ohlcv(np.full(50, 100.0), start="2026-01-01")
    save_to_disk(old, "TEST", "1d", base_dir=str(tmp_path))

    fresh = make_ohlcv(np.full(60, 101.0), start="2026-01-01")  # 10 newer bars, 50 overlap

    def fake_fetch(symbol, start):
        return fresh[fresh.index >= start]

    result = update_cache(["TEST"], base_dir=str(tmp_path), fetch_fn=fake_fetch)
    assert result["TEST"] == 10
    merged = load_from_disk("TEST", "1d", base_dir=str(tmp_path))
    assert len(merged) == 60
    assert not merged.index.duplicated().any()


def test_update_cache_empty_delta_is_noop(tmp_path):
    import numpy as np
    from tests.conftest import make_ohlcv
    from swingbot.core.data_store import save_to_disk, update_cache
    save_to_disk(make_ohlcv(np.full(50, 100.0), start="2026-01-01"), "TEST", "1d",
                 base_dir=str(tmp_path))
    result = update_cache(["TEST"], base_dir=str(tmp_path),
                          fetch_fn=lambda s, start: None)
    assert result["TEST"] == 0


# --- Data-quality validator (E16) -------------------------------------------

def _clean_frame(n=100):
    import numpy as np
    rng = np.random.default_rng(7)
    from tests.conftest import make_ohlcv
    return make_ohlcv(100 * np.cumprod(1 + rng.normal(0.0005, 0.01, n)),
                      volumes=rng.integers(1_000_000, 2_000_000, n).astype(float))


def test_clean_frame_has_no_issues():
    from swingbot.core.universe import data_quality_issues
    assert data_quality_issues(_clean_frame(), "OK") == []


def test_flat_closes_flagged():
    from swingbot.core.universe import data_quality_issues
    df = _clean_frame()
    df.iloc[40:47, df.columns.get_loc("Close")] = 55.5   # 7 identical closes
    assert any("identical closes" in i for i in data_quality_issues(df, "X"))


def test_unadjusted_split_flagged():
    from swingbot.core.universe import data_quality_issues
    df = _clean_frame()
    df.iloc[50:, df.columns.get_loc("Close")] *= 0.5     # -50% jump, volume unchanged
    assert any("split" in i for i in data_quality_issues(df, "X"))


def test_negative_price_and_gap_flagged():
    import pandas as pd
    from swingbot.core.universe import data_quality_issues
    df = _clean_frame()
    df.iloc[10, df.columns.get_loc("Low")] = -1.0
    df = df.drop(df.index[60:75])                        # 15-bar hole ≈ 21 calendar days
    issues = data_quality_issues(df, "X")
    assert any("non-positive" in i for i in issues)
    assert any("gap" in i for i in issues)


# --- Intraday confirmation data cache (E19) ---------------------------------

def test_get_intraday_roundtrip_and_cache(tmp_path):
    import numpy as np
    from tests.conftest import make_ohlcv
    from swingbot.core.data_store import get_intraday

    frame = make_ohlcv(np.full(40, 100.0), start="2026-07-01")
    calls = {"n": 0}

    def fake_fetch(symbol, interval):
        calls["n"] += 1
        return frame

    a = get_intraday("TEST", base_dir=str(tmp_path), fetch_fn=fake_fetch)
    b = get_intraday("TEST", base_dir=str(tmp_path), fetch_fn=fake_fetch)
    assert a is not None and len(a) == 40
    assert len(b) == 40
    assert calls["n"] == 1          # second call served from the fresh cache


def test_get_intraday_none_on_fetch_error(tmp_path):
    from swingbot.core.data_store import get_intraday

    def broken(symbol, interval):
        raise RuntimeError("rate limited")

    assert get_intraday("TEST", base_dir=str(tmp_path), fetch_fn=broken) is None


# --- Scan parallelization (E20) ---------------------------------------------

def test_map_tickers_preserves_order_and_matches_serial():
    from swingbot.core.scanning.engine import map_tickers
    tickers = [f"T{i}" for i in range(10)]
    fn = lambda t: t.lower()
    assert map_tickers(fn, tickers, workers=4) == map_tickers(fn, tickers, workers=1)
    assert map_tickers(fn, tickers, workers=4) == [t.lower() for t in tickers]


def test_map_tickers_isolates_errors():
    from swingbot.core.scanning.engine import map_tickers
    def flaky(t):
        if t == "BOOM":
            raise RuntimeError("bad ticker")
        return t
    out = map_tickers(flaky, ["A", "BOOM", "C"], workers=3)
    assert out == ["A", None, "C"]


# --- Timeframe-grouped cache layout -----------------------------------------

def test_timeframe_name_accepts_both_spellings():
    from swingbot.core.data_store import timeframe_name
    assert timeframe_name("1h") == "hourly"
    assert timeframe_name("60m") == "hourly"
    assert timeframe_name("hourly") == "hourly"
    assert timeframe_name("1d") == timeframe_name("daily") == "daily"
    assert timeframe_name("1wk") == timeframe_name("weekly") == "weekly"
    assert timeframe_name("1mo") == timeframe_name("monthly") == "monthly"


def test_timeframe_name_rejects_unknown():
    import pytest
    from swingbot.core.data_store import timeframe_name
    with pytest.raises(ValueError):
        timeframe_name("3decades")


def test_cache_path_groups_by_timeframe_and_sanitizes(tmp_path):
    from swingbot.core.data_store import cache_path
    p = cache_path("AAPL", "1h", base_dir=str(tmp_path))
    assert p.endswith(os.path.join("hourly", "AAPL.csv"))
    # futures/index symbols must not create stray nested folders
    assert cache_path("GC=F", "hourly", base_dir=str(tmp_path)).endswith(
        os.path.join("hourly", "GC_F.csv"))
    assert cache_path("^GSPC", "daily", base_dir=str(tmp_path)).endswith(
        os.path.join("daily", "_GSPC.csv"))


def test_both_spellings_hit_the_same_file(tmp_path):
    import numpy as np
    from tests.conftest import make_ohlcv
    from swingbot.core.data_store import save_to_disk, load_from_disk
    save_to_disk(make_ohlcv(np.full(12, 100.0)), "TEST", "1h", base_dir=str(tmp_path))
    assert len(load_from_disk("TEST", "hourly", base_dir=str(tmp_path))) == 12

