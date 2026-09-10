"""The v74 default parameter seam must reproduce pre-v74 replay plans."""
import json
from pathlib import Path

from swingbot.core.backtesting.backtest_scenarios import replay_scenarios
from swingbot.scan_params import ScanParams

from .test_v74_fixture import load_v74_fixture

GOLDEN = Path(__file__).resolve().parent.parent / "fixtures" / "v74" / "golden_plans.json"


def _round(value):
    return None if value is None else round(float(value), 6)


def test_from_config_reproduces_pre_v74_golden_plans():
    rows = []
    for symbol, frame in load_v74_fixture().items():
        for horizon in ("4w", "3m"):
            for index, plan in replay_scenarios(symbol, frame, horizon,
                                                params=ScanParams.from_config()):
                rows.append([symbol, horizon, int(index), _round(plan.trigger_price),
                             _round(plan.entry_price), _round(plan.stop_loss),
                             _round(plan.tp1), _round(plan.tp2)])
    assert rows == json.loads(GOLDEN.read_text())
