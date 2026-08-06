import types

import pandas as pd
import pytest

from swingbot.core.plan_engine import (
    PlanStatus,
    build_confluence_plan,
    scenario_is_breakout,
)
from swingbot.core.strategy_types import STRATEGY_RR_OVERRIDE

# Not in STRATEGY_RR_OVERRIDE -> exercises the 0.35 fallback.
DEFAULT_RR_STRATEGY = "S/R Confluence"
# In STRATEGY_RR_OVERRIDE at 0.40 -> exercises the override lookup itself
# (distinct from the 0.35 fallback, so a hardcoded 0.35 would be caught).
OVERRIDE_RR_STRATEGY = "Fibonacci"


def _make_scenario(**overrides):
    base = dict(
        direction="bullish",
        entry=100.0,
        market_price=100.0,
        stop_loss=98.0,
        stop_sources=["Rolling S/R"],
        stop_distance_pct=2.0,
        tight_stop=False,
        atr_floor_pct=1.5,
        take_profit=110.0,
        target_distance_pct=10.0,
        target_sources=["Rolling S/R"],
        target2_price=None,
        target2_distance_pct=None,
        target2_sources=None,
        constraints={
            "min_reward": True,
            "min_stop_distance": True,
            "max_stop_distance": True,
            "min_risk_reward": True,
        },
    )
    base.update(overrides)
    return types.SimpleNamespace(**base)


def _make_df(highs, lows):
    n = len(highs)
    idx = pd.date_range("2026-01-01", periods=n, freq="D")
    return pd.DataFrame(
        {
            "Open": highs,
            "High": highs,
            "Low": lows,
            "Close": highs,
            "Volume": [1_000_000] * n,
        },
        index=idx,
    )


# Recent 20-bar range tops out well under 110 -> a 110 target is "beyond
# recent range" (breakout).
_TIGHT_RANGE_DF = _make_df(
    highs=[100 + i * 0.1 for i in range(25)],
    lows=[100 + i * 0.1 - 1 for i in range(25)],
)

# A spike to 115 sits inside the rolling-20 lookback (but not on the last
# bar, which shift(1) excludes) -> recent range already covers a 105 or
# 110 target (not a breakout).
_WIDE_RANGE_HIGHS = [100.0] * 25
_WIDE_RANGE_HIGHS[10] = 115.0
_WIDE_RANGE_DF = _make_df(highs=_WIDE_RANGE_HIGHS, lows=[h - 1 for h in _WIDE_RANGE_HIGHS])


def test_tp1_recomputed_with_default_rr_and_tp2_set_beyond_it():
    scenario = _make_scenario(take_profit=110.0)

    plan = build_confluence_plan(
        scenario, _TIGHT_RANGE_DF, ticker="XYZ", horizon_key="2w",
        primary_strategy=DEFAULT_RR_STRATEGY,
    )

    risk = abs(scenario.entry - scenario.stop_loss)
    rr = STRATEGY_RR_OVERRIDE.get(DEFAULT_RR_STRATEGY, 0.35)
    assert rr == 0.35  # sanity: this strategy really is off the override dict
    expected_tp1 = scenario.entry + risk * rr

    assert plan.tp1 == pytest.approx(expected_tp1)
    assert plan.tp2 == scenario.take_profit
    assert plan.source == "confluence"
    assert plan.strategy == DEFAULT_RR_STRATEGY
    assert plan.horizon_key == "2w"
    assert plan.direction == "bullish"
    assert plan.trigger_price == scenario.entry
    assert plan.stop_loss == scenario.stop_loss
    assert plan.badge == "WEAK"  # confluence isn't registry-populated until Task 42


def test_tp1_uses_strategy_rr_override_not_hardcoded_default():
    scenario = _make_scenario(take_profit=110.0)

    plan = build_confluence_plan(
        scenario, _TIGHT_RANGE_DF, ticker="XYZ", horizon_key="2w",
        primary_strategy=OVERRIDE_RR_STRATEGY,
    )

    risk = abs(scenario.entry - scenario.stop_loss)
    rr = STRATEGY_RR_OVERRIDE[OVERRIDE_RR_STRATEGY]
    assert rr == 0.40
    expected_tp1 = scenario.entry + risk * rr
    assert plan.tp1 == pytest.approx(expected_tp1)


def test_tp2_none_when_scenario_target_not_beyond_recomputed_tp1():
    # tp1 = 100 + 2*0.35 = 100.7; a 100.5 scenario target sits inside it.
    scenario = _make_scenario(take_profit=100.5)

    plan = build_confluence_plan(
        scenario, _TIGHT_RANGE_DF, ticker="XYZ", horizon_key="2w",
        primary_strategy=DEFAULT_RR_STRATEGY,
    )

    assert plan.tp2 is None


def test_bearish_tp1_recomputed_downward_and_tp2_beyond():
    scenario = _make_scenario(
        direction="bearish", entry=100.0, stop_loss=102.0, take_profit=90.0,
    )

    plan = build_confluence_plan(
        scenario, _TIGHT_RANGE_DF, ticker="XYZ", horizon_key="2w",
        primary_strategy=DEFAULT_RR_STRATEGY,
    )

    risk = abs(scenario.entry - scenario.stop_loss)
    expected_tp1 = scenario.entry - risk * 0.35
    assert plan.tp1 == pytest.approx(expected_tp1)
    assert plan.tp2 == scenario.take_profit
    assert plan.direction == "bearish"


def test_scenario_is_breakout_true_when_target_beyond_recent_range():
    scenario = _make_scenario(direction="bullish", take_profit=110.0)
    assert scenario_is_breakout(scenario, _TIGHT_RANGE_DF) is True


def test_scenario_is_breakout_false_when_target_within_recent_range():
    scenario = _make_scenario(direction="bullish", take_profit=105.0)
    assert scenario_is_breakout(scenario, _WIDE_RANGE_DF) is False


def test_entry_type_stop_entry_and_pending_when_breakout():
    scenario = _make_scenario(direction="bullish", take_profit=110.0)

    plan = build_confluence_plan(
        scenario, _TIGHT_RANGE_DF, ticker="XYZ", horizon_key="2w",
        primary_strategy=DEFAULT_RR_STRATEGY,
    )

    assert plan.entry_type == "stop_entry"
    assert plan.entry_price is None
    assert plan.status == PlanStatus.PENDING


def test_entry_type_market_and_active_when_not_breakout():
    scenario = _make_scenario(direction="bullish", take_profit=105.0)

    plan = build_confluence_plan(
        scenario, _WIDE_RANGE_DF, ticker="XYZ", horizon_key="2w",
        primary_strategy=DEFAULT_RR_STRATEGY,
    )

    assert plan.entry_type == "market"
    assert plan.entry_price == scenario.entry
    assert plan.status == PlanStatus.ACTIVE
