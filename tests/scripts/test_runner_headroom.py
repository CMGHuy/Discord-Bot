import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "reports"))
from runner_headroom import runner_metrics, stop_rule, summarise  # noqa: E402

from swingbot.core.planning.plan_engine import simulate_exit
from tests.helpers import make_ohlcv
from tests.planning.test_exit_sim_single import _plan


def test_mfe_is_best_close_after_tp1_before_exit():
    df = make_ohlcv([100.0, (100, 111, 99.5, 110.5), (110, 114, 108, 113.0),
                     (113, 113.5, 107, 108.5)])
    plan = _plan(stop_loss=95.0, tp1=110.0, tp2=None)
    result = simulate_exit(df, 0, plan, scale_out=True)
    row = runner_metrics(df, result, plan)
    assert row["reason"] == "runner_trail"
    assert row["runner_r"] == pytest.approx(1.6)
    assert row["mfe_r"] == pytest.approx((113.0 - 100.0) / 5.0)   # bar 2's close
    assert row["capture"] == pytest.approx(1.6 / 2.6)


def test_non_runner_trade_is_excluded():
    df = make_ohlcv([100.0, (100, 101, 94, 95)])
    plan = _plan(stop_loss=95.0, tp1=110.0)
    assert runner_metrics(df, simulate_exit(df, 0, plan, scale_out=True), plan) is None


def test_frozen_stop_rule():
    rows = [{"horizon_key": "2w", "source": "strategy", "runner_r": 1.0, "mfe_r": 1.25,
             "capture": 0.8, "reason": "runner_trail"}]
    assert stop_rule(summarise(rows)) == "NO_HEADROOM"
    rows[0]["capture"] = 0.74
    assert stop_rule(summarise(rows)) == "HEADROOM"
