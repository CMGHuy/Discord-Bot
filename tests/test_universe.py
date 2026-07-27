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


# --- Auto-refresh (data_refresh) --------------------------------------------

def test_is_stale_true_when_missing(tmp_path):
    from swingbot.core.data_refresh import is_stale
    assert is_stale("NOPE", "daily", base_dir=str(tmp_path)) is True


def test_is_stale_false_for_just_written_file(tmp_path):
    import numpy as np
    from tests.conftest import make_ohlcv
    from swingbot.core.data_store import save_to_disk
    from swingbot.core.data_refresh import is_stale
    save_to_disk(make_ohlcv(np.full(5, 100.0)), "TEST", "daily", base_dir=str(tmp_path))
    assert is_stale("TEST", "daily", base_dir=str(tmp_path)) is False


def test_refresh_symbol_skips_fresh_cache(tmp_path, monkeypatch):
    import numpy as np
    from tests.conftest import make_ohlcv
    from swingbot.core import data_refresh
    from swingbot.core.data_store import save_to_disk

    save_to_disk(make_ohlcv(np.full(5, 100.0)), "TEST", "daily", base_dir=str(tmp_path))

    def boom(*a, **k):
        raise AssertionError("must not fetch a fresh cache")

    monkeypatch.setattr(data_refresh, "fetch_interval_data", boom)
    monkeypatch.setattr(data_refresh, "_default_ranged_fetch", boom)
    r = data_refresh.refresh_symbol("TEST", "daily", base_dir=str(tmp_path))
    assert r["status"] == "fresh"


def test_refresh_symbol_cold_does_full_fetch(tmp_path, monkeypatch):
    import numpy as np
    from tests.conftest import make_ohlcv
    from swingbot.core import data_refresh

    frame = make_ohlcv(np.full(30, 100.0))
    monkeypatch.setattr(data_refresh, "fetch_interval_data", lambda s, tf: frame)
    r = data_refresh.refresh_symbol("COLD", "daily", base_dir=str(tmp_path))
    assert r["status"] == "full" and r["rows"] == 30


def _age_cache(path, hours):
    """Backdate a cached CSV's mtime so the staleness gate lets it through."""
    import time as _t
    old = _t.time() - hours * 3600
    os.utime(path, (old, old))


def test_refresh_symbol_appends_only_new_bars(tmp_path, monkeypatch):
    import numpy as np
    from tests.conftest import make_ohlcv
    from swingbot.core import data_refresh
    from swingbot.core.data_store import save_to_disk, load_from_disk, cache_path

    old = make_ohlcv(np.full(20, 100.0), start="2026-01-01")
    save_to_disk(old, "TEST", "daily", base_dir=str(tmp_path))
    # Must be STALE and NOT forced: force=True routes to the cold full-fetch
    # path, which would call the real (unpatched) network fetch and hang.
    _age_cache(cache_path("TEST", "daily", base_dir=str(tmp_path)), 48)

    full = make_ohlcv(np.full(26, 101.0), start="2026-01-01")   # 6 newer bars
    monkeypatch.setattr(data_refresh, "_default_ranged_fetch",
                        lambda s, start, tf: full)
    monkeypatch.setattr(data_refresh, "fetch_interval_data",
                        lambda *a, **k: pytest.fail("took the cold-fetch path"))

    r = data_refresh.refresh_symbol("TEST", "daily", base_dir=str(tmp_path))
    assert r["status"] == "incremental"
    assert r["added"] == 6

    merged = load_from_disk("TEST", "daily", base_dir=str(tmp_path))
    assert len(merged) == 26
    assert not merged.index.duplicated().any()


