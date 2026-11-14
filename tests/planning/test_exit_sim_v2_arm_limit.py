"""v212 arm limit in the v2 replay (spec rule 6, G2 tie rules): bars t+1..t+3
only, trade-through fills at L, an open through L fills at the open, an open
through the stop fills and stops at the open (0R less frictions on
the planned risk; the from-L loss is a sensitivity field), TP1
cancels inclusively, a bar reaching both cancels; v113/v131 limits unchanged."""
import dataclasses

import pytest

from swingbot.core.backtesting.instrument.contract import ZERO_COSTS, resolve
from swingbot.core.planning import exit_sim_v2
from swingbot.core.planning.exit_sim import ExitResult
from swingbot.core.planning.exit_sim_v2 import (ENTRY_GAP_SCRATCH, FILLED_STOPPED_GAP,
                                                LIMIT_EXPIRED, LIMIT_TP1_CANCEL,
                                                simulate_exit_v2)
from swingbot.core.planning.plan_types import PlanStatus, TradePlanV2
from tests.backtesting.test_pullback_dryup_witness import pin_code_defaults
from tests.helpers import make_ohlcv

FREE = dataclasses.replace(resolve("v2"), cost_model=ZERO_COSTS)
SIGNAL = (100.0, 100.5, 99.5, 100.0)
QUIET = (100.0, 100.5, 99.5, 100.0)                 # never reaches 98.49 or 104
THROUGH = (99.5, 100.0, 98.4, 99.0)                 # low trades a tick under 98.5
TO_TP1 = (100.0, 104.5, 99.5, 104.0)
LONG = dict(direction="bullish", trigger_price=98.5, stop_loss=96.75, tp1=104.0)
SHORT = dict(direction="bearish", trigger_price=101.5, stop_loss=103.26, tp1=96.0)


@pytest.fixture(autouse=True)
def _pinned(monkeypatch):
    pin_code_defaults(monkeypatch)


def _plan(levels=LONG, **kw):
    base = dict(plan_id="p1", ticker="XYZ", created_at="2024-01-02", source="confluence",
                strategy="S/R Confluence", horizon_key="4w", entry_type="limit",
                entry_price=None, expiry_bars=3, tp1_fraction=1.0, tp2=None,
                breakeven_trigger_fraction=0.5, trail_atr_mult=2.5, quality_score=0,
                quality_breakdown=[], badge="WEAK", badge_stats={}, status=PlanStatus.PENDING,
                status_history=[], limit_cancel_level=levels["tp1"], limit_strict_fill=True,
                limit_entry_f=0.5, **levels)
    base.update(kw)
    return TradePlanV2(**base)


def _run(bars, plan=None, instrument=FREE, **kw):
    return simulate_exit_v2(make_ohlcv([SIGNAL, *bars]), 0, plan or _plan(), instrument, **kw)


def test_trade_through_fills_at_the_limit_then_walks():
    res = _run([QUIET, THROUGH, TO_TP1])
    assert (res.entry_index, res.entry_price, res.outcome) == (2, 98.5, "win")
    assert res.r_total == pytest.approx((104.0 - 98.5) / 1.75, abs=1e-3)   # costs.book rounds to 3 dp
    assert res.exit_reason is None


def test_a_fill_on_the_third_bar_counts_and_the_fourth_does_not():
    assert _run([QUIET, QUIET, THROUGH, TO_TP1]).entry_index == 3
    res = _run([QUIET, QUIET, QUIET, THROUGH, TO_TP1])
    assert (res.outcome, res.cancel_reason, res.exit_reason) == ("not_triggered", "expired", LIMIT_EXPIRED)
    assert (res.entry_index, res.legs) == (None, [])


def test_signal_on_the_last_bar_expires():
    res = simulate_exit_v2(make_ohlcv([SIGNAL]), 0, _plan(), FREE)
    assert res.exit_reason == LIMIT_EXPIRED


@pytest.mark.parametrize("bar", [(100.0, 104.0, 99.5, 103.0),      # TP1 printed exactly
                                 (100.0, 105.0, 98.0, 104.0)])     # L and TP1 on one bar
def test_tp1_before_a_fill_cancels_inclusively(bar):
    res = _run([bar, THROUGH])
    assert (res.outcome, res.cancel_reason, res.exit_reason) == ("not_triggered", "cancelled", LIMIT_TP1_CANCEL)


