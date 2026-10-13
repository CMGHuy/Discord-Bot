"""v157 FC4: the v2 exit walk -- gap-through stops and targets in both
directions, stop first, trailing stops effective next bar, and every trade's
r booked once through instrument/costs.py.

Most fixtures use FREE (v2 fills, zero costs) so the expected r is the plain
price arithmetic; the cost tests use resolve("v2"). Entry is at bar 0's
price; the walk starts at bar 1.
"""
import dataclasses

import pytest

from swingbot import config
from swingbot.core.backtesting.instrument.contract import ZERO_COSTS, FillModel, resolve
from swingbot.core.market.strategy_types import COMPRESSION_SHORT
from swingbot.core.planning.exit_sim_v2 import walk_v2
from swingbot.core.planning.plan_engine import PlanStatus, TradePlanV2
from swingbot.core.planning.time_exit import PROXY_BASIS, TIME_EXIT_REASON
from tests.backtesting.test_pullback_dryup_witness import pin_code_defaults
from tests.helpers import make_ohlcv

V2 = resolve("v2")
FREE = dataclasses.replace(V2, cost_model=ZERO_COSTS)
NO_GAP = dataclasses.replace(FREE, fill_model=FillModel("next_open", False, "stop_first"))
ENTRY = (100.0, 100.5, 99.5, 100.0)
FLAT = (100.0, 100.5, 99.5, 100.0)


@pytest.fixture(autouse=True)
def _pinned(monkeypatch):
    pin_code_defaults(monkeypatch)


def _plan(**kw):
    base = dict(
        plan_id="p1", ticker="T", created_at="2024-01-02", source="strategy",
        strategy="Probe", horizon_key="4w", direction="bullish",
        entry_type="market", trigger_price=100.0, entry_price=None, expiry_bars=3,
        stop_loss=95.0, tp1=110.0, tp1_fraction=1.0, tp2=None,
        breakeven_trigger_fraction=0.5, trail_atr_mult=1.0,
        quality_score=0, quality_breakdown=[],
        badge="WEAK", badge_stats={}, status=PlanStatus.PENDING, status_history=[],
    )
    base.update(kw)
    return TradePlanV2(**base)


def _bear(**kw):
    return _plan(direction="bearish", stop_loss=105.0, tp1=90.0, **kw)


def _walk(bars, plan=None, *, instrument=FREE, scale_out=False, hold=10):
    df = make_ohlcv([ENTRY, *bars])
    return walk_v2(df, 0, 100.0, plan or _plan(), hold, instrument, scale_out=scale_out)


def _leg(res, i=0):
    leg = res.legs[i]
    return leg["exit_price"], leg["r"], leg["reason"]


# --- stops ----------------------------------------------------------------

def test_bullish_stop_gapped_through_fills_at_the_open_worse_than_minus_one_r():
    res = _walk([(93.0, 94.0, 92.0, 93.0)])
    assert (res.outcome, res.exit_index, res.r_total) == ("loss", 1, -1.4)
    assert _leg(res) == (93.0, -1.4, "stop")


def test_bullish_stop_touched_intrabar_fills_at_the_stop():
    res = _walk([(98.0, 99.0, 94.0, 96.0)])
    assert (res.outcome, res.r_total) == ("loss", -1.0)
    assert _leg(res) == (95.0, -1.0, "stop")


def test_bearish_stop_gapped_through_fills_at_the_open():
    res = _walk([(107.0, 108.0, 106.0, 107.0)], _bear())
    assert (res.outcome, res.r_total) == ("loss", -1.4)
    assert _leg(res) == (107.0, -1.4, "stop")


def test_without_gap_through_a_gapped_stop_fills_at_the_level():
    res = _walk([(93.0, 94.0, 92.0, 93.0)], instrument=NO_GAP)
    assert _leg(res) == (95.0, -1.0, "stop")


def test_breakeven_stop_gapped_through_is_a_scratch_below_zero():
    # bar 1 reaches the 105 trigger (entry + 0.5 x 10); bar 2 gaps under entry.
    res = _walk([(104.0, 106.0, 103.0, 105.0), (98.0, 99.0, 97.0, 98.0)])
    assert (res.outcome, res.exit_index, res.r_total) == ("scratch", 2, -0.4)
    assert _leg(res) == (98.0, -0.4, "breakeven_stop")


def test_breakeven_move_protects_only_the_bars_after_the_trigger_bar():
    # bar 1 reaches the trigger AND trades under entry: the original stop governs it.
    res = _walk([(101.0, 106.0, 99.0, 104.0), FLAT])
    assert res.outcome == "scratch" and res.exit_index == 2


# --- targets --------------------------------------------------------------

def test_bullish_target_gapped_through_fills_at_the_better_open():
    res = _walk([(112.0, 113.0, 111.0, 112.0)])
    assert (res.outcome, res.r_total) == ("win", 2.4)
    assert _leg(res) == (112.0, 2.4, "tp1")


def test_bearish_target_gapped_through_fills_at_the_better_open():
    res = _walk([(88.0, 89.0, 87.0, 88.0)], _bear())
    assert (res.outcome, res.r_total) == ("win", 2.4)


def test_target_touched_intrabar_fills_at_the_target():
    res = _walk([(105.0, 111.0, 104.0, 109.0)])
    assert _leg(res) == (110.0, 2.0, "tp1")


def test_a_bar_holding_both_stop_and_target_is_a_stop_first_loss():
    res = _walk([(100.0, 111.0, 94.0, 105.0)])
    assert (res.outcome, res.r_total) == ("loss", -1.0)


