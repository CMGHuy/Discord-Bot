"""P1 wiring: the lifecycle adjuster must reach BOTH plan paths.

edge-engine-v4's DATA_DRIVEN_STOPS_ENABLED scored exactly 0.0000 and burned
its one pre-registered validation shot because it reached only
plan_engine.build_strategy_plan while the backtest sized through
backtest._trade_plan_at. `test_both_plan_paths_apply_the_same_adjustment` is
the regression test for that specific failure -- if someone later wires a
lifecycle consumer into one path only, it fails.
"""
import numpy as np
import pandas as pd
import pytest

from swingbot import config
from swingbot.core.planning import plan_engine
from swingbot.core.backtesting.backtest import _trade_plan_at
from swingbot.core.market.indicators import atr


def _frame(n=300, seed=7):
    """A walk with real structure, so levels exist to be classified."""
    rng = np.random.default_rng(seed)
    closes = 100 * np.cumprod(1 + rng.normal(0.0004, 0.012, n))
    highs, lows = closes * 1.01, closes * 0.99
    opens = np.concatenate([[closes[0]], closes[:-1]])
    return pd.DataFrame(
        {"Open": opens, "High": highs, "Low": lows, "Close": closes,
         "Volume": rng.integers(1_000_000, 3_000_000, n).astype(float)},
        index=pd.bdate_range("2020-01-01", periods=n),
    )


@pytest.fixture
def df():
    return _frame()


def _flags(monkeypatch, *, stops=False):
    monkeypatch.setattr("swingbot.config.LEVEL_LIFECYCLE_STOPS_ENABLED", stops, raising=False)


# --- the fast path must be bit-identical ------------------------------------

def test_flags_off_is_a_bit_identical_no_op(monkeypatch, df):
    _flags(monkeypatch)
    i = len(df) - 1
    entry = float(df["Close"].iloc[i])

    stop, tp1, meta = plan_engine.apply_level_lifecycle(
        df, i, entry=entry, stop=entry * 0.97, tp1=entry * 1.02, atr_val=entry * 0.02,
        direction="bullish", strategy="RSI", horizon_key="4w")

    assert (stop, tp1) == (entry * 0.97, entry * 1.02)
    assert meta == {}


def test_flags_off_does_not_build_levels(monkeypatch, df):
    """The zero-cost claim in the docstring, asserted rather than assumed."""
    _flags(monkeypatch)
    called = []
    monkeypatch.setattr(plan_engine, "_lifecycle_levels",
                        lambda *a, **k: called.append(1) or [])

    i = len(df) - 1
    entry = float(df["Close"].iloc[i])
    plan_engine.apply_level_lifecycle(
        df, i, entry=entry, stop=entry * 0.97, tp1=entry * 1.02, atr_val=entry * 0.02,
        direction="bullish", strategy="RSI", horizon_key="4w")

    assert called == [], "levels were built despite both flags being off"


# --- the parity test this whole module exists for ---------------------------

def test_both_plan_paths_apply_the_same_adjustment(monkeypatch, df):
    """backtest._trade_plan_at and build_strategy_plan must agree.

    Uses a strategy on the plain ATR branch so both paths run identical
    sizing arithmetic; any divergence is the lifecycle adjuster reaching one
    path and not the other.
    """
    i = len(df) - 40
    atr_series = atr(df, 14)

    def price_both():
        bt = _trade_plan_at(df, i, "bullish", "RSI", "4w", atr_series)
        live = plan_engine.build_strategy_plan(
            df, i, ticker="TEST", strategy="RSI", horizon_key="4w",
            direction="bullish")
        return bt, live

    _flags(monkeypatch)
    bt_off, live_off = price_both()

    _flags(monkeypatch, stops=True)
    bt_on, live_on = price_both()

    assert live_off is not None and live_on is not None
    # entry/stop/target agree across the two paths, flags off AND flags on
    assert bt_off[1] == pytest.approx(live_off.stop_loss)
    assert bt_off[2] == pytest.approx(live_off.tp1)
    assert bt_on[1] == pytest.approx(live_on.stop_loss)
    assert bt_on[2] == pytest.approx(live_on.tp1)


