import types
from unittest.mock import patch

import pandas as pd
import pytest

from swingbot.core.planning.plan_engine import (
    PlanStatus,
    build_confluence_plan,
    scenario_is_breakout,
)

DEFAULT_STRATEGY = "S/R Confluence"


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


def _lv(price):
    return types.SimpleNamespace(price=price)


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


def test_tp1_is_the_scenarios_own_target_when_it_sits_in_the_band():
    # entry 100, stop 96 (risk 4), min 1.5/max 2.5 -> band [106, 110].
    # take_profit 108 is 2.0R -- squarely inside the band.
    scenario = _make_scenario(entry=100.0, stop_loss=96.0, take_profit=108.0)

    plan = build_confluence_plan(
        scenario, _TIGHT_RANGE_DF, ticker="XYZ", horizon_key="2w",
        primary_strategy=DEFAULT_STRATEGY,
    )

    assert plan.tp1 == 108.0


def test_tp1_is_capped_when_the_nearest_level_is_beyond_max_rr():
    # Same band [106, 110]; take_profit 130 is way beyond max_rr, so tp1 is
    # synthesized at exactly the cap and the declined level becomes tp2 --
    # this is the pairing that proves "cap, don't skip".
    scenario = _make_scenario(entry=100.0, stop_loss=96.0, take_profit=130.0)

    plan = build_confluence_plan(
        scenario, _TIGHT_RANGE_DF, ticker="XYZ", horizon_key="2w",
        primary_strategy=DEFAULT_STRATEGY,
    )

    assert plan.tp1 == 110.0
    assert plan.tp2 == 130.0


def test_returns_none_when_no_level_clears_min_rr():
    # entry 100, stop 98 (risk 2), floor at 1.5R = 103. Neither 101 nor 102
    # clears it.
    scenario = _make_scenario(entry=100.0, stop_loss=98.0, take_profit=101.0)
    level_map = ([], [_lv(101.0), _lv(102.0)])

    plan = build_confluence_plan(
        scenario, _TIGHT_RANGE_DF, ticker="XYZ", horizon_key="2w",
        primary_strategy=DEFAULT_STRATEGY, level_map=level_map,
    )

    assert plan is None


def test_returns_none_builds_no_plan_id_and_stamps_no_badge():
    scenario = _make_scenario(entry=100.0, stop_loss=98.0, take_profit=101.0)
    level_map = ([], [_lv(101.0), _lv(102.0)])

    with patch("swingbot.core.planning.plan_engine.stamp_badge") as mock_stamp:
        plan = build_confluence_plan(
            scenario, _TIGHT_RANGE_DF, ticker="XYZ", horizon_key="2w",
            primary_strategy=DEFAULT_STRATEGY, level_map=level_map,
        )

    assert plan is None
    mock_stamp.assert_not_called()


_REWARD_BAND_CASES = [
    ("bullish", 100.0, 96.0, 108.0),   # in-band
    ("bullish", 100.0, 96.0, 130.0),   # beyond cap
    ("bullish", 100.0, 96.0, 106.0),   # exactly at floor
    ("bearish", 100.0, 104.0, 92.0),   # in-band
    ("bearish", 100.0, 104.0, 50.0),   # beyond cap
    ("bearish", 100.0, 104.0, 94.0),   # exactly at floor
]


@pytest.mark.parametrize("direction,entry,stop_loss,take_profit", _REWARD_BAND_CASES)
def test_reward_always_at_least_min_times_risk(direction, entry, stop_loss, take_profit):
    # This is the assertion that names the bug: every plan's target must pay
    # at least MIN_RISK_REWARD_RATIO times its own risk. The old per-strategy
    # fixed reward:risk arithmetic (0.30-0.40) violated this by construction.
    scenario = _make_scenario(direction=direction, entry=entry, stop_loss=stop_loss,
                              take_profit=take_profit)

    plan = build_confluence_plan(
        scenario, _WIDE_RANGE_DF, ticker="XYZ", horizon_key="2w",
        primary_strategy=DEFAULT_STRATEGY,
    )

    assert plan is not None
    risk = abs(entry - stop_loss)
    assert abs(plan.tp1 - entry) >= risk * 1.5 - 1e-9