# --- close-priced exits ---------------------------------------------------

def test_timeout_exits_at_the_last_walked_close():
    res = _walk([FLAT, (100.0, 101.0, 99.0, 100.6), FLAT], hold=2)
    assert (res.outcome, res.exit_index) == ("timeout", 2)
    assert _leg(res) == (100.6, 0.12, "timeout")


def test_acceptance_close_exits_after_stop_and_target():
    res = _walk([(99.0, 100.0, 96.5, 96.8)], _plan(acceptance_close_below=97.0))
    assert (res.outcome, res.exit_index) == ("loss", 1)
    assert _leg(res) == (96.8, -0.64, "acceptance_exit")


def test_stall_exit_runs_only_in_the_scale_out_walk(monkeypatch):
    monkeypatch.setattr(config, "STALL_EXIT_ENABLED", True)
    bars = [(100.0, 101.0, 99.0, 100.0), (99.0, 100.0, 98.0, 99.0), FLAT]
    plan = _plan(tp1_fraction=0.5, stall_exit_day=1)
    res = _walk(bars, plan, scale_out=True)
    assert (res.outcome, res.exit_index) == ("loss", 2)
    assert _leg(res) == (99.0, -0.2, "stall_exit")
    assert _walk(bars, plan, scale_out=False, hold=3).outcome == "timeout"


def test_compression_single_leg_timeout_keeps_the_tenth_session_label():
    plan = _bear(strategy=COMPRESSION_SHORT)
    res = _walk([FLAT, FLAT], plan, hold=2)
    assert res.legs[0]["reason"] == TIME_EXIT_REASON
    assert res.legs[0]["price_basis"] == PROXY_BASIS


# --- runner ---------------------------------------------------------------

TP1_BAR = (105.0, 111.0, 104.0, 110.0)


def test_runner_floor_gapped_through_fills_at_the_open():
    # floor = 100 + 2/3 x 10 = 106.667; bar 2 opens at 104, under it.
    res = _walk([TP1_BAR, (104.0, 105.0, 103.0, 104.0)], _plan(tp1_fraction=0.5),
                scale_out=True)
    assert (res.outcome, res.runner_outcome, res.exit_index) == ("win", "runner_be", 2)
    assert res.legs[0] == {"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1"}
    assert _leg(res, 1) == (104.0, 0.8, "runner_be")
    assert res.r_total == 1.4


def test_tp2_gapped_through_fills_at_the_better_open():
    res = _walk([TP1_BAR, (118.0, 119.0, 117.0, 118.0)], _plan(tp1_fraction=0.5, tp2=115.0),
                scale_out=True)
    assert (res.runner_outcome, res.r_total) == ("runner_tp2", 2.8)
    assert _leg(res, 1) == (118.0, 3.6, "runner_tp2")


def test_trailing_stop_from_a_close_takes_effect_on_the_next_bar():
    # Short tape: ATR falls back to 2% of entry = 2.0; trail mult 1.0.
    # Bar 2 closes 119 -> stop 117, but bar 2's own 107 low is checked against
    # the floor (106.667) only. Bar 3 opens 118 and trades to 116: out at 117.
    res = _walk([TP1_BAR, (110.0, 120.0, 107.0, 119.0), (118.0, 118.5, 116.0, 117.0)],
                _plan(tp1_fraction=0.5), scale_out=True)
    assert (res.runner_outcome, res.exit_index) == ("runner_trail", 3)
    assert _leg(res, 1) == (117.0, 3.4, "runner_trail")


def test_single_leg_walk_takes_the_whole_position_at_tp1():
    res = _walk([TP1_BAR], _plan(tp1_fraction=0.5), scale_out=False)
    assert (res.outcome, res.runner_outcome, len(res.legs)) == ("win", None, 1)


# --- costs, booked once ---------------------------------------------------

def test_v2_costs_book_a_stop_loss_net_of_both_slippages():
    res = _walk([(98.0, 99.0, 94.0, 96.0)], instrument=V2)
    # entry 100.05 (5 bps), stop exit 94.905 (10 bps), risk 5.05
    assert res.r_total == round((94.905 - 100.05) / 5.05, 3) == -1.019
    assert res.entry_price == 100.0 and res.legs[0]["exit_price"] == 95.0


def test_v2_costs_book_each_runner_leg_at_its_own_rate_and_round_once():
    res = _walk([TP1_BAR, (104.0, 105.0, 103.0, 104.0)], _plan(tp1_fraction=0.5),
                instrument=V2, scale_out=True)
    r1 = (110.0 * 0.9995 - 100.05) / 5.05
    r2 = (104.0 * 0.999 - 100.05) / 5.05
    assert [leg["r"] for leg in res.legs] == [round(r1, 3), round(r2, 3)]
    assert res.r_total == round(0.5 * r1 + 0.5 * r2, 3)


def test_outcome_label_follows_the_event_not_the_net_r():
    # A TP1 touch a hair above entry nets below zero after costs: still a win.
    res = _walk([(100.0, 100.1, 99.9, 100.0)], _plan(tp1=100.05), instrument=V2)
    assert res.outcome == "win" and res.r_total < 0


def test_zero_risk_entry_is_no_trade():
    res = _walk([FLAT], _plan(stop_loss=100.0))
    assert (res.outcome, res.legs, res.r_total) == ("no_trade", [], 0.0)


def test_booked_legs_carry_no_kind():
    res = _walk([(98.0, 99.0, 94.0, 96.0)])
    assert set(res.legs[0]) == {"fraction", "exit_price", "r", "reason"}
