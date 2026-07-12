"""Task 24: scale-out (TP1 partial + break-even runner) exit walk tests.

Only the scope-note's reduced `_scale_out_exit_walk` is exercised here: phase 1
(pre-TP1) is byte-identical to the single-leg walk, and the runner phase's
stop stays fixed at break-even for the whole runner phase (no chandelier
trail, no TP2 check -- those are Tasks 25/26).
"""
import pytest

from swingbot.core.plan_engine import simulate_exit
from tests.test_exit_sim_single import _plan
from tests.helpers import make_ohlcv


def test_bullish_tp1_partial_then_runner_stopped_at_breakeven():
    # entry 100, stop 95, tp1 110 -> rr = 2. Rise through TP1, fall back to entry.
    df = make_ohlcv([
        100.0,                           # 0: entry bar
        (100.0, 111.0, 99.5, 110.5),     # 1: High 111 >= tp1 110 -- leg 1 banked
        (110.0, 110.5, 104.0, 105.0),    # 2: above entry -- runner survives
        (105.0, 105.5, 99.5, 100.5),     # 3: Low 99.5 <= runner stop 100 -- runner_be
    ])
    plan = _plan(direction="bullish", stop_loss=95.0, tp1=110.0, tp2=None)
    result = simulate_exit(df, signal_index=0, plan=plan, scale_out=True)
    rr = 2.0
    assert result.outcome == "win"
    assert result.runner_outcome == "runner_be"
    assert result.exit_index == 3
    assert result.r_total == pytest.approx(rr * 0.5)
    assert len(result.legs) == 2
    assert result.legs[0] == {"fraction": 0.5, "exit_price": 110.0,
                              "r": pytest.approx(rr), "reason": "tp1"}
    assert result.legs[1]["r"] == pytest.approx(0.0)
    assert result.legs[1]["reason"] == "runner_be"


def test_bearish_mirror_runner_be():
    df = make_ohlcv([
        100.0,
        (100.0, 100.5, 89.0, 90.5),      # 1: Low 89 <= tp1 90 -- leg 1 banked
        (91.0, 100.5, 90.5, 99.5),       # 2: High 100.5 >= runner stop 100 -- runner_be
    ])
    plan = _plan(direction="bearish", stop_loss=105.0, tp1=90.0, tp2=None)
    result = simulate_exit(df, signal_index=0, plan=plan, scale_out=True)
    assert result.outcome == "win" and result.runner_outcome == "runner_be"
    assert result.r_total == pytest.approx(2.0 * 0.5)


def test_pre_tp1_loss_is_identical_to_single_leg():
    df = make_ohlcv([100.0, (100.0, 101.0, 94.0, 95.0)])
    plan = _plan(direction="bullish", stop_loss=95.0, tp1=110.0)
    result = simulate_exit(df, signal_index=0, plan=plan, scale_out=True)
    assert result.outcome == "loss" and result.runner_outcome is None
    assert result.legs == [{"fraction": 1.0, "exit_price": 95.0,
                            "r": pytest.approx(-1.0), "reason": "stop"}]


def test_runner_rides_to_tp2():
    # entry 100, stop 95, tp1 110 (rr=2), tp2 = 118 -> leg2 r = 18/5 = 3.6
    df = make_ohlcv([
        100.0,
        (100.0, 111.0, 99.5, 110.5),     # 1: TP1 banked
        (110.0, 115.0, 109.0, 114.0),    # 2: climbing, runner alive
        (114.0, 119.0, 113.0, 117.0),    # 3: High 119 >= tp2 118 -- runner_tp2
    ])
    plan = _plan(direction="bullish", stop_loss=95.0, tp1=110.0, tp2=118.0)
    result = simulate_exit(df, signal_index=0, plan=plan, scale_out=True)
    assert result.outcome == "win" and result.runner_outcome == "runner_tp2"
    assert result.exit_index == 3
    assert result.legs[1]["exit_price"] == 118.0
    assert result.legs[1]["r"] == pytest.approx(3.6)
    assert result.r_total == pytest.approx(0.5 * 2.0 + 0.5 * 3.6)


def test_tp2_none_means_runner_ignores_it():
    # Same tape, tp2=None: bar 3's spike to 119 must NOT close the runner.
    df = make_ohlcv([
        100.0,
        (100.0, 111.0, 99.5, 110.5),
        (110.0, 115.0, 109.0, 114.0),
        (114.0, 119.0, 113.0, 117.0),
        (117.0, 117.5, 99.0, 100.0),     # 4: collapse to runner stop
    ])
    plan = _plan(direction="bullish", stop_loss=95.0, tp1=110.0, tp2=None)
    result = simulate_exit(df, signal_index=0, plan=plan, scale_out=True)
    assert result.runner_outcome != "runner_tp2"
    assert result.exit_index == 4


def test_same_bar_runner_stop_and_tp2_is_conservative_stop_first():
    # Runner bar spans BOTH the runner stop (100, BE) and tp2: stop wins.
    df = make_ohlcv([
        100.0,
        (100.0, 111.0, 99.5, 110.5),     # 1: TP1 banked
        (110.0, 119.0, 99.0, 105.0),     # 2: High >= tp2 118 AND Low <= BE 100
    ])
    plan = _plan(direction="bullish", stop_loss=95.0, tp1=110.0, tp2=118.0)
    result = simulate_exit(df, signal_index=0, plan=plan, scale_out=True)
    assert result.runner_outcome == "runner_be"
    assert result.legs[1]["r"] == pytest.approx(0.0)
