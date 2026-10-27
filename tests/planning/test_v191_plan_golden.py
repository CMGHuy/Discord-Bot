"""v191 flag-off parity for the builder: with every v191 knob at its default,
build_confluence_plan returns exactly the plan dicts it did before V191-8
touched it -- same stop, ceiling, targets and the same persisted key list (no
stop_moved_by). Captured at V191-1 on unmodified code; never regenerate."""
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

GOLDEN = Path(__file__).resolve().parent.parent / "fixtures" / "v191" / "plan_golden.json"
INERT = {"CONFLUENCE_ATR_STOP_FLOOR": 0.0, "CONFLUENCE_ATR_TARGET_MODE": "rechoose",
         "LONG_GAP_SIZING": False, "CONFLUENCE_STRUCTURAL_STOP_PCT": 0.0,
         "CONFLUENCE_STOP_DROP_PCT": 0.0, "CLAMP_STOP_TO_HARD_CAP": True}
#: name -> (direction, entry, level stop, own target)
SCENARIOS = {
    "bull_inside": ("bullish", 100.0, 98.2, 104.0),
    "bull_clamped": ("bullish", 100.0, 96.5, 108.0),
    "bull_tight": ("bullish", 100.0, 99.0, 103.0),
    "bear_inside": ("bearish", 100.0, 101.8, 96.0),
    "bear_clamped": ("bearish", 100.0, 103.5, 92.0),
    "bear_tight": ("bearish", 100.0, 101.0, 97.0),
    "penny_bull": ("bullish", 0.85, 0.835, 0.88),
}
SKIP = ("plan_id", "badge", "badge_stats", "cohort_label", "cohort_stats", "ledger")


@pytest.fixture(autouse=True)
def _inert(monkeypatch):
    for attr, value in INERT.items():
        monkeypatch.setattr(config, attr, value, raising=False)


def _params():
    return dataclasses.replace(ScanParams.from_config(), min_risk_reward_ratio=1.5,
                               max_risk_reward_ratio=2.5, confluence_structural_stop_pct=0.0,
                               confluence_stop_drop_pct=0.0)


def _snapshot(direction, entry, stop, target):
    scenario = types.SimpleNamespace(direction=direction, entry=entry, stop_loss=stop,
                                     take_profit=target, target_sources=["Rolling S/R"],
                                     stop_sources=["Rolling S/R"])
    plan = build_confluence_plan(scenario, make_ohlcv([entry] * 60, spread=0.02), ticker="XYZ",
                                 horizon_key="4w", primary_strategy="S/R Confluence",
                                 level_map=None, params=_params())
    if plan is None:
        return None
    d = plan_to_dict(plan)
    return {"keys": list(d), "plan": {k: v for k, v in d.items() if k not in SKIP}}


def _capture():
    return {name: _snapshot(*args) for name, args in SCENARIOS.items()}


def _golden(captured):
    if os.environ.get("V191_CAPTURE_GOLDEN") == "1" and not GOLDEN.exists():
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(json.dumps(captured, indent=1) + "\n", encoding="utf-8")
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def test_knobs_off_confluence_plans_match_the_pre_v191_golden():
    captured = json.loads(json.dumps(_capture()))
    golden = _golden(captured)
    built = [snap for snap in golden.values() if snap is not None]
    assert len(built) >= 5, "the golden must hold real plans, not a row of Nones"
    assert all("stop_moved_by" not in snap["keys"] for snap in built)
    assert captured == golden
