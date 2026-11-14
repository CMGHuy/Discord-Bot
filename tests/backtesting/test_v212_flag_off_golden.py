"""v212 flag-off parity: with CONFLUENCE_LIMIT_ENTRY_F at 0 (and the v139/v191
knobs inert, LONG_GAP_SIZING off) the confluence replay builds and exits,
through simulate_exit_v2, exactly the plans it did before V212-3 touched
builders.py. The golden was captured at V212-3 Step 2, before any builder
change -- never regenerate it to make this pass."""
import json
import os
from pathlib import Path

import pytest

from swingbot import config
from swingbot.core.backtesting import backtest_scenarios as bs
from swingbot.core.backtesting.instrument.contract import resolve
from swingbot.core.planning.exit_sim_v2 import simulate_exit_v2
from swingbot.core.planning.plan_types import plan_to_dict
from swingbot.core.risk_limits import HARD_MAX_PLANNED_LOSS_PCT, planned_loss_pct
from tests.backtesting.test_backtest_scenarios import GATES, _structured_df
from tests.fixtures.ohlcv_parity import load_ohlcv

pytestmark = pytest.mark.slow

GOLDEN = Path(__file__).resolve().parent.parent / "fixtures" / "v212" / "replay_golden.json"
DELL_END = "2019-12-31"
ENTRY_TYPE, TRIGGER, LEVEL, KEYS = 3, 4, 8, 13   # row positions
V2 = resolve("v2")
#: Every knob at its inert value.
INERT = {"CONFLUENCE_LIMIT_ENTRY_F": 0.0, "CONFLUENCE_ATR_STOP_FLOOR": 0.0,
         "CONFLUENCE_ATR_TARGET_MODE": "rechoose", "LONG_GAP_SIZING": False,
         "CONFLUENCE_STRUCTURAL_STOP_PCT": 0.0, "CONFLUENCE_STOP_DROP_PCT": 0.0}


@pytest.fixture(autouse=True)
def _inert(monkeypatch):
    for attr, value in INERT.items():
        monkeypatch.setattr(config, attr, value, raising=False)


def _r6(value):
    return None if value is None else round(float(value), 6)


def _rows(ticker, df):
    rows = []
    for i, plan in bs.replay_scenarios(ticker, df, "4w", gates=GATES):
        res = simulate_exit_v2(df, i, plan, V2, scale_out=True)   # the path V212-5 edits
        rows.append([ticker, int(i), plan.direction, plan.entry_type, _r6(plan.trigger_price),
                     _r6(plan.stop_loss), _r6(plan.tp1), _r6(plan.tp2),
                     _r6(plan.acceptance_level), res.outcome, _r6(res.r_total),
                     None if res.exit_index is None else int(res.exit_index),
                     None if res.entry_index is None else int(res.entry_index),
                     sorted(plan_to_dict(plan))])
    return rows


def _capture():
    return {"structured": _rows("AAPL", _structured_df()),
            "dell": _rows("DELL", load_ohlcv("DELL").loc[:DELL_END])}


def _golden(captured):
    if os.environ.get("V212_CAPTURE_GOLDEN") == "1" and not GOLDEN.exists():
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(json.dumps(captured, indent=1) + "\n", encoding="utf-8")
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def _clamped(rows):
    return [r for r in rows if r[LEVEL] is not None
            and planned_loss_pct(r[TRIGGER], r[LEVEL]) > HARD_MAX_PLANNED_LOSS_PCT]


def test_knob_zero_replay_matches_the_pre_v212_golden():
    captured = json.loads(json.dumps(_capture()))
    golden = _golden(captured)
    assert len(_clamped(golden["dell"])) >= 5, "the golden must exercise clamped plans"
    rows = [row for rows in golden.values() for row in rows]
    assert all("limit_entry_f" not in row[KEYS] for row in rows)
    assert all(row[ENTRY_TYPE] != "limit" for row in rows)
    assert captured == golden