def test_both_paths_agree_on_none(monkeypatch, df):
    """Global constraint 7: the live and backtest paths must not diverge on
    WHETHER a plan exists either -- if one returns None (no qualifying
    target), the other must too, on the same bar.

    MIN/MAX_RISK_REWARD_RATIO pushed out of the ATR ladder's reach (max
    ~5R at k=10 ATR against the default 2-ATR stop) so every scanned bar
    is a genuine None case on both paths, deterministically -- not relying
    on the fixture happening to produce one.
    """
    monkeypatch.setattr(config, "MIN_RISK_REWARD_RATIO", 20.0)
    monkeypatch.setattr(config, "MAX_RISK_REWARD_RATIO", 25.0)
    atr_series = atr(df, 14)
    _flags(monkeypatch, stops=True)

    checked = 0
    for i in range(120, len(df) - 1, 5):
        bt = _trade_plan_at(df, i, "bullish", "RSI", "4w", atr_series)
        live = plan_engine.build_strategy_plan(
            df, i, ticker="TEST", strategy="RSI", horizon_key="4w", direction="bullish")
        assert bt is None and live is None, (
            f"bar {i}: expected both paths to agree on None with an unreachable "
            f"RR band, got backtest={bt!r} live={live!r}")
        checked += 1
    assert checked, "fixture must produce at least one bar to check"


def _bars_changed_by_lifecycle(monkeypatch, df, strategy="RSI", horizon="4w"):
    """Bars where turning the flags on actually moves the backtest plan."""
    atr_series = atr(df, 14)
    changed = []
    for i in range(120, len(df) - 1, 5):
        _flags(monkeypatch)
        off = _trade_plan_at(df, i, "bullish", strategy, horizon, atr_series)
        _flags(monkeypatch, stops=True)
        on = _trade_plan_at(df, i, "bullish", strategy, horizon, atr_series)
        if abs(off[1] - on[1]) > 1e-9 or abs(off[2] - on[2]) > 1e-9:
            changed.append((i, off, on))
    return changed


def test_the_backtest_path_is_not_left_behind(monkeypatch, df):
    """Guards the exact DATA_DRIVEN_STOPS_ENABLED failure mode.

    That component scored 0.0000 because it reached only build_strategy_plan
    while the backtest sized through _trade_plan_at. Asserting "the call is
    present" is not enough -- a no-op adjuster would pass that. This asserts
    the backtest plan MEASURABLY moves on at least one bar, which is the
    property the 0.0000 result actually violated.
    """
    changed = _bars_changed_by_lifecycle(monkeypatch, df)

    assert changed, ("the lifecycle adjuster never moved a backtest plan on this "
                     "fixture -- the wiring is present but inert, which is exactly "
                     "how DATA_DRIVEN_STOPS_ENABLED scored 0.0000")
    for _i, off, on in changed:
        assert off[0] == on[0], "entry price must never move"


def test_both_paths_agree_on_a_bar_the_lifecycle_actually_changes(monkeypatch, df):
    """Parity where it counts: a bar the adjuster provably touches.

    test_both_plan_paths_apply_the_same_adjustment could pass vacuously if the
    adjuster fired on neither path; this one cannot.
    """
    changed = _bars_changed_by_lifecycle(monkeypatch, df)
    assert changed, "no bar was changed -- see test_the_backtest_path_is_not_left_behind"
    i = changed[0][0]

    _flags(monkeypatch, stops=True)
    bt = _trade_plan_at(df, i, "bullish", "RSI", "4w", atr(df, 14))
    live = plan_engine.build_strategy_plan(
        df, i, ticker="TEST", strategy="RSI", horizon_key="4w", direction="bullish")

    assert live is not None
    assert bt[1] == pytest.approx(live.stop_loss)
    assert bt[2] == pytest.approx(live.tp1)


