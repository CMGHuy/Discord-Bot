"""v125: target_capped / stop_clamped derived from real builder output."""
import dataclasses
import types

import pytest

from swingbot import config
from swingbot.core.edge.context import PROVENANCE_KEYS, plan_provenance
from swingbot.core.market import levels
from swingbot.core.planning.builders import _atr_plan
from swingbot.core.planning.plan_engine import build_confluence_plan
from swingbot.core.planning.targets import select_structural_target
from swingbot.scan_params import ScanParams
from tests.helpers import make_ohlcv

MAX_RR = 2.5


def _params():
    return dataclasses.replace(ScanParams.from_config(),
                               min_risk_reward_ratio=1.5, max_risk_reward_ratio=MAX_RR)


def _scenario(direction, entry, stop_loss, take_profit):
    return types.SimpleNamespace(direction=direction, entry=entry, stop_loss=stop_loss,
                                 take_profit=take_profit, target_sources=["Rolling S/R"],
                                 stop_sources=["Rolling S/R"])


def _plan(direction, entry, stop_loss, take_profit, level_map=None):
    plan = build_confluence_plan(
        _scenario(direction, entry, stop_loss, take_profit), make_ohlcv([entry] * 60),
        ticker="XYZ", horizon_key="4w", primary_strategy="S/R Confluence",
        level_map=level_map, params=_params())
    assert plan is not None
    return plan


def _flags(plan):
    return plan_provenance(plan.trigger_price, plan.stop_loss, plan.tp1, MAX_RR)


@pytest.fixture(autouse=True)
def clamp_on(monkeypatch):
    monkeypatch.setattr(config, "CLAMP_STOP_TO_HARD_CAP", True)


@pytest.mark.parametrize("direction,stop,target,capped_tp1", [
    ("bullish", 98.5, 110.0, 103.75), ("bearish", 101.5, 90.0, 96.25)])
def test_nearest_level_beyond_the_cap_is_flagged_capped(direction, stop, target, capped_tp1):
    plan = _plan(direction, 100.0, stop, target)
    assert plan.tp1 == pytest.approx(capped_tp1)               # the synthetic price, not the level
    assert _flags(plan) == {"target_capped": True, "stop_clamped": False}


@pytest.mark.parametrize("direction,stop,target,clamped_stop", [
    ("bullish", 96.0, 104.0, 98.25), ("bearish", 104.0, 96.0, 101.75)])
def test_a_stop_beyond_two_percent_is_flagged_clamped(direction, stop, target, clamped_stop):
    plan = _plan(direction, 100.0, stop, target)
    assert plan.stop_loss == pytest.approx(clamped_stop)
    assert _flags(plan) == {"target_capped": False, "stop_clamped": True}


def test_clamped_and_capped_together():
    plan = _plan("bullish", 100.0, 96.0, 112.0)                # risk 1.75 -> cap 104.375
    assert (plan.stop_loss, plan.tp1) == (pytest.approx(98.25), pytest.approx(104.375))
    assert _flags(plan) == {"target_capped": True, "stop_clamped": True}


def test_an_ordinary_plan_is_neither():
    plan = _plan("bullish", 100.0, 98.5, 103.0)                # 2.0R real level, 1.5% stop
    assert _flags(plan) == {"target_capped": False, "stop_clamped": False}


def test_a_real_level_inside_the_band_is_not_capped():
    resistances = [levels.Level(p, ["Fibonacci"]) for p in (103.0, 104.5, 112.0)]
    supports = [levels.Level(90.0, ["Rolling S/R"])]
    plan = _plan("bullish", 100.0, 95.0, 112.0, level_map=(supports, resistances))
    assert plan.tp1 == pytest.approx(103.0)
    assert _flags(plan) == {"target_capped": False, "stop_clamped": True}


def test_capped_flag_holds_on_an_awkward_price():
    entry, stop = 613.37, 604.21
    tp1 = select_structural_target(entry, stop, True, [700.0], 1.5, MAX_RR)
    assert plan_provenance(entry, stop, tp1, MAX_RR)["target_capped"] is True


def test_strategy_atr_plan_on_the_cap_is_flagged():
    # 2w: risk = 2 ATR, cap = 5 ATR. Only a 9-ATR candidate -> synthetic cap price.
    stop, tp1 = _atr_plan(100.0, 1.0, "bullish", "2w", "RSI", candidate_levels=[109.0], params=_params())
    assert tp1 == pytest.approx(105.0)
    assert plan_provenance(100.0, stop, tp1, MAX_RR) == {"target_capped": True, "stop_clamped": False}


def test_no_entry_gives_none_never_a_guess():
    assert plan_provenance(None, 98.0, 104.0, MAX_RR) == {"target_capped": None, "stop_clamped": None}
    assert set(PROVENANCE_KEYS) == {"target_capped", "stop_clamped"}


@pytest.mark.parametrize("entry,stop,tp1", [(100.0, None, 104.0), (100.0, 98.0, None),
                                            (float("nan"), 98.0, 104.0), (0.0, -1.0, 2.0),
                                            (100.0, 100.0, 104.0), ("x", 98.0, 104.0)])
def test_unusable_inputs_give_none(entry, stop, tp1):
    assert plan_provenance(entry, stop, tp1, MAX_RR) == {"target_capped": None, "stop_clamped": None}


def test_missing_max_rr_leaves_only_target_capped_unknown():
    assert plan_provenance(100.0, 98.25, 104.375, None) == {"target_capped": None, "stop_clamped": True}


def test_clamp_flag_off_means_never_clamped(monkeypatch):
    monkeypatch.setattr(config, "CLAMP_STOP_TO_HARD_CAP", False)
    assert plan_provenance(100.0, 98.25, 104.0, MAX_RR)["stop_clamped"] is False


def test_a_stop_just_inside_the_landing_is_not_clamped():
    assert plan_provenance(100.0, 98.26, 104.0, MAX_RR)["stop_clamped"] is False


def test_overflowing_input_gives_none_flags():
    assert plan_provenance(10**400, 9.0, 12.0, 3.0) == {"target_capped": None, "stop_clamped": None}