@pytest.mark.parametrize("levels,open_,from_l", [(LONG, 96.0, (96.0 - 98.5) / 1.75),
                                                 (SHORT, 104.0, (101.5 - 104.0) / 1.76)])
def test_gap_through_the_stop_fills_and_stops_at_the_open(levels, open_, from_l):
    bar = (open_, open_ + 0.5, open_ - 0.5, open_)
    res = _run([bar], _plan(levels))
    assert (res.outcome, res.entry_index, res.exit_index) == ("loss", 1, 1)
    assert res.entry_price == open_                       # a resting limit fills at the open
    assert res.legs[0]["exit_price"] == open_ and res.legs[0]["reason"] == FILLED_STOPPED_GAP
    assert res.r_total == 0.0                             # 0R before frictions, never a -1R+ loss
    assert res.exit_reason == FILLED_STOPPED_GAP
    assert res.gap_stop_r_from_limit == pytest.approx(from_l, abs=1e-3)   # sensitivity only



def test_an_open_through_the_stop_beats_a_tp1_reach_on_the_same_bar():
    res = _run([(96.0, 104.5, 95.5, 104.0)])        # opens through 96.75, later prints TP1
    assert (res.outcome, res.exit_reason, res.entry_index) == ("loss", FILLED_STOPPED_GAP, 1)

def test_gap_stop_costs_are_scaled_by_the_planned_risk():
    res = _run([(96.0, 96.5, 95.5, 96.0)], instrument=resolve("v2"))
    # 5 bps in, 10 bps out on the stop, over |L - stop| = 1.75 (not |open - stop|)
    assert res.r_total == pytest.approx(-(96.0 * 0.0015) / 1.75, abs=1e-3)
    assert -1.0 < res.r_total < 0.0
    assert res.gap_stop_r_from_limit < -1.0


def test_sensitivity_field_is_unset_on_every_other_row():
    assert _run([QUIET, THROUGH, TO_TP1]).gap_stop_r_from_limit is None
    assert _run([QUIET, QUIET, QUIET]).gap_stop_r_from_limit is None


def test_an_open_through_the_limit_fills_at_the_open():
    res = _run([(98.0, 98.4, 97.5, 98.2), TO_TP1])
    assert (res.entry_index, res.entry_price, res.outcome) == (1, 98.0, "win")


def test_a_fill_bar_that_reaches_the_stop_is_a_one_r_loss_at_the_stop():
    res = _run([(98.0, 98.4, 96.5, 97.0)])
    assert (res.outcome, res.entry_price, res.legs[0]["exit_price"]) == ("loss", 98.0, 96.75)
    assert res.r_total == pytest.approx(-1.0)


def test_a_bare_touch_fills_only_with_touch_fill():
    touch = (99.5, 100.0, 98.5, 99.0)
    assert _run([touch, QUIET, QUIET, TO_TP1]).exit_reason == LIMIT_EXPIRED
    res = _run([touch, TO_TP1], touch_fill=True)
    assert (res.entry_index, res.entry_price) == (1, 98.5)


def _v131(**kw):
    return _plan(limit_entry_f=None, **kw)                     # out of scope: today's path


def test_out_of_scope_limit_keeps_the_0r_gap_scratch():
    res = _run([(96.0, 96.5, 95.5, 96.0)], _v131())
    assert (res.outcome, res.r_total, res.legs[0]["reason"]) == ("scratch", 0.0, ENTRY_GAP_SCRATCH)
    assert res.exit_reason is None


def test_out_of_scope_limit_fills_on_a_bar_that_also_reaches_tp1():
    res = _run([(100.0, 105.0, 98.0, 104.0), TO_TP1], _v131())
    assert res.outcome != "not_triggered" and res.entry_index == 1


@pytest.mark.parametrize("bars", [[(99.5, 100.0, 98.5, 99.0), TO_TP1], [QUIET, THROUGH, TO_TP1]])
def test_touch_fill_is_ignored_by_out_of_scope_plans(bars):
    assert _run(bars, _v131(), touch_fill=True) == _run(bars, _v131())


def test_exit_reason_is_not_a_dataclass_field():
    res = _run([QUIET, QUIET, QUIET])
    assert {"exit_reason", "gap_stop_r_from_limit"}.isdisjoint(dataclasses.asdict(res))
    assert ExitResult.exit_reason is None and ExitResult.gap_stop_r_from_limit is None
    assert exit_sim_v2._ENTRIES["limit"] is exit_sim_v2._limit_entry_v2   # dispatch table untouched
