"""v129: exit on a daily CLOSE beyond the acceptance threshold (spec § Exit
rule). Order on one bar: stop -> target/TP1 -> acceptance -> stall -> timeout.
entry 100 (market, bar 0), stop 95, tp1 110 -> risk 5, rr 2; threshold 98."""
import pytest

from swingbot import config
from swingbot.core.planning.exit_sim import acceptance_exit, simulate_exit
from tests.helpers import make_ohlcv
from tests.planning.test_exit_sim_single import _plan

BOTH = pytest.mark.parametrize("scale_out", [False, True])


def _bull(**kw):
    return _plan(direction="bullish", stop_loss=95.0, tp1=110.0,
                 acceptance_close_below=98.0, **kw)


def _bear(**kw):
    return _plan(direction="bearish", stop_loss=105.0, tp1=90.0,
                 acceptance_close_below=102.0, **kw)


# --- the pure rule -------------------------------------------------------------

def test_acceptance_exit_bullish_strict_below():
    assert acceptance_exit(_bull(), 97.99) is True
    assert acceptance_exit(_bull(), 98.0) is False      # exactly on: no exit
    assert acceptance_exit(_bull(), 98.5) is False


def test_acceptance_exit_bearish_strict_above():
    assert acceptance_exit(_bear(), 102.01) is True
    assert acceptance_exit(_bear(), 102.0) is False
    assert acceptance_exit(_bear(), 101.0) is False


def test_acceptance_exit_none_threshold_never_fires():
    assert acceptance_exit(_plan(acceptance_close_below=None), 1.0) is False


# --- in the walks ------------------------------------------------------------------

@BOTH
def test_close_through_exits_at_the_close(scale_out):
    df = make_ohlcv([100.0, (99.0, 99.5, 97.5, 97.8), (97.8, 98.0, 96.0, 97.0)])
    res = simulate_exit(df, 0, _bull(), scale_out=scale_out)
    assert res.outcome == "loss"
    assert res.exit_index == 1
    assert res.legs == [{"fraction": 1.0, "exit_price": 97.8,
                         "r": pytest.approx(-0.44), "reason": "acceptance_exit"}]
    assert res.r_total == pytest.approx(-0.44)


@BOTH
def test_wick_only_bar_does_not_exit(scale_out):
    df = make_ohlcv([100.0, (99.0, 99.5, 97.0, 98.5), (98.5, 111.0, 98.4, 110.5)])
    res = simulate_exit(df, 0, _bull(), scale_out=scale_out)
    assert res.outcome == "win"          # bar 2 reaches TP1; bar 1 only wicked
    assert res.exit_index == 2
    assert all(leg["reason"] != "acceptance_exit" for leg in res.legs)


@BOTH
def test_close_exactly_on_threshold_does_not_exit(scale_out):
    df = make_ohlcv([100.0, (99.0, 99.5, 97.5, 98.0), (98.0, 111.0, 97.9, 110.5)])
    res = simulate_exit(df, 0, _bull(), scale_out=scale_out)
    assert all(leg["reason"] != "acceptance_exit" for leg in res.legs)


@BOTH
def test_stop_and_close_through_on_one_bar_stop_wins(scale_out):
    df = make_ohlcv([100.0, (99.0, 99.5, 94.0, 96.0)])
    res = simulate_exit(df, 0, _bull(), scale_out=scale_out)
    assert res.outcome == "loss"
    assert res.r_total == -1.0
    assert res.legs[0]["reason"] == "stop"


def test_tp1_and_close_through_on_one_bar_banks_tp1_then_exits_runner():
    df = make_ohlcv([100.0, (100.0, 111.0, 97.0, 97.5), (97.5, 120.0, 97.0, 119.0)])
    res = simulate_exit(df, 0, _bull(), scale_out=True)
    assert res.outcome == "win"
    assert res.runner_outcome == "acceptance_exit"
    assert res.exit_index == 1
    assert res.legs[0] == {"fraction": 0.5, "exit_price": 110.0, "r": pytest.approx(2.0),
                           "reason": "tp1"}
    assert res.legs[1]["exit_price"] == pytest.approx(97.5)
    assert res.legs[1]["r"] == pytest.approx(-0.5)
    assert res.legs[1]["reason"] == "acceptance_exit"
    assert res.r_total == pytest.approx(0.75)


def test_single_leg_tp1_and_close_through_is_a_plain_win():
    df = make_ohlcv([100.0, (100.0, 111.0, 97.0, 97.5)])
    res = simulate_exit(df, 0, _bull(), scale_out=False)
    assert res.outcome == "win" and res.r_total == pytest.approx(2.0)


@BOTH
def test_bearish_mirror_close_through(scale_out):
    df = make_ohlcv([100.0, (101.0, 102.5, 100.5, 102.2)])
    res = simulate_exit(df, 0, _bear(), scale_out=scale_out)
    assert res.legs[0]["reason"] == "acceptance_exit"
    assert res.legs[0]["exit_price"] == pytest.approx(102.2)
    assert res.r_total == pytest.approx(-0.44)


def test_acceptance_beats_stall_on_the_same_bar(monkeypatch):
    monkeypatch.setattr(config, "STALL_EXIT_ENABLED", True)
    # Bar 1 is past stall_exit_day 0 AND below +0.5R AND closes through 98:
    # both rules are live on the same bar; acceptance is checked first.
    df = make_ohlcv([100.0, (99.0, 99.5, 97.5, 97.8)])
    res = simulate_exit(df, 0, _bull(stall_exit_day=0), scale_out=True)
    assert res.exit_index == 1
    assert res.legs[0]["reason"] == "acceptance_exit"


def test_stall_still_fires_without_a_threshold(monkeypatch):
    monkeypatch.setattr(config, "STALL_EXIT_ENABLED", True)
    df = make_ohlcv([100.0, 100.0, 101.0, 101.0])
    plan = _plan(direction="bullish", stop_loss=90.0, tp1=120.0, stall_exit_day=1)
    res = simulate_exit(df, 0, plan, scale_out=True)
    assert res.legs[0]["reason"] == "stall_exit"
    assert res.exit_index == 2
