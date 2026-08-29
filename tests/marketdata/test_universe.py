import os

import numpy as np
import pytest

from tests.conftest import make_ohlcv
from swingbot.core.marketdata.universe import liquidity_ok


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
    from swingbot.core.marketdata.universe import load, universe_symbols
    rows = load("etfs")
    syms = universe_symbols("etfs")
    assert "SPY" in syms and "QQQ" in syms and "GLD" in syms and "TLT" in syms
    assert all(set(r) >= {"symbol", "name", "sector", "etf"} for r in rows)
    assert all(r["etf"] is True for r in rows)


def test_load_dedupes_and_unknown_is_empty(tmp_path, monkeypatch):
    import json
    from swingbot.core.marketdata import universe
    d = tmp_path / "universe"; d.mkdir()
    (d / "dup.json").write_text(json.dumps([
        {"symbol": "AAA", "name": "A", "sector": "Energy", "etf": False},
        {"symbol": "AAA", "name": "A again", "sector": "Energy", "etf": False},
    ]))
    monkeypatch.setattr(universe, "UNIVERSE_DIR", str(d))
    assert len(universe.load("dup")) == 1
    assert universe.load("nope") == []


def test_sector_map():
    from swingbot.core.marketdata.universe import sector_map
    m = sector_map("etfs")
    assert m.get("XLE") == "Energy"


def test_is_etf():
    from swingbot.core.marketdata.universe import is_etf
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
    from swingbot.core.market import events

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
    from swingbot.core.planning.plan_engine import build_strategy_plan

    df = make_trend_df(300, +0.15)
    plan = build_strategy_plan(df, len(df) - 1, ticker="SPY", strategy="MACD",
                                horizon_key="4w", direction="bullish")
    assert plan is not None and plan.stop_loss < plan.entry_price


def test_update_cache_appends_only_new_bars(tmp_path):
    import numpy as np
    import pandas as pd
    from tests.conftest import make_ohlcv
    from swingbot.core.marketdata.data_store import save_to_disk, load_from_disk, update_cache

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


def test_default_ranged_fetch_sends_date_only_start(monkeypatch):
    """yf.download's start= only accepts a bare date -- a Timestamp with a
    time/tz component (every intraday `last` index value has one, e.g.
    "2026-07-24 19:30:00+00:00") stringifies to something yfinance's own
    date parser rejects. It doesn't raise: it prints "1 Failed download"
    and hands back an empty frame, which silently looked like "nothing new"
    on every warm incremental refresh at an intraday interval."""
    import pandas as pd
    from swingbot.core.marketdata import data_store

    captured = {}

    def fake_download(symbol, start=None, interval=None, **kwargs):
        captured["start"] = start
        return pd.DataFrame({"Close": [1.0]}, index=pd.DatetimeIndex(["2026-07-25"]))

    monkeypatch.setattr(data_store.yf, "download", fake_download)
    last = pd.Timestamp("2026-07-24 19:30:00+00:00")
    df = data_store._default_ranged_fetch("TEST", last, "1h")

    assert captured["start"] == "2026-07-24"
    assert df is not None and not df.empty


def test_update_cache_empty_delta_is_noop(tmp_path):
    import numpy as np
    from tests.conftest import make_ohlcv
    from swingbot.core.marketdata.data_store import save_to_disk, update_cache
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
    from swingbot.core.marketdata.universe import data_quality_issues
    assert data_quality_issues(_clean_frame(), "OK") == []


def test_flat_closes_flagged():
    from swingbot.core.marketdata.universe import data_quality_issues
    df = _clean_frame()
    df.iloc[40:47, df.columns.get_loc("Close")] = 55.5   # 7 identical closes
    assert any("identical closes" in i for i in data_quality_issues(df, "X"))


