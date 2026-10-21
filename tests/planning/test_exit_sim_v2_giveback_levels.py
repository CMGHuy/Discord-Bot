"""v178 V178-2: the v2 walk follows every give-back arm exactly as the v1 walk.

Frames and helpers come from test_giveback_levels.py (V178-1); its module
docstring derives every level. The v2 walk runs with zero costs, so a stop
filled at its level (every open here sits on the profit side of the level)
matches the v1 exit price.
"""
import dataclasses

import pytest

from swingbot import config
from swingbot.core.backtesting.instrument.contract import ZERO_COSTS, resolve
from swingbot.core.planning import exit_sim
from swingbot.core.planning.exit_sim_v2 import walk_v2
from swingbot.core.planning.plan_engine import simulate_exit
from tests.helpers import make_ohlcv
from tests.planning.test_giveback_levels import (ARMS, ENTRY, FLOOR, JUMP, NAN_ATR_BARS,
                                                 REVERSE, _arm, _bear, _bull, _mirror)

FREE = dataclasses.replace(resolve("v2"), cost_model=ZERO_COSTS)
FRAMES = [("reverse-long", REVERSE, _bull), ("jump-long", JUMP, _bull),
          ("reverse-short", _mirror(REVERSE), _bear), ("jump-short", _mirror(JUMP), _bear)]


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_ENABLED", True)
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_PCT", 5.0)
    monkeypatch.setattr(config, "RUNNER_STRUCTURE_EXIT", "off")
    monkeypatch.setattr(config, "ADAPTIVE_RUNNER_TRAIL_ENABLED", False)
    monkeypatch.setattr(config, "STALL_EXIT_ENABLED", False)
    monkeypatch.setattr(exit_sim, "GIVEBACK_EXTREME_BASIS", "close")
    monkeypatch.setattr(exit_sim, "GIVEBACK_MODE", "pct")
    monkeypatch.setattr(exit_sim, "GIVEBACK_K", 1.0)
    monkeypatch.setattr(exit_sim, "GIVEBACK_F", 0.33)


def _v1(bars, plan, entry=ENTRY):
    return simulate_exit(make_ohlcv(bars), entry, plan, scale_out=True, max_holding_days=10)


def _v2(bars, plan, entry=ENTRY):
    return walk_v2(make_ohlcv(bars), entry, 100.0, plan, 10, FREE, scale_out=True)


@pytest.mark.parametrize("mode, k, f", ARMS)
@pytest.mark.parametrize("name, bars, plan", FRAMES, ids=[f[0] for f in FRAMES])
def test_v1_and_v2_agree_on_every_arm(monkeypatch, mode, k, f, name, bars, plan):
    _arm(monkeypatch, mode, k, f)
    v1, v2 = _v1(bars, plan()), _v2(bars, plan())
    assert (v1.outcome, v1.exit_index, v1.runner_outcome, v1.runner_stop_source) == \
           (v2.outcome, v2.exit_index, v2.runner_outcome, v2.runner_stop_source)
    assert v1.legs[1]["exit_price"] == pytest.approx(v2.legs[1]["exit_price"])


@pytest.mark.parametrize("bars, plan", [(JUMP, _bull), (_mirror(JUMP), _bear)])
def test_v2_carries_an_earlier_atr_level_as_giveback(monkeypatch, bars, plan):
    _arm(monkeypatch, "range", k=1.0)
    res = _v2(bars, plan())
    assert (res.exit_index, res.runner_stop_source) == (18, "giveback")


@pytest.mark.parametrize("mode", ["range", "profit_share"])
def test_v2_no_atr_means_no_term(monkeypatch, mode):
    _arm(monkeypatch, mode)
    res = _v2(NAN_ATR_BARS, _bull(), entry=0)
    assert (res.runner_outcome, res.runner_stop_source, res.exit_index) == \
           ("runner_be", "floor", 4)


def test_v2_an_allowance_beyond_the_profit_exits_at_the_floor(monkeypatch):
    _arm(monkeypatch, "profit_share", f=0.95)
    res = _v2(REVERSE, _bull())
    assert (res.runner_stop_source, res.exit_index) == ("floor", 18)
    assert res.legs[1]["exit_price"] == pytest.approx(FLOOR)


def test_the_recomputing_helpers_are_gone():
    assert not hasattr(exit_sim, "_giveback_ratchet")
    assert not hasattr(exit_sim, "_stop_source")
