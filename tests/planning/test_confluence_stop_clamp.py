"""v115: build_confluence_plan clamps a stop beyond the 2% hard cap to exactly
2% from the trigger, BEFORE target selection, so tp1 pays the min R:R against
the clamped risk. Spec: docs/superpowers/specs/2026-09-30-v115-restore-sep22-issuance-design.md"""
import dataclasses
import types

import pytest

from swingbot import config
from swingbot.core.market import levels
from swingbot.core.planning import builders
from swingbot.core.planning.plan_engine import build_confluence_plan
from swingbot.core.risk_limits import HARD_MAX_PLANNED_LOSS_PCT, planned_loss_pct
from swingbot.scan_params import ScanParams
from tests.helpers import make_ohlcv


def _params():
    return dataclasses.replace(ScanParams.from_config(),
                               min_risk_reward_ratio=1.5, max_risk_reward_ratio=2.5)


def _scenario(direction, entry, stop_loss, take_profit):
    return types.SimpleNamespace(
        direction=direction, entry=entry, stop_loss=stop_loss, take_profit=take_profit,
        target_sources=["Rolling S/R"], stop_sources=["Rolling S/R"])


def _build(scenario, level_map=None):
    return build_confluence_plan(
        scenario, make_ohlcv([scenario.entry] * 60), ticker="XYZ", horizon_key="4w",
        primary_strategy="S/R Confluence", level_map=level_map, params=_params())


@pytest.fixture
def clamp_on(monkeypatch):
    monkeypatch.setattr(config, "CLAMP_STOP_TO_HARD_CAP", True)


def test_long_four_percent_stop_is_clamped_to_two_percent(clamp_on):
    plan = _build(_scenario("bullish", 100.0, 96.0, 104.0))
    assert plan is not None
    assert plan.stop_loss == pytest.approx(98.0)
    assert plan.tp1 == pytest.approx(104.0)
    assert (plan.tp1 - 100.0) / (100.0 - plan.stop_loss) >= 1.5 - 1e-9


def test_short_four_percent_stop_is_clamped_to_two_percent(clamp_on):
    plan = _build(_scenario("bearish", 100.0, 104.0, 96.0))
    assert plan is not None
    assert plan.stop_loss == pytest.approx(102.0)
    assert plan.tp1 == pytest.approx(96.0)
    assert (100.0 - plan.tp1) / (plan.stop_loss - 100.0) >= 1.5 - 1e-9


def test_target_is_chosen_against_the_clamped_risk(clamp_on):
    # Clamped risk 2 -> band [103, 105]: the nearest qualifying level is 103.
    # Unclamped (risk 5) the floor would be 107.5 and tp1 would be 112.
    resistances = [levels.Level(p, ["Fibonacci"]) for p in (103.0, 104.5, 112.0)]
    supports = [levels.Level(90.0, ["Rolling S/R"])]
    plan = _build(_scenario("bullish", 100.0, 95.0, 112.0), level_map=(supports, resistances))
    assert plan.stop_loss == pytest.approx(98.0)
    assert plan.tp1 == pytest.approx(103.0)


def test_no_target_paying_min_rr_at_two_percent_returns_none(clamp_on):
    # 102.5 is 1.25R against the clamped 2% risk: the existing no_qualifying_target path.
    assert _build(_scenario("bullish", 100.0, 96.0, 102.5)) is None


def test_a_stop_within_the_cap_is_untouched(clamp_on):
    plan = _build(_scenario("bullish", 100.0, 98.5, 103.0))
    assert plan.stop_loss == 98.5


def test_a_stop_exactly_at_the_cap_is_untouched(clamp_on):
    plan = _build(_scenario("bullish", 100.0, 98.0, 104.0))
    assert plan.stop_loss == 98.0


def test_flag_off_restores_the_unclamped_stop(monkeypatch):
    monkeypatch.setattr(config, "CLAMP_STOP_TO_HARD_CAP", False)
    plan = _build(_scenario("bullish", 100.0, 96.0, 108.0))
    assert plan.stop_loss == 96.0
    assert plan.tp1 == pytest.approx(108.0)


def test_clamped_plan_never_exceeds_the_attach_safety_net(clamp_on):
    # GC=F 2026-09-28 prices: the f01e87e2 reject uses a 1e-9 tolerance, and a
    # clamped plan must never trip it on a float edge.
    plan = _build(_scenario("bearish", 4194.30, 4278.68, 4066.11))
    assert plan is not None
    assert planned_loss_pct(plan.trigger_price, plan.stop_loss) <= HARD_MAX_PLANNED_LOSS_PCT + 1e-9


def test_helper_leaves_an_invalid_entry_alone(clamp_on):
    assert builders._clamp_stop_to_hard_cap(0.0, 5.0, True) == 5.0