def test_unadjusted_split_flagged():
    from swingbot.core.marketdata.universe import data_quality_issues
    df = _clean_frame()
    df.iloc[50:, df.columns.get_loc("Close")] *= 0.5     # -50% jump, volume unchanged
    assert any("split" in i for i in data_quality_issues(df, "X"))


def test_negative_price_and_gap_flagged():
    import pandas as pd
    from swingbot.core.marketdata.universe import data_quality_issues
    df = _clean_frame()
    df.iloc[10, df.columns.get_loc("Low")] = -1.0
    df = df.drop(df.index[60:75])                        # 15-bar hole ≈ 21 calendar days
    issues = data_quality_issues(df, "X")
    assert any("non-positive" in i for i in issues)
    assert any("gap" in i for i in issues)


def test_ancient_frozen_run_outside_the_lookback_window_is_not_flagged():
    """The market_data/ cache is deliberately allowed to grow deeper than any
    live scan needs (data_refresh.py's whole design: 'archive grows past the
    provider's window over time') -- restoring a ticker's full decades-deep
    history (as happened 2026-08-24 recovering from the get_intraday
    overwrite bug) must not resurrect ancient data-provider artifacts (e.g.
    PFE genuinely has an 18-day identical-close run in 1977) as if they were
    live feed problems today. Only the trailing window a scan actually reads
    should be checked."""
    from swingbot.core.marketdata.universe import data_quality_issues, QUALITY_CHECK_LOOKBACK_BARS
    df = _clean_frame(n=QUALITY_CHECK_LOOKBACK_BARS + 200)
    # Plant the frozen run well before the lookback window starts.
    df.iloc[5:15, df.columns.get_loc("Close")] = 55.5
    assert data_quality_issues(df, "X") == []


def test_recent_frozen_run_inside_the_lookback_window_is_still_flagged():
    from swingbot.core.marketdata.universe import data_quality_issues, QUALITY_CHECK_LOOKBACK_BARS
    df = _clean_frame(n=QUALITY_CHECK_LOOKBACK_BARS + 200)
    # Plant the frozen run in the most recent bars -- inside the window.
    last = len(df) - 1
    df.iloc[last - 9:last, df.columns.get_loc("Close")] = 55.5
    assert any("identical closes" in i for i in data_quality_issues(df, "X"))


# --- Intraday confirmation data cache (E19) ---------------------------------

def test_get_intraday_roundtrip_and_cache(tmp_path):
    import numpy as np
    from tests.conftest import make_ohlcv
    from swingbot.core.marketdata.data_store import get_intraday

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
    from swingbot.core.marketdata.data_store import get_intraday

    def broken(symbol, interval):
        raise RuntimeError("rate limited")

    assert get_intraday("TEST", base_dir=str(tmp_path), fetch_fn=broken) is None


def test_get_intraday_merges_stale_refetch_with_existing_history(tmp_path):
    """A stale-cache refetch must UNION with what's already on disk, the same
    contract data_refresh._merge_save() gives every other timeframe -- a
    shallower provider response must never destroy deeper accumulated
    history. This is what production lost: get_intraday() plain-overwrote
    market_data/hourly/{TICKER}.csv with a fresh ~700-day window and wiped
    years of archived history that data_refresh.py had built up."""
    import time
    import numpy as np
    from tests.conftest import make_ohlcv
    from swingbot.core.marketdata.data_store import (
        cache_path, get_intraday, load_from_disk, save_to_disk,
    )

    old = make_ohlcv(np.full(40, 100.0), start="2019-01-01")
    save_to_disk(old, "TEST", "1h", base_dir=str(tmp_path))
    path = cache_path("TEST", "1h", base_dir=str(tmp_path))
    stale_time = time.time() - 5 * 3600  # older than INTRADAY_MAX_AGE_SECONDS (4h)
    os.utime(path, (stale_time, stale_time))

    fresh = make_ohlcv(np.full(40, 100.0), start="2026-07-01")

    def fake_fetch(symbol, interval):
        return fresh

    get_intraday("TEST", base_dir=str(tmp_path), fetch_fn=fake_fetch)

    merged = load_from_disk("TEST", "1h", base_dir=str(tmp_path))
    assert merged.index.min() == old.index.min(), (
        "existing pre-2026 history was discarded by the stale refetch")
    assert merged.index.max() == fresh.index.max()


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
    from swingbot.core.marketdata.data_store import timeframe_name
    assert timeframe_name("1h") == "hourly"
    assert timeframe_name("60m") == "hourly"
    assert timeframe_name("hourly") == "hourly"
    assert timeframe_name("1d") == timeframe_name("daily") == "daily"
    assert timeframe_name("1wk") == timeframe_name("weekly") == "weekly"
    assert timeframe_name("1mo") == timeframe_name("monthly") == "monthly"


