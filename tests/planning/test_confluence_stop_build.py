"""v139: build_confluence_plan takes its stop from confluence_stop_geometry --
today's clamp with both knobs at 0, arm S's structural stop with a re-chosen
target and a stored ceiling, arm D's drop."""
import dataclasses
import types

import pytest

from swingbot import config
from swingbot.core.planning import builders
from swingbot.core.planning.plan_engine import build_confluence_plan
from swingbot.scan_params import ScanParams
from tests.helpers import make_ohlcv


@pytest.fixture(autouse=True)
def clamp_on(monkeypatch):
    monkeypatch.setattr(config, "CLAMP_STOP_TO_HARD_CAP", True)


def _params(s=0.0, d=0.0):
    return dataclasses.replace(ScanParams.from_config(),
                               min_risk_reward_ratio=1.5, max_risk_reward_ratio=2.5,
                               confluence_structural_stop_pct=s, confluence_stop_drop_pct=d)


def _scenario(direction, entry, stop_loss, take_profit):
    return types.SimpleNamespace(
        direction=direction, entry=entry, stop_loss=stop_loss, take_profit=take_profit,
        target_sources=["Rolling S/R"], stop_sources=["Rolling S/R"])


def _build(scenario, params):
    return build_confluence_plan(
        scenario, make_ohlcv([scenario.entry] * 60), ticker="XYZ", horizon_key="4w",
        primary_strategy="S/R Confluence", level_map=None, params=params)


def test_knobs_off_build_todays_clamped_plan():
    plan = _build(_scenario("bullish", 100.0, 96.5, 108.0), _params())
    assert plan.stop_loss == pytest.approx(98.25)
    assert plan.tp1 == pytest.approx(100.0 + 1.75 * 2.5)   # 108 is past the cap: synthetic
    assert plan.tp2 == pytest.approx(108.0)
    assert plan.stop_ceiling_pct is None
    assert plan.acceptance_level == 96.5


def test_arm_s_keeps_the_level_and_reselects_the_target():
    plan = _build(_scenario("bullish", 100.0, 96.5, 108.0), _params(s=4.0))
    assert plan.stop_loss == 96.5
    assert plan.stop_ceiling_pct == 4.0
    assert plan.tp1 == pytest.approx(108.0)   # 2.29R against the 3.5 structural risk
    assert plan.tp2 is None
    assert plan.acceptance_level == 96.5


def test_arm_s_bearish_mirror():
    plan = _build(_scenario("bearish", 100.0, 103.5, 92.0), _params(s=4.0))
    assert (plan.stop_loss, plan.stop_ceiling_pct) == (103.5, 4.0)
    assert plan.tp1 == pytest.approx(92.0)


def test_arm_s_rollback_builds_exactly_todays_plan():
    # 104 is 1.14R at the 3.5 structural risk (rollback) and 2.29R at 1.75.
    scenario = _scenario("bullish", 100.0, 96.5, 104.0)
    today, rolled = _build(scenario, _params()), _build(scenario, _params(s=4.0))
    assert rolled.stop_ceiling_pct is None
    assert (rolled.stop_loss, rolled.tp1, rolled.tp2) == (today.stop_loss, today.tp1, today.tp2)


@pytest.mark.parametrize("direction,stop,target", [("bullish", 96.5, 108.0),
                                                    ("bearish", 103.5, 92.0)])
def test_arm_d_drops_beyond_its_ceiling_and_keeps_within(direction, stop, target):
    assert _build(_scenario(direction, 100.0, stop, target), _params(d=3.0)) is None
    kept = _build(_scenario(direction, 100.0, stop, target), _params(d=4.0))
    assert kept.stop_loss == pytest.approx(98.25 if direction == "bullish" else 101.75)
    assert kept.stop_ceiling_pct is None


def test_unclamped_plan_is_untouched_by_both_arms():
    plan = _build(_scenario("bullish", 100.0, 98.5, 104.0), _params(s=3.0, d=3.0))
    assert plan.stop_loss == 98.5
    assert plan.stop_ceiling_pct is None


def test_confluence_stop_dropped_agrees_with_the_builder():
    scenario = _scenario("bullish", 100.0, 96.5, 108.0)
    assert builders.confluence_stop_dropped(scenario, None, _params(d=3.0)) is True
    assert builders.confluence_stop_dropped(scenario, None, _params(d=4.0)) is False
    assert builders.confluence_stop_dropped(scenario, None, _params()) is False
    assert builders.confluence_stop_dropped(scenario, None, _params(s=4.0, d=3.0)) is False
