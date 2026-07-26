from types import SimpleNamespace
import numpy as np
import swingbot.config as config
from swingbot.core.edge import throttle
from swingbot.core.performance import TradeLog
from swingbot.core.scanning import engine
from swingbot.core.scanning.engine import ScanProgress
from tests.helpers import make_ohlcv

def _item():
    return SimpleNamespace(plan_v2=None)   # or a real ScanItem fixture

def _scenario():
    return SimpleNamespace(direction="bullish", entry=100.0, stop_loss=95.0,
                           take_profit=110.0, target_sources=["EMA21"],
                           stop_sources=["Rolling support"])

def test_flag_off_attaches_nothing(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "off")
    item = _item()
    engine.attach_plan_v2(item, _scenario(), make_ohlcv([100.0] * 60),
                          "AAPL", "4w", level_map=([], []))
    assert item.plan_v2 is None

def test_flag_shadow_attaches_plan_without_touching_legacy(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "shadow")
    item = _item()
    sc = _scenario()
    engine.attach_plan_v2(item, sc, make_ohlcv([100.0] * 60),
                          "AAPL", "4w", level_map=([], []))
    assert item.plan_v2 is not None
    assert item.plan_v2.source == "confluence"
    # legacy scenario numbers untouched -- the embed keeps reading these
    assert sc.entry == 100.0 and sc.take_profit == 110.0

def test_plan_construction_failure_never_kills_the_scan(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "shadow")
    monkeypatch.setattr(engine, "build_confluence_plan",
                        lambda *a, **k: 1 / 0)
    item = _item()
    engine.attach_plan_v2(item, _scenario(), make_ohlcv([100.0] * 60),
                          "AAPL", "4w", level_map=([], []))   # must not raise
    assert item.plan_v2 is None

def _structured_df():
    """Trend up, then a 60-bar consolidation between roughly ±5% of the
    trend's last close -- gives every level source (rolling S/R, Donchian,
    pivots, Bollinger, fibs) real structure on both sides of price, so
    levels.build_scenarios() reliably produces at least one genuine
    scenario. Same recipe as test_levels_scenarios.py's proven fixture.
    """
    rng = np.random.RandomState(7)
    trend = list(100 * np.cumprod(1 + rng.normal(0.002, 0.01, 120)))
    box = [trend[-1] * (1 + 0.05 * np.sin(i / 4)) for i in range(60)]
    return make_ohlcv(trend + box)