def test_timeframe_name_rejects_unknown():
    import pytest
    from swingbot.core.marketdata.data_store import timeframe_name
    with pytest.raises(ValueError):
        timeframe_name("3decades")


def test_cache_path_groups_by_timeframe_and_sanitizes(tmp_path):
    from swingbot.core.marketdata.data_store import cache_path
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
    from swingbot.core.marketdata.data_store import save_to_disk, load_from_disk
    save_to_disk(make_ohlcv(np.full(12, 100.0)), "TEST", "1h", base_dir=str(tmp_path))
    assert len(load_from_disk("TEST", "hourly", base_dir=str(tmp_path))) == 12


# --- Auto-refresh (data_refresh) --------------------------------------------

def test_is_stale_true_when_missing(tmp_path):
    from swingbot.core.marketdata.data_refresh import is_stale
    assert is_stale("NOPE", "daily", base_dir=str(tmp_path)) is True


def test_is_stale_false_for_just_written_file(tmp_path):
    import numpy as np
    from tests.conftest import make_ohlcv
    from swingbot.core.marketdata.data_store import save_to_disk
    from swingbot.core.marketdata.data_refresh import is_stale
    save_to_disk(make_ohlcv(np.full(5, 100.0)), "TEST", "daily", base_dir=str(tmp_path))
    assert is_stale("TEST", "daily", base_dir=str(tmp_path)) is False


def test_refresh_symbol_skips_fresh_cache(tmp_path, monkeypatch):
    import numpy as np
    from tests.conftest import make_ohlcv
    from swingbot.core.marketdata import data_refresh
    from swingbot.core.marketdata.data_store import save_to_disk

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
    from swingbot.core.marketdata import data_refresh

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
    from swingbot.core.marketdata import data_refresh
    from swingbot.core.marketdata.data_store import save_to_disk, load_from_disk, cache_path

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
    from swingbot.core.marketdata import data_refresh
    from swingbot.core.marketdata.data_store import save_to_disk, cache_path

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
    from swingbot.core.marketdata import data_refresh

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
    from swingbot.core.marketdata import data_refresh
    from swingbot.core.marketdata.data_store import save_to_disk, load_from_disk

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
    from swingbot.core.marketdata import data_refresh
    from swingbot.core.marketdata.data_store import load_from_disk, cache_path

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
    from swingbot.core.marketdata import data_refresh

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
    from swingbot.core.marketdata import data_refresh
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
    from swingbot.core.marketdata import data_refresh
    from swingbot.core.marketdata.data_store import save_to_disk, cache_path

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
    from swingbot.core.marketdata import data_refresh
    monkeypatch.setattr(data_refresh, "fetch_interval_data",
                        lambda s, tf: (_ for _ in ()).throw(RuntimeError("down")))
    monkeypatch.setattr(data_refresh, "RETRY_BASE_DELAY", 0.0)
    res = data_refresh.refresh_all(["AAA"], ["daily"], base_dir=str(tmp_path),
                                   persist_state=False)
    gaps = data_refresh.pending_gaps(res["state"])
    assert ("AAA", "daily") == (gaps[0][0], gaps[0][1])


