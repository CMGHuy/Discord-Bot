"""V180-4: Turtle Soup plan -- DROP scope, single market leg, stop Low[t] - 0.25 x ATR14 via
_bounded_stop, target = nearest resistance INSIDE the R band (no synthetic cap), no lifecycle."""
import dataclasses
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from swingbot import config
from swingbot.core.market import levels as levels_mod
from swingbot.core.market.indicators import atr
from swingbot.core.market.levels import Level
from swingbot.core.market.strategy_types import (COMPRESSION_SHORT, HORIZONS, SHORT_STRATEGIES,
                                                  STRUCTURAL_DROP_STRATEGIES, TURTLE_SOUP)
from swingbot.core.planning import builders
from swingbot.core.planning import turtle_soup_plan as tsp
from swingbot.core.planning.params import EXIT_V2_PARAMS, PLAN_SHAPES, STRUCTURE_BUFFER_ATR
from swingbot.core.planning.stop_scope import (CAP, DROP, in_scope, plan_stop_ceiling,
                                               risk_sizing_ok, stop_ceiling)
from swingbot.core.planning.targets import select_structural_target

HZ = "2w"
T = 50          # the sweep bar


@pytest.fixture(autouse=True)
def pins(monkeypatch):
    for name in ("LEVEL_LIFECYCLE_STOPS_ENABLED", "STALL_EXIT_ENABLED",
                 "REGIME_GATES_ENABLED", "DATA_DRIVEN_STOPS_ENABLED"):
        monkeypatch.setattr(config, name, False, raising=False)
    monkeypatch.setattr(config, "MIN_RISK_REWARD_RATIO", 1.5, raising=False)
    monkeypatch.setattr(config, "MAX_RISK_REWARD_RATIO", 2.5, raising=False)
    monkeypatch.setattr(config, "STRUCTURAL_STOP_SCOPE", "", raising=False)


def _frame(sweep_low=98.5, n=60):
    """Flat 100 closes, lows 99.5; bar 40 sets the 20-bar low 99.0 (age 10 at T); bar T
    sweeps it to `sweep_low` and closes back at 100 -- a live Turtle Soup bar."""
    idx = pd.bdate_range("2024-01-02", periods=n)
    close = np.full(n, 100.0)
    low = np.full(n, 99.5)
    low[40] = 99.0
    low[T] = sweep_low
    return pd.DataFrame({"Open": close, "High": close + 0.5, "Low": low, "Close": close,
                         "Volume": np.full(n, 1e6)}, index=idx)


def _map(*prices):
    return [], [Level(price=p, sources=["Swing high", "Pivot high"]) for p in prices]


def _real_stop_and_target(df, r=2.0):
    """The stop build_strategy_plan will compute (its own ATR14) and a level r R above 100."""
    stop = 98.5 - STRUCTURE_BUFFER_ATR * float(atr(df, 14).iloc[T])
    return stop, 100.0 + r * (100.0 - stop)


def _built(df, level_map, direction="bullish"):
    return builders.build_strategy_plan(df, T, ticker="TS", strategy=TURTLE_SOUP, horizon_key=HZ,
                                        direction=direction, level_map=level_map)


def test_turtle_soup_is_a_long_that_is_always_dropped_never_capped():
    assert STRUCTURAL_DROP_STRATEGIES == (TURTLE_SOUP,)
    assert TURTLE_SOUP not in SHORT_STRATEGIES
    assert in_scope(TURTLE_SOUP, "bullish", raw="")
    assert stop_ceiling(TURTLE_SOUP, "bullish", HZ, raw="") == (3.0, DROP)
    assert stop_ceiling("RSI", "bullish", HZ, raw="")[1] == CAP          # unchanged for other longs
    assert stop_ceiling("Bull Trap", "bearish", HZ, raw="") == (3.0, DROP)  # unchanged for shorts


def test_the_fill_reads_the_three_percent_drop_ceiling_and_sizing_caps_dollar_risk():
    plan = SimpleNamespace(source="strategy", strategy=TURTLE_SOUP, direction="bullish",
                           horizon_key=HZ, stop_ceiling_pct=None, trigger_price=100.0,
                           stop_loss=97.5)
    assert plan_stop_ceiling(plan) == 3.0
    budget = {"mode": "risk_pct", "balance": 10_000.0, "risk_pct": 2.0}
    assert risk_sizing_ok(plan, lambda e, s: {**budget, "shares": 80})       # 80 x 2.5 = 200 = 2%
    assert not risk_sizing_ok(plan, lambda e, s: {**budget, "shares": 81})


def test_plan_shape_is_one_market_leg_with_a_ten_session_cap():
    assert PLAN_SHAPES[TURTLE_SOUP] == {"entry_type": "market", "expiry_bars": 1,
                                        "tp1_fraction": 1.0, "breakeven_trigger_fraction": 1.0,
                                        "hold_cap_bars": 10}
    shape = builders.plan_shape_for(TURTLE_SOUP)
    assert (shape["entry_type"], shape["tp1_fraction"], shape["hold_cap_bars"]) == ("market", 1.0, 10)
    assert EXIT_V2_PARAMS[TURTLE_SOUP] == {"trail_atr_mult": 2.5, "tp2": False}
    assert HORIZONS[HZ]["max_holding_days"] >= PLAN_SHAPES[TURTLE_SOUP]["hold_cap_bars"] == 10


def test_in_band_keeps_levels_between_floor_and_cap_nearest_first():
    prices = [106.0, 105.0, 103.0, 101.0, 99.0, 104.0, 105.01, 102.99]
    assert tsp.in_band(100.0, 98.0, prices, 1.5, 2.5) == [103.0, 104.0, 105.0]
    assert tsp.in_band(100.0, 100.0, [103.0], 1.5, 2.5) == []


