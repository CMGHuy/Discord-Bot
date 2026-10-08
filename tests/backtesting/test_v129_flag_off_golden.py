"""v129 flag-off parity (spec § Testing, first bullet): with
ACCEPTANCE_EXIT_ENABLED off, the Break & Retest backtest and the confluence
replay produce exactly the exits they produced before v129 touched
builders.py, backtest.py or exit_sim.py. The golden was captured at V129-0,
before any v129 code change -- never regenerate it to make this pass."""
import json
from pathlib import Path

import pytest

from swingbot import config
from swingbot.core.backtesting import backtest_scenarios as bs
from swingbot.core.backtesting.backtest import run_backtest
from swingbot.core.planning.exit_sim import simulate_exit
from tests.backtesting.test_backtest_scenarios import GATES, _structured_df
from tests.fixtures.ohlcv_parity import load_ohlcv

pytestmark = pytest.mark.slow

GOLDEN = Path(__file__).resolve().parent.parent / "fixtures" / "v129" / "flag_off_golden.json"
# The only Break & Retest cells the frozen fixtures trade (3 trades total).
BR_CASES = (("DELL", "2m"), ("DELL", "3m"))


def _r6(value):
    return None if value is None else round(float(value), 6)


def _break_retest_rows():
    rows = []
    for ticker, horizon_key in BR_CASES:
        summary = run_backtest(ticker, load_ohlcv(ticker), "Break & Retest", horizon_key,
                               exit_model="v2", scale_out=True, tp2_mode="levels")
        rows += [[ticker, horizon_key, t.entry_date, t.exit_date, t.direction,
                  _r6(t.stop_loss), _r6(t.take_profit), t.outcome, _r6(t.r_multiple),
                  t.runner_outcome] for t in summary.trades]
    return rows


def _confluence_rows():
    df = _structured_df()
    rows = []
    for i, plan in bs.replay_scenarios("AAPL", df, "4w", gates=GATES):
        res = simulate_exit(df, i, plan, scale_out=True)
        exit_index = None if res.exit_index is None else int(res.exit_index)
        rows.append([int(i), plan.direction, plan.entry_type, _r6(plan.stop_loss),
                     _r6(plan.tp1), res.outcome, _r6(res.r_total), exit_index])
    return rows


def _capture():
    return {"break_retest": _break_retest_rows(), "confluence": _confluence_rows()}


def test_flag_off_exits_match_the_pre_v129_golden(monkeypatch):
    # raising=False: the attribute only exists from V129-5 on.
    monkeypatch.setattr(config, "ACCEPTANCE_EXIT_ENABLED", False, raising=False)
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert golden["break_retest"] and golden["confluence"], "golden must be non-empty"
    assert _capture() == golden
