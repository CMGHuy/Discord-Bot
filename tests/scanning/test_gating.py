import dataclasses

from swingbot.core.scanning.gating import HARD_MAX_PLANNED_LOSS_PCT, passes_confluence, scenario_gate_inputs
from swingbot.scan_params import ScanParams


HORIZON = {"bars": 60, "label": "3m", "sr_target_min_pct": 8.0, "max_risk_pct": 9.0}


def test_gate_inputs_never_widen_the_hard_planned_loss_ceiling():
    params = dataclasses.replace(ScanParams.from_config(), min_reward_pct=3.0, max_stop_loss_pct=7.0)
    got = scenario_gate_inputs(params, HORIZON)
    assert got["min_reward_pct"] == 3.0
    assert got["max_stop_distance_pct"] == HARD_MAX_PLANNED_LOSS_PCT


def test_gate_inputs_allow_a_user_to_choose_a_tighter_stop():
    params = dataclasses.replace(ScanParams.from_config(), max_stop_loss_pct=1.5)
    assert scenario_gate_inputs(params, HORIZON)["max_stop_distance_pct"] == 1.5


def test_confluence_uses_the_explicit_params_value():
    params = dataclasses.replace(ScanParams.from_config(), min_target_confluence_count=2)
    assert passes_confluence(2, params)
    assert not passes_confluence(1, params)