def test_sync_run_scan_gates_attach_plan_v2_on_all_ok(monkeypatch, tmp_path):
    """
    Real regression test for the `if all_ok:` gate around the
    attach_plan_v2(...) call at engine.py:676-677, driven through the
    actual `_sync_run_scan` code path -- not a direct call to
    attach_plan_v2, which is what the old version of this test did (and
    which passes identically whether the gate exists, is True/False, or
    is deleted entirely -- it never touched _sync_run_scan at all).

    Every scenario levels.build_scenarios() actually returns has already
    cleared min_reward/min_stop_distance/max_stop_distance/min_risk_reward
    (see build_scenarios' own docstring: a scenario failing any of those
    hard filters is simply never built). That leaves exactly two
    requirement checks in _build_requirement_checks that a real, built
    scenario can still fail: min_confluence and min_confidence. This test
    uses _sync_run_scan's own `min_confluence` override parameter (the
    same lever `!check <N>` uses) to force those two checks to fail (Run
    1: all_ok=False) or pass (Run 2, contrast: all_ok=True) for every
    scenario found, without hand-crafting exact price levels.

    Hard-filter config values (MIN_REWARD_PCT/MIN_STOP_DISTANCE_PCT/
    MAX_STOP_LOSS_PCT/MIN_RISK_REWARD_RATIO) are loosened so scenario
    *construction* itself -- already covered by test_levels_scenarios.py
    -- isn't what's under test here; only the all_ok gate is.

    engine.dedup_scan_items is monkeypatched to capture the real
    ScanItem objects exactly as built (plan_v2 already attached or not,
    per the gate at engine.py:676-677) and then short-circuits to `[]`,
    so the expensive/network-touching alert-building loop further down
    (chart rendering, earnings lookups, secondary notifications) never
    runs -- that loop is irrelevant to the gate under test here and
    would otherwise make this test slow and non-hermetic.
    """
    df = _structured_df()

    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "shadow")
    monkeypatch.setattr(config, "MIN_REWARD_PCT", 0.5)
    monkeypatch.setattr(config, "MIN_STOP_DISTANCE_PCT", 0.0)
    monkeypatch.setattr(config, "MAX_STOP_LOSS_PCT", 50.0)
    monkeypatch.setattr(config, "MIN_RISK_REWARD_RATIO", 0.0)
    # engine.py also floors the min-reward requirement at 15% of the horizon's
    # OWN sr_target_min_pct (see engine.py's effective_min_reward comment) --
    # 4w's default (15.0) floors it at 2.25%, above this fixture's nearest
    # S/R distance (~1.35-1.78%), so no scenario would ever get built without
    # loosening this horizon setting too. This only relaxes a per-horizon
    # constant used to *build* a scenario -- unrelated to the all_ok gate.
    monkeypatch.setitem(engine.HORIZONS["4w"], "sr_target_min_pct", 1.0)

    monkeypatch.setattr(engine, "load_watchlist", lambda: ["TEST"])
    monkeypatch.setattr(
        engine, "get_daily_data",
        lambda ticker, period=None: df.copy() if ticker == "TEST" else None,
    )
    monkeypatch.setattr(engine, "get_current_price", lambda ticker: None)
    monkeypatch.setattr(engine, "trade_log", TradeLog(path=str(tmp_path / "trades.json")))
    monkeypatch.setattr(engine, "is_stop_requested", lambda: False)

    captured = {}

    def _capture_and_shortcircuit(items):
        captured["items"] = list(items)
        return []   # skip the alert-building loop entirely -- plan_v2 is already decided by here

    monkeypatch.setattr(engine, "dedup_scan_items", _capture_and_shortcircuit)

    # --- Run 1: an unreachable min_confluence means every scenario fails
    # the min_confluence requirement -> all_ok=False for all of them.
    engine._sync_run_scan("4w", require_confirmation=False, progress=None, min_confluence=999_999)
    failing_items = captured["items"]
    assert failing_items, "fixture must produce at least one real scenario to exercise the gate"
    assert all(item.plan_v2 is None for item in failing_items), (
        "attach_plan_v2 must NOT be called (plan_v2 must stay None) for a scenario that "
        "fails a requirement check -- the engine.py:676-677 `if all_ok:` gate regressed"
    )

    # --- Run 2 (contrast): min_confluence=0 and the confidence floor
    # dropped to 1 (the lowest level) make both remaining soft
    # requirements pass for every real scenario -> all_ok=True for all.
    monkeypatch.setattr(config, "MIN_ALERT_CONFIDENCE_LEVEL", 1)
    captured.clear()
    engine._sync_run_scan("4w", require_confirmation=False, progress=None, min_confluence=0)
    passing_items = captured["items"]
    assert passing_items, "fixture must produce at least one real scenario to exercise the gate"
    assert all(item.plan_v2 is not None for item in passing_items), (
        "attach_plan_v2 SHOULD be called (plan_v2 must be set) for a scenario that passes "
        "every requirement check -- the engine.py:676-677 `if all_ok:` gate's other branch"
    )


