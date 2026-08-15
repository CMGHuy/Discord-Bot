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


def _flags(monkeypatch, *, stops=False, targets=False):
    monkeypatch.setattr("swingbot.config.LEVEL_LIFECYCLE_STOPS_ENABLED", stops, raising=False)
    monkeypatch.setattr("swingbot.config.LEVEL_LIFECYCLE_TARGETS_ENABLED", targets, raising=False)


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

    _flags(monkeypatch, stops=True, targets=True)
    bt_on, live_on = price_both()

    assert live_off is not None and live_on is not None
    # entry/stop/target agree across the two paths, flags off AND flags on
    assert bt_off[1] == pytest.approx(live_off.stop_loss)
    assert bt_off[2] == pytest.approx(live_off.tp1)
    assert bt_on[1] == pytest.approx(live_on.stop_loss)
    assert bt_on[2] == pytest.approx(live_on.tp1)


def _bars_changed_by_lifecycle(monkeypatch, df, strategy="RSI", horizon="4w"):
    """Bars where turning the flags on actually moves the backtest plan."""
    atr_series = atr(df, 14)
    changed = []
    for i in range(120, len(df) - 1, 5):
        _flags(monkeypatch)
        off = _trade_plan_at(df, i, "bullish", strategy, horizon, atr_series)
        _flags(monkeypatch, stops=True, targets=True)
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

    _flags(monkeypatch, stops=True, targets=True)
    bt = _trade_plan_at(df, i, "bullish", "RSI", "4w", atr(df, 14))
    live = plan_engine.build_strategy_plan(
        df, i, ticker="TEST", strategy="RSI", horizon_key="4w", direction="bullish")

    assert live is not None
    assert bt[1] == pytest.approx(live.stop_loss)
    assert bt[2] == pytest.approx(live.tp1)


def test_widening_the_stop_preserves_the_frozen_rr(monkeypatch, df):
    """The R:R table and the 0.30 floor are frozen constants this must not move.

    Re-deriving the target from the new risk distance is what keeps that true,
    so reward/risk must come out identical before and after the adjustment.
    """
    changed = _bars_changed_by_lifecycle(monkeypatch, df)
    assert changed

    # Every changed bar on this fixture is a stop-anchor adjustment (the
    # target pull-in does not fire here), so R:R must survive all of them.
    # A target pull-in deliberately lowers R:R and would need its own case.
    for _i, off, on in changed:
        entry = off[0]
        rr_off = (off[2] - entry) / (entry - off[1])
        rr_on = (on[2] - entry) / (entry - on[1])
        assert rr_on == pytest.approx(rr_off, rel=1e-6), (
            f"R:R moved {rr_off:.4f} -> {rr_on:.4f}; the frozen table must hold")


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


def test_target_pull_in_never_breaks_the_rr_floor(monkeypatch, df):
    _flags(monkeypatch, targets=True)
    i = len(df) - 1
    entry = float(df["Close"].iloc[i])
    stop = entry * 0.95

    _stop, tp1, _meta = plan_engine.apply_level_lifecycle(
        df, i, entry=entry, stop=stop, tp1=entry * 1.10, atr_val=entry * 0.02,
        direction="bullish", strategy="RSI", horizon_key="4w")

    rr = (tp1 - entry) / (entry - stop)
    assert rr >= plan_engine.RR_FLOOR - 1e-9


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