def _base_atr_plan(entry, atr_val, direction, horizon_key="4w", strategy="RSI"):
    candidates = plan_engine.atr_target_candidates(entry, atr_val, direction)
    return plan_engine._atr_plan(entry, atr_val, direction, horizon_key, strategy,
                                 candidate_levels=candidates)


def _bars_where_stop_widening_fires(monkeypatch, df, *, candidates_for, strategy="RSI",
                                    horizon="4w"):
    """Bars where a real (base_stop, base_tp1) pair (priced the same way
    _atr_plan prices it) has a tested anchor wide enough that
    apply_level_lifecycle's stop-widening branch actually engages.
    `candidates_for(entry, atr_val)` decides whether the widening is then
    kept (a qualifying target exists at the new risk) or rolled back (it
    doesn't). Direct calls to apply_level_lifecycle, not _trade_plan_at, so
    `meta` is visible. Returns (i, entry, base_stop, base_tp1, stop, tp1,
    meta) for every bar where the branch actually fired (meta non-empty)."""
    atr_series = atr(df, 14)
    results = []
    _flags(monkeypatch, stops=True)
    for i in range(120, len(df) - 1, 5):
        entry = float(df["Close"].iloc[i])
        atr_val = plan_engine._safe_atr_value(entry, float(atr_series.iloc[i]))
        base = _base_atr_plan(entry, atr_val, "bullish", horizon, strategy)
        if base is None:
            continue
        base_stop, base_tp1 = base
        stop, tp1, meta = plan_engine.apply_level_lifecycle(
            df, i, entry=entry, stop=base_stop, tp1=base_tp1, atr_val=atr_val,
            direction="bullish", strategy=strategy, horizon_key=horizon,
            candidate_levels=candidates_for(entry, atr_val))
        if meta:
            results.append((i, entry, base_stop, base_tp1, stop, tp1, meta))
    return results


def test_widening_that_keeps_a_qualifying_target_is_applied(monkeypatch, df):
    """The wider stop's own tp1 is RE-SELECTED against the new risk, not
    carried over from the pre-widening plan -- generous ATR-ladder
    candidates guarantee something qualifies at the new risk too."""
    fired = _bars_where_stop_widening_fires(
        monkeypatch, df,
        candidates_for=lambda entry, atr_val: plan_engine.atr_target_candidates(
            entry, atr_val, "bullish"))
    applied = [r for r in fired if "lifecycle_stop" in r[6]]

    assert applied, "fixture must produce at least one bar where the widening applies"
    for _i, entry, base_stop, base_tp1, stop, tp1, _meta in applied:
        assert stop != base_stop, "the widened stop must actually be wider"
        risk = entry - stop
        assert config.MIN_RISK_REWARD_RATIO - 1e-6 <= (tp1 - entry) / risk <= \
            config.MAX_RISK_REWARD_RATIO + 1e-6
        # tp1 is re-derived from the NEW risk, not the old plan's target.
        assert tp1 != pytest.approx(base_tp1)


def test_widening_with_no_qualifying_target_is_rolled_back_entirely(monkeypatch, df):
    """No candidates at all -> select_structural_target always returns None
    at the new risk -> the whole widening rolls back: BOTH stop and tp1 stay
    at their pre-lifecycle values, never a wide stop paired with the old
    (now too-generous) target."""
    fired = _bars_where_stop_widening_fires(monkeypatch, df, candidates_for=lambda e, a: [])
    rolled_back = [r for r in fired if "lifecycle_stop_rolled_back" in r[6]]

    assert rolled_back, "fixture must produce at least one bar where widening would fire"
    for _i, entry, base_stop, base_tp1, stop, tp1, _meta in rolled_back:
        assert stop == base_stop, "a rolled-back widening must not keep the wide stop"
        assert tp1 == base_tp1, "a rolled-back widening must not keep the old target either"