def test_illiquid_ticker_skips_new_signals_but_still_monitors_open_trades(monkeypatch, tmp_path):
    """
    Task E12 regression: the liquidity screen must gate NEW-signal scanning
    only (level maps / scenarios / confluence / plan-v2 for this ticker this
    scan), never the existing-open-trade monitoring
    (update_open_trades/_check_near_close) that already runs earlier in the
    same per-ticker iteration -- an open paper trade's SL/TP must keep being
    checked every scan even on a day the ticker fails the liquidity floor.
    See the ordering comment right above the `illiquid_reason` check in
    engine.py's _sync_run_scan.

    Uses the same structured trend+box fixture as
    test_sync_run_scan_gates_attach_plan_v2_on_all_ok (proven to make
    levels.build_scenarios() return real scenarios) but with volume low
    enough ($100 x 10k shares = $1M/day) to fail config.UNIVERSE_MIN_DOLLAR_VOL's
    default $20M/day floor -- real liquidity_reason() is exercised, not
    monkeypatched, so this is a genuine integration check of the wiring.
    """
    df = _structured_df()
    # Collapse volume well under the $20M/day default floor without touching
    # price (which the fixture's scenario-building relies on).
    df = df.assign(Volume=10_000.0)

    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "shadow")
    monkeypatch.setattr(engine, "load_watchlist", lambda: ["TEST"])
    monkeypatch.setattr(
        engine, "get_daily_data",
        lambda ticker, period=None: df.copy() if ticker == "TEST" else None,
    )
    monkeypatch.setattr(engine, "get_current_price", lambda ticker: None)
    monkeypatch.setattr(engine, "is_stop_requested", lambda: False)

    test_log = TradeLog(path=str(tmp_path / "trades.json"))
    monkeypatch.setattr(engine, "trade_log", test_log)

    calls = {"update_open_trades": [], "check_near_close": []}
    real_update_open_trades = test_log.update_open_trades
    real_check_near_close = engine._check_near_close

    def _spy_update_open_trades(ticker, df, live_price=None):
        calls["update_open_trades"].append(ticker)
        return real_update_open_trades(ticker, df, live_price=live_price)

    def _spy_check_near_close(ticker, df):
        calls["check_near_close"].append(ticker)
        return real_check_near_close(ticker, df)

    monkeypatch.setattr(test_log, "update_open_trades", _spy_update_open_trades)
    monkeypatch.setattr(engine, "_check_near_close", _spy_check_near_close)

    captured = {}

    def _capture_and_shortcircuit(items):
        captured["items"] = list(items)
        return []

    monkeypatch.setattr(engine, "dedup_scan_items", _capture_and_shortcircuit)

    engine._sync_run_scan("4w", require_confirmation=False, progress=None)

    assert calls["update_open_trades"] == ["TEST"], (
        "update_open_trades must still run for an illiquid ticker -- an existing open "
        "trade's SL/TP monitoring must not stop just because liquidity dipped today"
    )
    assert calls["check_near_close"] == ["TEST"], (
        "_check_near_close must still run for an illiquid ticker for the same reason"
    )
    assert captured["items"] == [], (
        "an illiquid ticker must produce NO new scan items -- level maps/scenarios/plan-v2 "
        "building must be skipped entirely by the E12 liquidity screen"
    )


def test_sync_run_scan_parallel_dispatch_matches_serial(monkeypatch, tmp_path):
    """
    Task E20 fix round 1, Finding 2: every existing _sync_run_scan-driving
    test in this file uses a single-ticker watchlist
    (`load_watchlist` -> ["TEST"]), so map_tickers()'s `len(tickers) <= 1`
    branch always degrades to the serial `[safe(t) for t in tickers]`
    fallback -- the real `ThreadPoolExecutor.map` path was previously only
    ever exercised by the generic, business-logic-free tests in
    tests/test_universe.py, never through the actual scan pipeline's
    merge/confirmation/funnel-summing logic.

    Drives _sync_run_scan with 3 real tickers, once with SCAN_WORKERS=1
    (serial) and once with SCAN_WORKERS=3 (forces genuine parallel
    dispatch -- map_tickers()'s `n <= 1 or len(tickers) <= 1`
    short-circuit does NOT trigger with 3 workers and 3 tickers), and
    asserts the two runs produce identical scan_items composition and
    funnel counts.

    Also re-verifies Finding 1's fix (attach_plan_v2 deferred out of
    _scan_one into _sync_run_scan's post-join merge loop) holds under
    real parallel dispatch: every item here is all_ok (min_confluence=0,
    confidence floor dropped to 1 -- same recipe as
    test_sync_run_scan_gates_attach_plan_v2_on_all_ok's Run 2), so
    plan_v2 must be attached for all of them in both runs.
    """
    dfs = {ticker: _structured_df() for ticker in ("T0", "T1", "T2")}

    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "shadow")
    monkeypatch.setattr(config, "MIN_REWARD_PCT", 0.5)
    monkeypatch.setattr(config, "MIN_STOP_DISTANCE_PCT", 0.0)
    monkeypatch.setattr(config, "MAX_STOP_LOSS_PCT", 50.0)
    monkeypatch.setattr(config, "MIN_RISK_REWARD_RATIO", 0.0)
    monkeypatch.setattr(config, "MIN_ALERT_CONFIDENCE_LEVEL", 1)
    # Same per-horizon loosening as test_sync_run_scan_gates_attach_plan_v2_on_all_ok
    # -- see that test's docstring for why 4w's default sr_target_min_pct
    # would otherwise block this fixture from producing any scenario at all.
    monkeypatch.setitem(engine.HORIZONS["4w"], "sr_target_min_pct", 1.0)

    monkeypatch.setattr(engine, "load_watchlist", lambda: ["T0", "T1", "T2"])
    monkeypatch.setattr(
        engine, "get_daily_data",
        lambda ticker, period=None: dfs[ticker].copy() if ticker in dfs else None,
    )
    monkeypatch.setattr(engine, "get_current_price", lambda ticker: None)
    monkeypatch.setattr(engine, "is_stop_requested", lambda: False)

    def _run(workers: int):
        # Fresh TradeLog and fresh ScanProgress per run -- neither the
        # debounce state nor the progress/funnel state from one run may
        # leak into the other.
        monkeypatch.setattr(config, "SCAN_WORKERS", workers)
        monkeypatch.setattr(engine, "trade_log", TradeLog(path=str(tmp_path / f"trades_{workers}.json")))
        progress = ScanProgress()

        captured = {}

        def _capture_and_shortcircuit(items):
            captured["items"] = list(items)
            return []   # skip the alert-building loop -- plan_v2/funnel are already decided by here

        monkeypatch.setattr(engine, "dedup_scan_items", _capture_and_shortcircuit)

        engine._sync_run_scan("4w", require_confirmation=False, progress=progress, min_confluence=0)
        return captured["items"], progress.funnel

    items_serial, funnel_serial = _run(1)
    items_parallel, funnel_parallel = _run(3)

    assert items_serial, "fixture must produce at least one real scenario across the 3 tickers"
    assert len(items_serial) == len(items_parallel)

    def _identity_set(items):
        return {
            (item.result.ticker, item.result.horizon_key, item.result.trend, item.plan_v2 is not None)
            for item in items
        }

    assert _identity_set(items_serial) == _identity_set(items_parallel), (
        "SCAN_WORKERS=3 (real ThreadPoolExecutor.map dispatch) must produce the exact same "
        "scan_items composition as SCAN_WORKERS=1 (serial) for the same 3 tickers"
    )

    # Re-verify Finding 1's fix under real parallel dispatch: every scenario here is
    # all_ok, so attach_plan_v2 must have run for all of them, in both runs.
    assert all(item.plan_v2 is not None for item in items_serial)
    assert all(item.plan_v2 is not None for item in items_parallel)

    assert funnel_serial == funnel_parallel, (
        "the funnel summary must be identical whether the ANALYZE phase ran serially or "
        "through the real thread pool"
    )
    for key in ("checked", "scenarios_found", "fully_qualifying", "shown"):
        assert funnel_serial[key] == funnel_parallel[key]