@pytest.mark.parametrize("direction,entry,stop_loss,take_profit", _REWARD_BAND_CASES)
def test_reward_never_exceeds_max_times_risk(direction, entry, stop_loss, take_profit):
    scenario = _make_scenario(direction=direction, entry=entry, stop_loss=stop_loss,
                              take_profit=take_profit)

    plan = build_confluence_plan(
        scenario, _WIDE_RANGE_DF, ticker="XYZ", horizon_key="2w",
        primary_strategy=DEFAULT_STRATEGY,
    )

    assert plan is not None
    risk = abs(entry - stop_loss)
    assert abs(plan.tp1 - entry) <= risk * 2.5 + 1e-9


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
        primary_strategy=DEFAULT_STRATEGY,
    )

    assert plan.entry_type == "stop_entry"
    assert plan.entry_price is None
    assert plan.status == PlanStatus.PENDING


def test_entry_type_market_and_active_when_not_breakout():
    scenario = _make_scenario(direction="bullish", take_profit=105.0)

    plan = build_confluence_plan(
        scenario, _WIDE_RANGE_DF, ticker="XYZ", horizon_key="2w",
        primary_strategy=DEFAULT_STRATEGY,
    )

    assert plan.entry_type == "market"
    assert plan.entry_price == scenario.entry


# v36 -- end-to-end wiring: real Level objects (with real touch-strength)
# reach _select_target through build_confluence_plan, only when
# config.LEVEL_TOUCH_STRENGTH is on.
def test_tp1_prefers_better_tested_level_when_flag_on(monkeypatch):
    from swingbot import config
    from swingbot.core.market.levels import Level

    monkeypatch.setattr(config, "LEVEL_TOUCH_STRENGTH", True)
    # entry 100, stop 96 (risk 4) -> band [106, 110]. 108.0 and 108.2 are
    # both in-band and close enough (0.2 apart on an 8.0 distance-to-entry)
    # to be a tie; the better-tested one should win as tp1.
    weak = Level(price=108.0, sources=["Rolling S/R"],
                strength={"score": 0.2, "touches": 4, "rejections": 0,
                          "breaks": 4, "available": True})
    strong = Level(price=108.2, sources=["Rolling S/R"],
                  strength={"score": 0.9, "touches": 4, "rejections": 4,
                            "breaks": 0, "available": True})
    scenario = _make_scenario(entry=100.0, stop_loss=96.0, take_profit=108.0)
    level_map = ([], [weak, strong])

    plan = build_confluence_plan(
        scenario, _TIGHT_RANGE_DF, ticker="XYZ", horizon_key="2w",
        primary_strategy=DEFAULT_STRATEGY, level_map=level_map,
    )

    assert plan.tp1 == 108.2


def test_tp1_unaffected_by_strength_when_flag_off(monkeypatch):
    from swingbot import config
    from swingbot.core.market.levels import Level

    monkeypatch.setattr(config, "LEVEL_TOUCH_STRENGTH", False)
    weak = Level(price=108.0, sources=["Rolling S/R"],
                strength={"score": 0.2, "touches": 4, "rejections": 0,
                          "breaks": 4, "available": True})
    strong = Level(price=108.2, sources=["Rolling S/R"],
                  strength={"score": 0.9, "touches": 4, "rejections": 4,
                            "breaks": 0, "available": True})
    scenario = _make_scenario(entry=100.0, stop_loss=96.0, take_profit=108.0)
    level_map = ([], [weak, strong])

    plan = build_confluence_plan(
        scenario, _TIGHT_RANGE_DF, ticker="XYZ", horizon_key="2w",
        primary_strategy=DEFAULT_STRATEGY, level_map=level_map,
    )

    assert plan.tp1 == 108.0