def test_refresh_symbol_no_new_bars_touches_mtime(tmp_path, monkeypatch):
    import numpy as np
    from tests.conftest import make_ohlcv
    from swingbot.core import data_refresh
    from swingbot.core.data_store import save_to_disk, cache_path

    save_to_disk(make_ohlcv(np.full(20, 100.0), start="2026-01-01"), "TEST",
                 "daily", base_dir=str(tmp_path))
    _age_cache(cache_path("TEST", "daily", base_dir=str(tmp_path)), 48)

    monkeypatch.setattr(data_refresh, "_default_ranged_fetch",
                        lambda s, start, tf: None)
    r = data_refresh.refresh_symbol("TEST", "daily", base_dir=str(tmp_path))
    assert r["status"] == "fresh"
    # mtime touched, so a closed market doesn't re-request the same empty
    # window on every single tick
    assert data_refresh.is_stale("TEST", "daily", base_dir=str(tmp_path)) is False


def test_refresh_all_survives_a_failing_symbol(tmp_path, monkeypatch):
    from swingbot.core import data_refresh

    def flaky(symbol, tf):
        if symbol == "BAD":
            raise RuntimeError("rate limited")
        import numpy as np
        from tests.conftest import make_ohlcv
        return make_ohlcv(np.full(10, 100.0))

    monkeypatch.setattr(data_refresh, "fetch_interval_data", flaky)
    monkeypatch.setattr(data_refresh, "RETRY_BASE_DELAY", 0.0)
    # persist_state=False: refresh_all writes to the REAL data/ state file by
    # default, and a test must never leave a fake symbol in production state.
    res = data_refresh.refresh_all(["GOOD", "BAD"], ["daily"],
                                   base_dir=str(tmp_path), persist_state=False)
    assert res["summary"]["daily"]["full"] == 1
    assert res["summary"]["daily"]["failed"] == 1
    assert res["failures"][0][0] == "BAD"


# --- Never lose accumulated history (forward accumulation) -------------------

def test_forced_refresh_merges_never_overwrites(tmp_path, monkeypatch):
    """The provider's window slides forward. A later full-fetch returning a
    SHALLOWER span must not destroy bars already archived -- that is what
    lets the cache outgrow the provider's cap over time."""
    import numpy as np
    from tests.conftest import make_ohlcv
    from swingbot.core import data_refresh
    from swingbot.core.data_store import save_to_disk, load_from_disk

    deep = make_ohlcv(np.full(60, 100.0), start="2026-01-01")   # archived
    save_to_disk(deep, "TEST", "hourly", base_dir=str(tmp_path))

    # Provider now only serves the last 20 bars (window slid forward)
    shallow = deep.iloc[-20:]
    monkeypatch.setattr(data_refresh, "fetch_interval_data",
                        lambda s, tf: shallow)

    r = data_refresh.refresh_symbol("TEST", "hourly", base_dir=str(tmp_path),
                                    force=True)
    kept = load_from_disk("TEST", "hourly", base_dir=str(tmp_path))
    assert len(kept) == 60, "archived bars were destroyed by a shallower fetch"
    assert kept.index.min() == deep.index.min()
    assert r["added"] == 0


def test_archive_grows_past_provider_window(tmp_path, monkeypatch):
    """Two successive fetches of non-overlapping windows accumulate."""
    import numpy as np
    from tests.conftest import make_ohlcv
    from swingbot.core import data_refresh
    from swingbot.core.data_store import load_from_disk, cache_path

    old_window = make_ohlcv(np.full(30, 100.0), start="2026-01-01")
    monkeypatch.setattr(data_refresh, "fetch_interval_data",
                        lambda s, tf: old_window)
    data_refresh.refresh_symbol("TEST", "hourly", base_dir=str(tmp_path))

    # Later: provider has moved on, serving a newer window entirely
    new_window = make_ohlcv(np.full(30, 101.0), start="2026-03-01")
    monkeypatch.setattr(data_refresh, "_default_ranged_fetch",
                        lambda s, start, tf: new_window)
    _age_cache(cache_path("TEST", "hourly", base_dir=str(tmp_path)), 48)
    data_refresh.refresh_symbol("TEST", "hourly", base_dir=str(tmp_path))

    kept = load_from_disk("TEST", "hourly", base_dir=str(tmp_path))
    assert len(kept) == 60                      # both windows retained
    assert str(kept.index.min())[:10] == "2026-01-01"


