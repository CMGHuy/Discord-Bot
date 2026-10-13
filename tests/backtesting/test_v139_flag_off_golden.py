"""v139 flag-off parity (spec § Testing, first bullet): with
CONFLUENCE_STRUCTURAL_STOP_PCT and CONFLUENCE_STOP_DROP_PCT at 0, the
confluence replay builds and exits exactly the plans it did before v139
touched builders.py, stop_scope.py or analyze.py. The golden was captured at
V139-0, before any v139 code change -- never regenerate it to make this pass."""
import json
from pathlib import Path

import pytest

from swingbot import config
from swingbot.core.backtesting import backtest_scenarios as bs
from swingbot.core.planning.exit_sim import simulate_exit
from swingbot.core.risk_limits import HARD_MAX_PLANNED_LOSS_PCT, planned_loss_pct
from tests.backtesting.test_backtest_scenarios import GATES, _structured_df
from tests.fixtures.ohlcv_parity import load_ohlcv

pytestmark = pytest.mark.slow

GOLDEN = Path(__file__).resolve().parent.parent / "fixtures" / "v139" / "flag_off_golden.json"
#: DELL 4w through 2019 under GATES: 40 plans, 9 clamped (d 2.04 .. 5.55).
DELL_END = "2019-12-31"
TRIGGER, LEVEL = 4, 8      # row positions of trigger_price and acceptance_level


def _r6(value):
    return None if value is None else round(float(value), 6)


def _rows(ticker, df):
    rows = []
    for i, plan in bs.replay_scenarios(ticker, df, "4w", gates=GATES):
        res = simulate_exit(df, i, plan, scale_out=True)
        exit_index = None if res.exit_index is None else int(res.exit_index)
        rows.append([ticker, int(i), plan.direction, plan.entry_type, _r6(plan.trigger_price),
                     _r6(plan.stop_loss), _r6(plan.tp1), _r6(plan.tp2),
                     _r6(plan.acceptance_level), res.outcome, _r6(res.r_total), exit_index])
    return rows


def _capture():
    return {"structured": _rows("AAPL", _structured_df()),
            "dell": _rows("DELL", load_ohlcv("DELL").loc[:DELL_END])}


def _clamped(rows):
    return [r for r in rows if r[LEVEL] is not None
            and planned_loss_pct(r[TRIGGER], r[LEVEL]) > HARD_MAX_PLANNED_LOSS_PCT]


def test_knobs_off_replay_matches_the_pre_v139_golden(monkeypatch):
    # raising=False: the attributes only exist from V139-2 on.
    monkeypatch.setattr(config, "CONFLUENCE_STRUCTURAL_STOP_PCT", 0.0, raising=False)
    monkeypatch.setattr(config, "CONFLUENCE_STOP_DROP_PCT", 0.0, raising=False)
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert len(_clamped(golden["dell"])) >= 5, "the golden must exercise clamped plans"
    assert _capture() == golden