def test_rr_holds_after_the_lifecycle_runs(monkeypatch, df):
    """Whatever the lifecycle does to (stop, tp1) -- widen-and-reselect, or
    roll back entirely -- the result must sit inside
    [MIN_RISK_REWARD_RATIO, MAX_RISK_REWARD_RATIO], never the old frozen
    0.30 floor this test used to check."""
    fired = _bars_where_stop_widening_fires(
        monkeypatch, df,
        candidates_for=lambda entry, atr_val: plan_engine.atr_target_candidates(
            entry, atr_val, "bullish"))
    assert fired, "fixture must produce at least one bar where the lifecycle fires"
    for _i, entry, _base_stop, _base_tp1, stop, tp1, _meta in fired:
        risk = entry - stop
        rr = (tp1 - entry) / risk
        assert config.MIN_RISK_REWARD_RATIO - 1e-9 <= rr <= config.MAX_RISK_REWARD_RATIO + 1e-9, (
            f"rr={rr:.4f} outside [{config.MIN_RISK_REWARD_RATIO}, {config.MAX_RISK_REWARD_RATIO}]")


# --- adjustment semantics ---------------------------------------------------

def test_stop_only_ever_widens(monkeypatch, df):
    _flags(monkeypatch, stops=True)
    i = len(df) - 1
    entry = float(df["Close"].iloc[i])
    tight = entry * 0.999          # absurdly tight stop, well inside any level

    stop, _tp1, _meta = plan_engine.apply_level_lifecycle(
        df, i, entry=entry, stop=tight, tp1=entry * 1.05, atr_val=entry * 0.02,
        direction="bullish", strategy="RSI", horizon_key="4w")

    assert stop <= tight, "a bullish stop must never move up toward entry"


def test_stop_adjustment_respects_max_risk_pct(monkeypatch, df):
    from swingbot.core.market.strategy_types import HORIZONS

    _flags(monkeypatch, stops=True)
    i = len(df) - 1
    entry = float(df["Close"].iloc[i])

    stop, _tp1, _meta = plan_engine.apply_level_lifecycle(
        df, i, entry=entry, stop=entry * 0.98, tp1=entry * 1.05, atr_val=entry * 0.02,
        direction="bullish", strategy="RSI", horizon_key="4w")

    max_risk = entry * (HORIZONS["4w"]["max_risk_pct"] / 100)
    assert entry - stop <= max_risk + 1e-9


def test_levels_are_built_without_lookahead_in_the_backtest_branch(monkeypatch, df):
    """The backtest has no level_map and builds one itself -- from bars <= i only.

    df runs to the end of history here, so an unsliced build would draw levels
    out of bars the trade cannot have seen.
    """
    seen = {}
    from swingbot.core.market import levels as levels_mod
    real = levels_mod.build_level_map

    def spy(hist, h, price):
        seen["bars"] = len(hist)
        return real(hist, h, price)

    monkeypatch.setattr(levels_mod, "build_level_map", spy)
    i = 200
    plan_engine._lifecycle_levels(df, i, "4w", float(df["Close"].iloc[i]), None)

    assert seen["bars"] == i + 1, f"built levels from {seen['bars']} bars, expected {i + 1}"


def test_live_path_reuses_the_callers_level_map(monkeypatch, df):
    """Live already has a level_map; rebuilding it would be wasted work."""
    from swingbot.core.market import levels as levels_mod
    monkeypatch.setattr(levels_mod, "build_level_map",
                        lambda *a, **k: pytest.fail("rebuilt levels despite a level_map"))

    i = len(df) - 1
    entry = float(df["Close"].iloc[i])
    lv = levels_mod.Level(price=entry * 0.97, sources=["pivot"])
    plan_engine._lifecycle_levels(df, i, "4w", entry, ([lv], []))