def _drive_alert_loop(monkeypatch, tmp_path, intraday_fn):
    """Run _sync_run_scan all the way THROUGH the alert-building loop.

    Every other _sync_run_scan test in this file short-circuits
    `dedup_scan_items` to `[]` precisely so this loop never runs (it is
    network-bound: charts, earnings lookups, secondary notifications).
    Task E29's intraday annotation is wired INSIDE that loop, so testing
    it means letting the loop run with its network-bound helpers stubbed
    out -- otherwise the wiring has zero coverage and could be deleted
    without a single test noticing.

    Returns the ScanItem list exactly as it looked when build_embed was
    called, i.e. after the loop stamped item.intraday.
    """
    df = _structured_df()

    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "shadow")
    monkeypatch.setattr(config, "MIN_REWARD_PCT", 0.5)
    monkeypatch.setattr(config, "MIN_STOP_DISTANCE_PCT", 0.0)
    monkeypatch.setattr(config, "MAX_STOP_LOSS_PCT", 50.0)
    monkeypatch.setattr(config, "MIN_RISK_REWARD_RATIO", 0.0)
    monkeypatch.setattr(config, "MIN_ALERT_CONFIDENCE_LEVEL", 1)
    monkeypatch.setitem(engine.HORIZONS["4w"], "sr_target_min_pct", 1.0)

    monkeypatch.setattr(engine, "load_watchlist", lambda: ["TEST"])
    monkeypatch.setattr(
        engine, "get_daily_data",
        lambda ticker, period=None: df.copy() if ticker == "TEST" else None,
    )
    monkeypatch.setattr(engine, "get_current_price", lambda ticker: None)
    monkeypatch.setattr(engine, "trade_log", TradeLog(path=str(tmp_path / "trades.json")))
    monkeypatch.setattr(engine, "is_stop_requested", lambda: False)

    # Network / filesystem-bound parts of the alert loop, stubbed.
    monkeypatch.setattr(engine, "earnings_within_window", lambda t, d: None)
    monkeypatch.setattr(engine, "get_market_events", lambda d: [])
    monkeypatch.setattr(engine, "generate_trade_chart",
                        lambda *a, **k: str(tmp_path / "chart.png"))
    monkeypatch.setattr(engine, "notify_secondary", lambda *a, **k: None)

    # The annotation under test.
    monkeypatch.setattr(engine.rs_factors, "intraday_confirms", intraday_fn)

    seen = []

    def _capture_embed(item, *a, **k):
        seen.append(item)
        return SimpleNamespace(fields=[])

    monkeypatch.setattr(engine, "build_embed", _capture_embed)

    engine._sync_run_scan("4w", require_confirmation=False, progress=None, min_confluence=0)
    assert seen, "fixture must produce at least one alert to exercise the loop"
    return seen


