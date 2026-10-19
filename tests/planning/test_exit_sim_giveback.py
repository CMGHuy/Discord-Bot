"""v176 V176-5: the runner give-back in both exit simulators.

Bullish frame: the market entry fills at bar 0's close (100); stop 95,
TP1 110 (tp1_fraction 0.5), so the runner floor is 106.6667.
trail_atr_mult=50 parks the chandelier far below the floor, so only the
floor and the give-back can bind.
  bar 1 (100, 111, 99.5, 110.5)   TP1 touched; extreme close 110.5
  bar 2 (110.5, 121, 110, 120)    checked against the floor (low 110 passes);
                                  its close 120 sets give-back 114.0 for bar 3
  bar 3 (120, 120.5, 113, 113.5)  low 113 <= 114: runner out at 114 (give-back)
  bar 4 (113.5, 114, 106, 106.5)  reached only with the give-back off:
                                  low 106 <= floor -> runner_be
Bar 2's own low (110) is below the 114 its close sets: an intrabar read
would close the runner on bar 2, so exit_index == 3 is the no-lookahead check.
The bearish frame mirrors it around 100 (floor 93.3333, give-back 84.0).
"""
import dataclasses
import hashlib
import json

import pytest

from swingbot import config
from swingbot.core.backtesting.instrument.contract import ZERO_COSTS, resolve
from swingbot.core.planning import exit_sim
from swingbot.core.planning.exit_sim_v2 import walk_v2
from swingbot.core.planning.plan_engine import simulate_exit
from tests.helpers import make_ohlcv
from tests.planning.test_exit_sim_scaleout_witness import FIXTURE, witness_rows
from tests.planning.test_exit_sim_single import _plan

FLOOR = 100.0 + (2.0 / 3.0) * 10.0
BEAR_FLOOR = 100.0 - (2.0 / 3.0) * 10.0
BULL_BARS = [100.0, (100.0, 111.0, 99.5, 110.5), (110.5, 121.0, 110.0, 120.0),
             (120.0, 120.5, 113.0, 113.5), (113.5, 114.0, 106.0, 106.5)]
BEAR_BARS = [100.0, (100.0, 100.5, 89.0, 89.5), (89.5, 90.0, 79.0, 80.0),
             (80.0, 87.0, 79.5, 86.5), (86.5, 94.0, 86.0, 93.5)]
FREE = dataclasses.replace(resolve("v2"), cost_model=ZERO_COSTS)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """Give-back on at 5%, every other runner rule that could bind switched off."""
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_ENABLED", True)
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_PCT", 5.0)
    monkeypatch.setattr(config, "RUNNER_STRUCTURE_EXIT", "off")
    monkeypatch.setattr(config, "ADAPTIVE_RUNNER_TRAIL_ENABLED", False)
    monkeypatch.setattr(config, "STALL_EXIT_ENABLED", False)
    monkeypatch.setattr(exit_sim, "GIVEBACK_EXTREME_BASIS", "close")


def _bull(**kw):
    base = dict(direction="bullish", stop_loss=95.0, tp1=110.0, tp2=None, trail_atr_mult=50.0)
    base.update(kw)
    return _plan(**base)


def _bear(**kw):
    base = dict(direction="bearish", stop_loss=105.0, tp1=90.0, tp2=None, trail_atr_mult=50.0)
    base.update(kw)
    return _plan(**base)


def _v1(bars, plan):
    return simulate_exit(make_ohlcv(bars), 0, plan, scale_out=True)


def _v2(bars, plan):
    return walk_v2(make_ohlcv(bars), 0, 100.0, plan, 10, FREE, scale_out=True)


# --- v1 walk ---------------------------------------------------------------

def test_flag_on_bullish_runner_exits_at_the_giveback_level_the_next_bar():
    res = _v1(BULL_BARS, _bull())
    assert res.outcome == "win"
    assert res.runner_outcome == "runner_trail"            # no new reason string
    assert res.runner_stop_source == "giveback"
    assert res.exit_index == 3                             # bar 2 sets it, bar 3 checks it
    assert res.legs[1]["exit_price"] == exit_sim.giveback_stop(120.0, 5.0, "bullish")
    assert res.legs[1]["exit_price"] == pytest.approx(114.0)
    assert res.legs[1]["reason"] == "runner_trail"
    assert res.legs[1]["r"] == pytest.approx(2.8)
    assert res.r_total == pytest.approx(2.4)
    assert set(res.legs[1]) == {"fraction", "exit_price", "r", "reason"}   # legs untouched


def test_flag_on_bearish_runner_exits_at_the_giveback_level_the_next_bar():
    res = _v1(BEAR_BARS, _bear())
    assert res.runner_outcome == "runner_trail"
    assert res.runner_stop_source == "giveback"
    assert res.exit_index == 3
    assert res.legs[1]["exit_price"] == exit_sim.giveback_stop(80.0, 5.0, "bearish")
    assert res.legs[1]["exit_price"] == pytest.approx(84.0)
    assert res.legs[1]["r"] == pytest.approx(3.2)
    assert res.r_total == pytest.approx(2.6)