def test_transient_failure_is_retried_then_succeeds(tmp_path, monkeypatch):
    import numpy as np
    from tests.conftest import make_ohlcv
    from swingbot.core import data_refresh

    calls = {"n": 0}
    frame = make_ohlcv(np.full(10, 100.0))

    def flaky(symbol, tf):
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("curl timeout")
        return frame

    monkeypatch.setattr(data_refresh, "fetch_interval_data", flaky)
    monkeypatch.setattr(data_refresh, "RETRY_BASE_DELAY", 0.0)
    r = data_refresh.refresh_symbol("TEST", "daily", base_dir=str(tmp_path))
    assert r["status"] == "full"
    assert calls["n"] == 3          # failed twice, succeeded on the third


def test_retry_gives_up_after_attempts(tmp_path, monkeypatch):
    from swingbot.core import data_refresh
    calls = {"n": 0}

    def always_fails(symbol, tf):
        calls["n"] += 1
        raise RuntimeError("rate limited")

    monkeypatch.setattr(data_refresh, "fetch_interval_data", always_fails)
    monkeypatch.setattr(data_refresh, "RETRY_BASE_DELAY", 0.0)
    r = data_refresh.refresh_symbol("TEST", "daily", base_dir=str(tmp_path))
    assert r["status"] == "failed"
    assert calls["n"] == data_refresh.RETRY_ATTEMPTS   # bounded, not infinite


def test_failed_pair_is_retried_sooner_and_tracked(tmp_path, monkeypatch):
    """A failure must stay on the books and come back around quickly."""
    import numpy as np
    from tests.conftest import make_ohlcv
    from swingbot.core import data_refresh
    from swingbot.core.data_store import save_to_disk, cache_path

    save_to_disk(make_ohlcv(np.full(5, 100.0)), "TEST", "monthly",
                 base_dir=str(tmp_path))
    # monthly normally waits 24h; 1h old is NOT stale under that rule
    _age_cache(cache_path("TEST", "monthly", base_dir=str(tmp_path)), 1)
    assert data_refresh.is_stale("TEST", "monthly", base_dir=str(tmp_path)) is False

    # but with a recorded failure it becomes eligible again after 0.5h
    state = {data_refresh._key("TEST", "monthly"): {"last_status": "failed"}}
    assert data_refresh.is_stale("TEST", "monthly", base_dir=str(tmp_path),
                                 state=state) is True


def test_pending_gaps_lists_failures(tmp_path, monkeypatch):
    from swingbot.core import data_refresh
    monkeypatch.setattr(data_refresh, "fetch_interval_data",
                        lambda s, tf: (_ for _ in ()).throw(RuntimeError("down")))
    monkeypatch.setattr(data_refresh, "RETRY_BASE_DELAY", 0.0)
    res = data_refresh.refresh_all(["AAA"], ["daily"], base_dir=str(tmp_path),
                                   persist_state=False)
    gaps = data_refresh.pending_gaps(res["state"])
    assert ("AAA", "daily") == (gaps[0][0], gaps[0][1])


def test_cap_alerts_ranks_by_follow_score():
    from swingbot.commands.scanning import cap_alerts

    class Item:
        def __init__(self, t, fs):
            self.ticker, self.follow_score = t, fs
    items = [Item("LOW", 40), Item("HI", 90), Item("MID", 70)]
    top, rest = cap_alerts(items, max_alerts=2)
    assert [i.ticker for i in top] == ["HI", "MID"]
    assert [i.ticker for i in rest] == ["LOW"]


def test_sector_dedup_collapses_to_best():
    from swingbot.core.scanning.engine import dedup_sector_items

    class Item:
        def __init__(self, t, sector, fs):
            self.ticker, self.sector, self.follow_score = t, sector, fs
            self.also_qualifying = []
    items = [Item("XOM", "Energy", 80), Item("CVX", "Energy", 70),
             Item("MSFT", "Tech", 60)]
    out = dedup_sector_items(items)
    assert [i.ticker for i in out] == ["XOM", "MSFT"]
    assert out[0].also_qualifying == ["CVX"]