def test_alert_loop_stamps_intraday_annotation_on_every_item(monkeypatch, tmp_path):
    """Task E29: the alert loop asks for a 1h/VWAP reading per posted alert
    and stamps it on the item so build_embed can render it."""
    calls = []

    def _confirms(ticker, direction):
        calls.append((ticker, direction))
        return True

    items = _drive_alert_loop(monkeypatch, tmp_path, _confirms)
    assert all(item.intraday is True for item in items)
    assert calls and all(t == "TEST" for t, _ in calls)
    assert all(d in ("bullish", "bearish") for _, d in calls)
    # One lookup per POSTED alert, not per scanned ticker-horizon.
    assert len(calls) == len(items)


def test_intraday_lookup_failure_never_breaks_the_alert(monkeypatch, tmp_path):
    """An advisory annotation must never be able to take down an alert:
    a raising lookup leaves item.intraday at None (renders as no field)
    and the alert is still built."""
    def _boom(ticker, direction):
        raise RuntimeError("yfinance is down")

    items = _drive_alert_loop(monkeypatch, tmp_path, _boom)
    assert all(item.intraday is None for item in items)


def test_mass_fetch_failure_raises_data_fail_frac_and_engages_kill_switch(monkeypatch, tmp_path):
    """Task E47 review Finding 1 regression: a total per-ticker fetch
    failure (get_daily_data returns None, the `df is None` early-return in
    _scan_one) must count toward data_fail_frac the same way the later E16
    data-quality-issues path does. Before the fix, stats["data_quality_failed"]
    stayed at its default False on the df-is-None path, so the denominator
    (len(tickers)) never moved for a mass feed outage -- the kill switch's
    "broken data feed" trigger couldn't see the worst version of the failure
    mode it exists to catch.

    4 of 5 watchlist tickers here fetch as None (80% > KILL_DATA_FAIL_FRAC's
    20%); the 5th ("OK") fetches real data so the scan has something to
    analyze. SPY (config.MARKET_REGIME_TICKER) also resolves to None through
    the same stub, which keeps spy_move_pct at 0 -- and the balance-history
    stub keeps dd_pct at 0 -- so the ONLY trigger that can fire here is the
    data-quality one under test. dedup_scan_items short-circuits to `[]`
    (same pattern as every other _sync_run_scan test in this file) since the
    kill-switch computation happens before the alert-building loop and
    doesn't need it to run.
    """
    monkeypatch.setattr(throttle, "KILLSWITCH_PATH", str(tmp_path / "killswitch.json"))
    assert throttle.kill_state()["on"] is False   # sanity: off before the scan

    good_df = _structured_df()
    tickers = ["OK", "BAD1", "BAD2", "BAD3", "BAD4"]

    monkeypatch.setattr(engine, "load_watchlist", lambda: tickers)
    monkeypatch.setattr(
        engine, "get_daily_data",
        lambda ticker, period=None: good_df.copy() if ticker == "OK" else None,
    )
    monkeypatch.setattr(engine, "get_current_price", lambda ticker: None)
    monkeypatch.setattr(engine, "trade_log", TradeLog(path=str(tmp_path / "trades.json")))
    monkeypatch.setattr(engine, "is_stop_requested", lambda: False)
    monkeypatch.setattr(engine.account_module, "get_balance_history_points", lambda: [])
    monkeypatch.setattr(engine, "dedup_scan_items", lambda items: [])

    engine._sync_run_scan("4w", require_confirmation=False, progress=None, min_confluence=0)

    st = throttle.kill_state()
    assert st["on"] is True, "80% fetch-failure rate must cross KILL_DATA_FAIL_FRAC and engage the switch"
    assert "data quality" in st["reason"]
