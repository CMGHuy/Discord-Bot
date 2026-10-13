"""v139 on the live attach path: an arm S plan passes the risk check at its own
stored ceiling and must have dollar-risk sizing; an arm D drop is recorded as
stop_beyond_confluence_ceiling. Knobs at 0 change nothing."""
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.scanning import analyze, engine
from tests.helpers import make_ohlcv


@pytest.fixture(autouse=True)
def v2_on(monkeypatch):
    monkeypatch.setattr(config, "PLAN_ENGINE_V2", "on")
    monkeypatch.setattr(config, "CLAMP_STOP_TO_HARD_CAP", True)
    monkeypatch.setattr(config, "MIN_RISK_REWARD_RATIO", 1.5)
    monkeypatch.setattr(config, "MAX_RISK_REWARD_RATIO", 2.5)


def _scenario(stop, target, direction="bullish", entry=100.0):
    return SimpleNamespace(direction=direction, entry=entry, stop_loss=stop, take_profit=target,
                           target_sources=["EMA21"], stop_sources=["Rolling support"])


def _attach(scenario):
    item = SimpleNamespace(plan_v2=None)
    engine.attach_plan_v2(item, scenario, make_ohlcv([scenario.entry] * 60),
                          "AAPL", "4w", level_map=None)
    return item


def test_knobs_off_issue_todays_clamped_plan():
    item = _attach(_scenario(96.5, 108.0))
    assert item.plan_v2.stop_loss == pytest.approx(98.25)
    assert item.plan_v2.stop_ceiling_pct is None


def test_sizing_is_not_consulted_for_a_plan_without_a_stored_ceiling(monkeypatch):
    monkeypatch.setattr(analyze, "risk_sizing_ok", lambda plan: pytest.fail("consulted"))
    assert _attach(_scenario(96.5, 108.0)).plan_v2 is not None


def test_arm_s_plan_passes_the_risk_check_at_its_own_ceiling(monkeypatch):
    monkeypatch.setattr(config, "CONFLUENCE_STRUCTURAL_STOP_PCT", 4.0)
    monkeypatch.setattr(analyze, "risk_sizing_ok", lambda plan: True)
    item = _attach(_scenario(96.5, 108.0))
    assert getattr(item, "plan_v2_rejected", None) is None
    assert item.plan_v2.stop_loss == 96.5
    assert item.plan_v2.stop_ceiling_pct == 4.0


def test_arm_s_plan_without_risk_based_sizing_is_rejected(monkeypatch):
    monkeypatch.setattr(config, "CONFLUENCE_STRUCTURAL_STOP_PCT", 4.0)
    monkeypatch.setattr(analyze, "risk_sizing_ok", lambda plan: False)
    item = _attach(_scenario(96.5, 108.0))
    assert item.plan_v2 is None
    assert item.plan_v2_rejected == "risk_sizing"


@pytest.mark.parametrize("direction,stop,target", [("bullish", 96.5, 108.0),
                                                    ("bearish", 103.5, 92.0)])
def test_arm_d_drop_is_recorded_with_its_own_reason(monkeypatch, direction, stop, target):
    monkeypatch.setattr(config, "CONFLUENCE_STOP_DROP_PCT", 3.0)
    item = _attach(_scenario(stop, target, direction=direction))
    assert item.plan_v2 is None
    assert item.plan_v2_rejected == "stop_beyond_confluence_ceiling"


def test_arm_d_within_its_ceiling_keeps_todays_plan(monkeypatch):
    monkeypatch.setattr(config, "CONFLUENCE_STOP_DROP_PCT", 4.0)
    assert _attach(_scenario(96.5, 108.0)).plan_v2.stop_loss == pytest.approx(98.25)


def test_no_target_is_still_no_qualifying_target(monkeypatch):
    monkeypatch.setattr(config, "CONFLUENCE_STOP_DROP_PCT", 3.0)
    item = _attach(_scenario(98.5, 100.5))      # unclamped; 0.33R
    assert item.plan_v2_rejected == "no_qualifying_target"