# --- Time-budgeted sweeps (bounds market_data_refresh so a slow/large sweep
# can never run long enough to starve the Discord gateway heartbeat) --------

def test_refresh_all_stops_at_its_time_budget(tmp_path, monkeypatch):
    """A slow sweep must never be allowed to run unbounded -- an unbounded
    background refresh is what let market_data_refresh monopolize the box
    long enough that Discord's gateway heartbeat got missed and the bot
    showed offline. deadline_seconds caps it: whatever wasn't reached this
    pass simply waits for the next scheduled tick, its staleness carried
    over rather than lost."""
    import time as time_mod
    from swingbot.core.marketdata import data_refresh

    calls = []

    def slow_fetch(symbol, tf):
        calls.append(symbol)
        time_mod.sleep(0.05)
        return make_ohlcv(np.full(5, 100.0))

    monkeypatch.setattr(data_refresh, "fetch_interval_data", slow_fetch)
    symbols = [f"SYM{i}" for i in range(20)]
    res = data_refresh.refresh_all(symbols, ["daily"], base_dir=str(tmp_path),
                                   persist_state=False, deadline_seconds=0.12)

    assert res["deadline_hit"] is True
    assert 0 < len(calls) < len(symbols)   # made real progress, but stopped early


def test_refresh_all_deadline_hit_is_false_when_unbounded(tmp_path, monkeypatch):
    from swingbot.core.marketdata import data_refresh

    monkeypatch.setattr(data_refresh, "fetch_interval_data",
                        lambda s, tf: make_ohlcv(np.full(5, 100.0)))
    res = data_refresh.refresh_all(["AAA"], ["daily"], base_dir=str(tmp_path),
                                   persist_state=False)
    assert res["deadline_hit"] is False


def test_refresh_all_deadline_does_not_abandon_partial_progress(tmp_path, monkeypatch):
    """Symbols already refreshed before the deadline hit must keep their
    result -- a time-boxed sweep degrades to 'less done', never to 'undoes
    what it already did'."""
    import time as time_mod
    from swingbot.core.marketdata import data_refresh
    from swingbot.core.marketdata.data_store import load_from_disk

    def slow_fetch(symbol, tf):
        time_mod.sleep(0.05)
        return make_ohlcv(np.full(5, 100.0))

    monkeypatch.setattr(data_refresh, "fetch_interval_data", slow_fetch)
    res = data_refresh.refresh_all(["AAA", "BBB", "CCC", "DDD"], ["daily"],
                                   base_dir=str(tmp_path), persist_state=False,
                                   deadline_seconds=0.08)

    assert res["deadline_hit"] is True
    completed = res["summary"]["daily"]["full"]
    assert 0 < completed < 4
    for key in list(res["state"].keys())[:completed]:
        symbol = key.split("|")[0]
        assert load_from_disk(symbol, "daily", base_dir=str(tmp_path)) is not None


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


def test_scan_telemetry_roundtrip_and_slowdown_alarm(tmp_path):
    from swingbot.core.scanning.engine import log_scan_telemetry, recent_telemetry, scan_slowdown
    p = str(tmp_path / "t.jsonl")
    for d in [60] * 20:
        log_scan_telemetry({"duration_s": d, "tickers": 150}, path=p)
    rows = recent_telemetry(n=10, path=p)
    assert len(rows) == 10 and rows[-1]["duration_s"] == 60
    assert scan_slowdown(path=p) is False
    log_scan_telemetry({"duration_s": 150, "tickers": 150}, path=p)
    assert scan_slowdown(path=p) is True


def test_lru_frames_evicts_least_recent():
    from swingbot.core.scanning.engine import LRUFrames
    lru = LRUFrames(max_frames=2)
    lru["A"], lru["B"] = 1, 2
    _ = lru["A"]              # touch A -> B is now least recent
    lru["C"] = 3
    assert "B" not in lru and "A" in lru and "C" in lru


