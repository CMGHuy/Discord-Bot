"""v191 flag-off parity (spec § Testing, first bullet): with
CONFLUENCE_ATR_STOP_FLOOR at 0 (and the v139 knobs at 0, LONG_GAP_SIZING off)
the confluence replay builds and exits exactly the plans it did before v191
touched builders.py, levels.py, backtest_scenarios.py or gap_sizing.py. The
golden was captured at V191-1, before any v191 code change -- never
regenerate it to make this pass."""
import json
import os
from pathlib import Path

import pytest

from swingbot import config
from swingbot.core.backtesting import backtest_scenarios as bs
from swingbot.core.planning.exit_sim import simulate_exit
from swingbot.core.risk_limits import HARD_MAX_PLANNED_LOSS_PCT, planned_loss_pct
from tests.backtesting.test_backtest_scenarios import GATES, _structured_df
from tests.fixtures.ohlcv_parity import load_ohlcv

pytestmark = pytest.mark.slow

GOLDEN = Path(__file__).resolve().parent.parent / "fixtures" / "v191" / "flag_off_golden.json"
DELL_END = "2019-12-31"
TRIGGER, LEVEL, CEILING = 4, 8, 12      # row positions of trigger_price, acceptance_level, stop_ceiling_pct
#: Every knob at its inert value. raising=False: the v191 attributes exist from V191-2 on.
INERT = {"CONFLUENCE_ATR_STOP_FLOOR": 0.0, "CONFLUENCE_ATR_TARGET_MODE": "rechoose",
         "LONG_GAP_SIZING": False, "CONFLUENCE_STRUCTURAL_STOP_PCT": 0.0,
         "CONFLUENCE_STOP_DROP_PCT": 0.0}


@pytest.fixture(autouse=True)
def _inert(monkeypatch):
    for attr, value in INERT.items():
        monkeypatch.setattr(config, attr, value, raising=False)


def _r6(value):
    return None if value is None else round(float(value), 6)


def _rows(ticker, df):
    rows = []
    for i, plan in bs.replay_scenarios(ticker, df, "4w", gates=GATES):
        res = simulate_exit(df, i, plan, scale_out=True)
        exit_index = None if res.exit_index is None else int(res.exit_index)
        rows.append([ticker, int(i), plan.direction, plan.entry_type, _r6(plan.trigger_price),
                     _r6(plan.stop_loss), _r6(plan.tp1), _r6(plan.tp2),
                     _r6(plan.acceptance_level), res.outcome, _r6(res.r_total), exit_index,
                     _r6(plan.stop_ceiling_pct)])
    return rows


def _capture():
    return {"structured": _rows("AAPL", _structured_df()),
            "dell": _rows("DELL", load_ohlcv("DELL").loc[:DELL_END])}


def _golden(captured):
    if os.environ.get("V191_CAPTURE_GOLDEN") == "1" and not GOLDEN.exists():
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(json.dumps(captured, indent=1) + "\n", encoding="utf-8")
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def _clamped(rows):
    return [r for r in rows if r[LEVEL] is not None
            and planned_loss_pct(r[TRIGGER], r[LEVEL]) > HARD_MAX_PLANNED_LOSS_PCT]


def test_knobs_off_replay_matches_the_pre_v191_golden():
    captured = json.loads(json.dumps(_capture()))
    golden = _golden(captured)
    assert len(_clamped(golden["dell"])) >= 5, "the golden must exercise clamped plans"
    assert all(row[CEILING] is None for rows in golden.values() for row in rows), (
        "with every knob off no confluence plan stores a ceiling")
    assert captured == golden