@pytest.mark.parametrize("bars,plan,floor", [(BULL_BARS, _bull, FLOOR),
                                              (BEAR_BARS, _bear, BEAR_FLOOR)])
def test_flag_off_runner_rides_to_the_floor(monkeypatch, bars, plan, floor):
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_ENABLED", False)
    res = _v1(bars, plan())
    assert res.runner_outcome == "runner_be"
    assert res.runner_stop_source == "floor"
    assert res.exit_index == 4
    assert res.legs[1]["exit_price"] == pytest.approx(floor)


def test_a_giveback_looser_than_the_floor_never_moves_the_stop(monkeypatch):
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_PCT", 20.0)    # 120 x 0.80 = 96 < floor
    res = _v1(BULL_BARS, _bull())
    assert res.runner_outcome == "runner_be"
    assert res.runner_stop_source == "floor"
    assert res.exit_index == 4


def test_a_chandelier_tighter_than_the_giveback_is_tagged_trail():
    # trail_atr_mult=0.01 puts the chandelier a hair under the 120 close,
    # far above the 114 give-back: the trail binds, the give-back never does.
    res = _v1(BULL_BARS, _bull(trail_atr_mult=0.01))
    assert res.runner_outcome == "runner_trail"
    assert res.runner_stop_source == "trail"
    assert res.exit_index == 3
    assert res.legs[1]["exit_price"] > 114.0


@pytest.mark.parametrize("bars,plan,extreme,direction", [
    (BULL_BARS, _bull, 121.0, "bullish"),       # bar 2's high
    (BEAR_BARS, _bear, 79.0, "bearish"),        # bar 2's low
])
def test_high_low_basis_tracks_the_bar_extreme_for_the_next_bar(monkeypatch, bars, plan,
                                                                 extreme, direction):
    monkeypatch.setattr(exit_sim, "GIVEBACK_EXTREME_BASIS", "high_low")
    res = _v1(bars, plan())
    assert res.runner_stop_source == "giveback"
    assert res.exit_index == 3
    assert res.legs[1]["exit_price"] == exit_sim.giveback_stop(extreme, 5.0, direction)


def test_an_unknown_basis_is_rejected(monkeypatch):
    monkeypatch.setattr(exit_sim, "GIVEBACK_EXTREME_BASIS", "open")
    with pytest.raises(ValueError, match="GIVEBACK_EXTREME_BASIS"):
        _v1(BULL_BARS, _bull())


def test_non_stop_runner_exits_and_single_legs_carry_no_stop_source():
    tp2 = _v1(BULL_BARS, _bull(tp2=115.0))                 # bar 2's high 121 reaches TP2
    assert tp2.runner_outcome == "runner_tp2"
    assert tp2.runner_stop_source is None
    timeout = _v1(BULL_BARS[:3], _bull())                  # data ends on bar 2
    assert timeout.runner_outcome == "runner_timeout"
    assert timeout.runner_stop_source is None
    single = simulate_exit(make_ohlcv(BULL_BARS), 0, _bull(), scale_out=False)
    assert single.runner_outcome is None
    assert single.runner_stop_source is None


def test_flag_off_reproduces_the_frozen_scale_out_witness(monkeypatch):
    """Spec § Testing: flag off gives an identical trade list on an existing
    fixture. The new field is dropped before hashing (V176-6 moves that drop
    into witness_rows itself; pop(..., None) keeps this test valid after it)."""
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_ENABLED", False)
    rows = witness_rows()
    for row in rows:
        assert row[4].pop("runner_stop_source", None) != "giveback"
    digest = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
    assert digest == FIXTURE.read_text(encoding="utf-8").strip()


# --- v2 walk ---------------------------------------------------------------

@pytest.mark.parametrize("bars,plan,exit_price", [
    (BULL_BARS, _bull, 114.0),
    (BEAR_BARS, _bear, 84.0),
])
def test_v2_flag_on_runner_exits_at_the_giveback_level(bars, plan, exit_price):
    res = _v2(bars, plan())
    assert res.outcome == "win"
    assert res.runner_outcome == "runner_trail"
    assert res.runner_stop_source == "giveback"
    assert res.exit_index == 3
    assert res.legs[1]["exit_price"] == pytest.approx(exit_price)
    assert res.legs[1]["reason"] == "runner_trail"


def test_v2_flag_off_runner_rides_to_the_floor(monkeypatch):
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_ENABLED", False)
    res = _v2(BULL_BARS, _bull())
    assert res.runner_outcome == "runner_be"
    assert res.runner_stop_source == "floor"
    assert res.exit_index == 4
    assert res.legs[1]["exit_price"] == pytest.approx(FLOOR)


def test_v1_and_v2_agree_on_the_giveback_exit():
    v1, v2 = _v1(BULL_BARS, _bull()), _v2(BULL_BARS, _bull())
    assert (v1.exit_index, v1.runner_outcome, v1.runner_stop_source) == \
           (v2.exit_index, v2.runner_outcome, v2.runner_stop_source)
    assert v1.legs[1]["exit_price"] == pytest.approx(v2.legs[1]["exit_price"])