def test_stop_is_the_buffered_sweep_low_and_the_target_the_nearest_level_in_band():
    out = tsp.turtle_soup_levels(_frame(), T, HZ, entry=100.0, atr_val=1.0,
                                 level_map=_map(102.0, 103.0, 104.0, 110.0))
    assert out.stop == pytest.approx(98.25)              # 98.5 - 0.25 x 1.0; risk 1.75
    assert out.candidates == (103.0, 104.0)              # band [102.625, 104.375]
    assert (out.tp1, out.reason) == (103.0, None)


def test_a_stop_beyond_three_percent_is_dropped_never_squeezed():
    out = tsp.turtle_soup_levels(_frame(), T, HZ, entry=100.0, atr_val=8.0, level_map=_map(105.0))
    # 98.5 - 2.0 = 96.5: 3.5% from the close, beyond the 2w DROP ceiling of 3.0%
    assert (out.stop, out.tp1, out.candidates, out.reason) == (None, None, (), tsp.RISK_CAP)


def test_no_level_in_band_is_no_plan_never_the_synthetic_cap_target():
    out = tsp.turtle_soup_levels(_frame(), T, HZ, entry=100.0, atr_val=1.0,
                                 level_map=_map(110.0, 101.0))
    assert (out.tp1, out.candidates, out.reason) == (None, (), tsp.NO_LEVEL_IN_BAND)
    assert out.stop == pytest.approx(98.25)
    # Unfiltered, the selector would price a synthetic entry + 2.5R target here.
    assert select_structural_target(100.0, 98.25, True, [110.0, 101.0], 1.5, 2.5) == pytest.approx(104.375)


def test_a_stop_at_or_above_the_entry_is_plan_other():
    out = tsp.turtle_soup_levels(_frame(), T, HZ, entry=98.0, atr_val=0.0, level_map=_map(103.0))
    assert (out.stop, out.reason) == (None, tsp.PLAN_OTHER)


def test_a_missing_level_map_is_built_from_bars_up_to_the_signal(monkeypatch):
    seen = {}

    def fake(window, h, price, *args, **kwargs):
        seen.update(last=window.index[-1], price=price, h=h)
        return _map(103.0)

    monkeypatch.setattr(levels_mod, "build_level_map", fake)
    df = _frame()
    out = tsp.turtle_soup_levels(df, T, HZ, entry=100.0, atr_val=1.0)
    assert seen == {"last": df.index[T], "price": 100.0, "h": HORIZONS[HZ]}
    assert out.tp1 == 103.0


def test_reads_no_bar_after_the_signal():
    df = _frame()
    later = df.copy()
    later.iloc[T + 1:, later.columns.get_loc("High")] = 130.0
    later.iloc[T + 1:, later.columns.get_loc("Low")] = 60.0
    assert (tsp.turtle_soup_levels(df, T, HZ, entry=100.0, atr_val=1.0)
            == tsp.turtle_soup_levels(later, T, HZ, entry=100.0, atr_val=1.0))


def test_the_branch_is_bullish_only_and_returns_the_builder_tuple():
    inputs = builders._BranchInputs(_frame(), T, TURTLE_SOUP, HZ, "bullish", 100.0, 1.0,
                                    None, None, _map(103.0, 104.0))
    stop, tp1, candidates, applied = tsp.turtle_soup_branch(inputs)
    assert stop == pytest.approx(98.25)
    assert (tp1, candidates, applied) == (103.0, [103.0, 104.0], None)
    assert tsp.turtle_soup_branch(dataclasses.replace(inputs, direction="bearish")) is None
    assert builders._STRUCTURAL_BRANCHES[TURTLE_SOUP] is builders._turtle_soup_branch


def test_build_strategy_plan_makes_a_single_leg_market_plan():
    df = _frame()
    stop, target = _real_stop_and_target(df)
    plan = _built(df, _map(target))
    assert plan is not None
    assert plan.stop_loss == pytest.approx(stop)
    assert plan.tp1 == pytest.approx(target)
    assert (plan.entry_type, plan.trigger_price, plan.entry_price) == ("market", 100.0, 100.0)
    assert (plan.tp1_fraction, plan.breakeven_trigger_fraction,
            plan.hold_cap_bars, plan.tp2) == (1.0, 1.0, 10, None)
    assert (plan.source, plan.strategy, plan.direction) == ("strategy", TURTLE_SOUP, "bullish")
    assert _built(df, _map(target), direction="bearish") is None
    assert _built(_frame(sweep_low=95.0), _map(110.0)) is None


def test_the_level_lifecycle_never_moves_a_turtle_soup_plan(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("level lifecycle ran for Turtle Soup")

    monkeypatch.setattr(builders, "apply_level_lifecycle", boom)
    df = _frame()
    _, target = _real_stop_and_target(df)
    assert _built(df, _map(target)) is not None
    assert builders._LIFECYCLE_EXEMPT == frozenset({COMPRESSION_SHORT, TURTLE_SOUP})


def test_rejection_reason_names_why_no_plan_was_built():
    assert tsp.turtle_soup_rejection_reason(_frame(sweep_low=95.0), T, HZ,
                                            level_map=_map(110.0)) == tsp.RISK_CAP
    assert tsp.turtle_soup_rejection_reason(_frame(), T, HZ,
                                            level_map=_map(130.0)) == tsp.NO_LEVEL_IN_BAND
    df = _frame()
    _, target = _real_stop_and_target(df)
    assert tsp.turtle_soup_rejection_reason(df, T, HZ, level_map=_map(target)) == tsp.PLAN_OTHER
