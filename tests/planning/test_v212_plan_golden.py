"""v212 knob-0 parity for the builder: with CONFLUENCE_LIMIT_ENTRY_F at 0,
build_confluence_plan returns exactly the plan dicts it did before V212-3
touched it. Captured at V212-3 Step 2 on unmodified builder code; never
regenerate. Above 0, only in-scope (clamped) scenarios change."""
import dataclasses
import json
import os
import types
from pathlib import Path

import pytest

from swingbot import config
from swingbot.core.planning.plan_engine import build_confluence_plan
from swingbot.core.planning.plan_types import plan_to_dict
from swingbot.scan_params import ScanParams
from tests.helpers import make_ohlcv

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
GOLDEN = FIXTURES / "v212" / "plan_golden.json"
V191_GOLDEN = FIXTURES / "v191" / "plan_golden.json"
INERT = {"CONFLUENCE_LIMIT_ENTRY_F": 0.0, "CONFLUENCE_ATR_STOP_FLOOR": 0.0,
         "CONFLUENCE_ATR_TARGET_MODE": "rechoose", "LONG_GAP_SIZING": False,
         "CONFLUENCE_STRUCTURAL_STOP_PCT": 0.0, "CONFLUENCE_STOP_DROP_PCT": 0.0,
         "CLAMP_STOP_TO_HARD_CAP": True}
#: name -> (direction, entry, level stop, own target); the v191 seven plus two far levels
SCENARIOS = {
    "bull_inside": ("bullish", 100.0, 98.2, 104.0),
    "bull_clamped": ("bullish", 100.0, 96.5, 108.0),
    "bull_tight": ("bullish", 100.0, 99.0, 103.0),
    "bear_inside": ("bearish", 100.0, 101.8, 96.0),
    "bear_clamped": ("bearish", 100.0, 103.5, 92.0),
    "bear_tight": ("bearish", 100.0, 101.0, 97.0),
    "penny_bull": ("bullish", 0.85, 0.835, 0.88),
    "bull_far": ("bullish", 100.0, 97.0, 110.0),
    "bear_far": ("bearish", 100.0, 103.0, 90.0),
}
IN_SCOPE = ("bull_clamped", "bear_clamped", "bull_far", "bear_far")
SKIP = ("plan_id", "badge", "badge_stats", "cohort_label", "cohort_stats", "ledger")


@pytest.fixture(autouse=True)
def _inert(monkeypatch):
    for attr, value in INERT.items():
        monkeypatch.setattr(config, attr, value, raising=False)


def _params(f=0.0):
    return dataclasses.replace(ScanParams.from_config(), min_risk_reward_ratio=1.5,
                               max_risk_reward_ratio=2.5, confluence_structural_stop_pct=0.0,
                               confluence_stop_drop_pct=0.0, confluence_limit_entry_f=f)


def _ranged(entry):
    """A frame whose 20-bar range holds every target, so the scenario is not a
    breakout (scenario_is_breakout) and the plan enters at market -- the only
    entry type v212 converts. The flat frame makes every SCENARIOS plan a
    stop_entry, which is what the goldens hold."""
    return make_ohlcv([entry] * 49 + [(entry, entry * 1.12, entry * 0.88, entry)]
                      + [entry] * 10, spread=0.02)


def _build(direction, entry, stop, target, f=0.0, df=None):
    scenario = types.SimpleNamespace(direction=direction, entry=entry, stop_loss=stop,
                                     take_profit=target, target_sources=["Rolling S/R"],
                                     stop_sources=["Rolling S/R"])
    if df is None:
        df = make_ohlcv([entry] * 60, spread=0.02)
    return build_confluence_plan(scenario, df, ticker="XYZ",
                                 horizon_key="4w", primary_strategy="S/R Confluence",
                                 level_map=None, params=_params(f))


def _snapshot(*args, f=0.0):
    plan = _build(*args, f=f)
    if plan is None:
        return None
    d = plan_to_dict(plan)
    return {"keys": list(d), "plan": {k: v for k, v in d.items() if k not in SKIP}}


def _capture(f=0.0):
    return json.loads(json.dumps({name: _snapshot(*a, f=f) for name, a in SCENARIOS.items()}))


def _golden(captured):
    if os.environ.get("V212_CAPTURE_GOLDEN") == "1" and not GOLDEN.exists():
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(json.dumps(captured, indent=1) + "\n", encoding="utf-8")
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def test_knob_zero_confluence_plans_match_the_pre_v212_golden():
    captured = _capture()
    golden = _golden(captured)
    built = [snap for snap in golden.values() if snap is not None]
    assert len(built) >= 7, "the golden must hold real plans, not a row of Nones"
    assert all("limit_entry_f" not in snap["keys"] for snap in built)
    assert captured == golden


def test_golden_agrees_with_the_pre_v191_capture_on_shared_scenarios():
    golden, v191 = (json.loads(p.read_text(encoding="utf-8")) for p in (GOLDEN, V191_GOLDEN))
    shared = set(golden) & set(v191)
    assert len(shared) == 7
    assert all(golden[name] == v191[name] for name in shared)


@pytest.mark.parametrize("f", [1 / 3, 0.5, 2 / 3])
def test_knob_on_leaves_out_of_scope_scenarios_identical(f):
    golden, captured = _golden(_capture()), _capture(f)
    for name in set(SCENARIOS) - set(IN_SCOPE):
        assert captured[name] == golden[name], name


@pytest.mark.parametrize("name", IN_SCOPE)
def test_knob_on_turns_in_scope_scenarios_into_limits_or_drops(name):
    df = _ranged(SCENARIOS[name][1])
    ref = _build(*SCENARIOS[name], df=df)
    arm = _build(*SCENARIOS[name], f=2 / 3, df=df)
    assert ref.entry_type == "market" and arm is not None
    assert (arm.entry_type, arm.limit_entry_f, arm.expiry_bars) == ("limit", 2 / 3, 3)
    assert (arm.tp1, arm.tp2, arm.limit_cancel_level) == (ref.tp1, ref.tp2, ref.tp1)
    assert arm.acceptance_level == ref.acceptance_level == SCENARIOS[name][2]
    assert arm.status == "PENDING" and arm.entry_price is None