def test_lru_frames_get_also_counts_as_a_touch():
    """dict.get() bypasses a subclass's __getitem__ override at the C level
    -- this codebase's actual scan loop reads fresh_data almost exclusively
    via .get(t), so LRUFrames must override get() too, or recency tracking
    would silently degrade to insertion order and defeat the point of the
    cache once eviction actually triggers (universe > max_frames)."""
    from swingbot.core.scanning.engine import LRUFrames
    lru = LRUFrames(max_frames=2)
    lru["A"], lru["B"] = 1, 2
    assert lru.get("A") == 1   # touch A via get() -> B is now least recent
    lru["C"] = 3
    assert "B" not in lru and "A" in lru and "C" in lru


def test_alert_routing_by_confidence_level(monkeypatch):
    from swingbot import config
    from swingbot.commands.scanning import route_channel_id

    class Item:
        def __init__(self, confidence_level, badge):
            self.plan = type("P", (), {"confidence_level": confidence_level, "badge": badge})()
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_ID", "111", raising=False)
    monkeypatch.setattr(config, "DISCORD_CHANNEL_FIREHOSE_ID", "222", raising=False)
    assert route_channel_id(Item(5, "VALIDATED")) == "111"
    assert route_channel_id(Item(3, "VALIDATED")) == "222"
    assert route_channel_id(Item(5, "WEAK")) == "222"
    monkeypatch.setattr(config, "DISCORD_CHANNEL_FIREHOSE_ID", "", raising=False)
    assert route_channel_id(Item(1, "WEAK")) == "111"   # unset -> no change


def test_deep_scan_report_renders():
    from swingbot.commands.scanning import deep_scan_report

    class Item:
        def __init__(self, t, score, dist):
            self.ticker, self.quality_score, self.trigger_distance_pct = t, score, dist
            self.plan = type("P", (), {"strategy": "MACD"})()
    out = deep_scan_report([Item("AAA", 80, 1.2), Item("BBB", 60, 0.4)])
    assert "AAA" in out and "MACD" in out and "+1.2%" in out
    assert "watchlist candidates" in out.lower()


def test_sector_dedup_reads_ticker_off_the_real_scanitem_shape():
    """`test_sector_dedup_collapses_to_best` above uses a stub carrying
    `.ticker` directly, a shape the scan never produces: the real ScanItem
    keeps its ticker on `.result`. dedup_sector_items is a documented no-op
    today only because nothing stamps `.sector` yet -- the moment sector
    stamping lands, `g.ticker` raises AttributeError inside dedup_scan_items,
    which sits in no try/except and takes the whole scan down."""
    from swingbot.core.scanning.engine import ScanItem, dedup_sector_items

    class _Result:
        def __init__(self, ticker):
            self.ticker = ticker

    best = ScanItem(result=_Result("XOM"), plan=None, conf=None)
    other = ScanItem(result=_Result("CVX"), plan=None, conf=None)
    best.sector = other.sector = "Energy"
    best.follow_score, other.follow_score = 80, 70

    out = dedup_sector_items([best, other])

    assert [i.result.ticker for i in out] == ["XOM"]
    assert out[0].also_qualifying == ["CVX"]


def test_large_gap_with_prior_twenty_bar_volume_spike_is_not_a_bad_split():
    from swingbot.core.marketdata.universe import data_quality_issues

    df = _clean_frame()
    df.iloc[-21:-1, df.columns.get_loc("Volume")] = 50_000_000.0
    df.iloc[-2, df.columns.get_loc("Close")] = 100.0
    df.iloc[-1, df.columns.get_loc("Close")] = 144.6
    df.iloc[-1, df.columns.get_loc("Volume")] = 164_000_000.0

    assert not any("split" in issue for issue in data_quality_issues(df, "QBTS"))
