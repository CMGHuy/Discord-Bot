"""v157 FC5: v2 entries behind the simulate_exit seam -- next-open market
fills and their gap cancel, limit and stop-entry fills on fills.py, the
fill-bar stop check for every v2 entry, and v1 untouched by the seam."""
import dataclasses

import pytest

from swingbot.core.backtesting.instrument.contract import (V1_FILLS, ZERO_COSTS,
                                                           InstrumentSpec, resolve)
from swingbot.core.market.strategy_types import COMPRESSION_SHORT
from swingbot.core.planning import exit_sim_v2
from swingbot.core.planning.exit_sim import simulate_exit
from swingbot.core.planning.exit_sim_v2 import ENTRY_GAP_SCRATCH, GAP_CANCEL
from swingbot.core.planning.plan_engine import PlanStatus, TradePlanV2
from swingbot.core.planning.stop_scope import plan_stop_ceiling
from tests.backtesting.test_pullback_dryup_witness import pin_code_defaults
from tests.helpers import make_ohlcv

V2 = resolve("v2")
FREE = dataclasses.replace(V2, cost_model=ZERO_COSTS)
SIGNAL = (100.0, 100.5, 99.5, 100.0)
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


def _run(bars, plan, instrument=FREE, **kw):
    return simulate_exit(make_ohlcv([SIGNAL, *bars]), 0, plan, instrument=instrument, **kw)


# --- market: next open, gap cancel, entry-bar stop ---------------------------

def test_market_entry_fills_at_the_next_open():
    res = _run([(100.5, 101.0, 100.0, 100.8), FLAT], _plan(), max_holding_days=1)
    assert (res.entry_index, res.entry_price) == (1, 100.5)
    assert (res.outcome, res.exit_index) == ("timeout", 2)


@pytest.mark.parametrize("gap_open", [95.0, 94.0])
def test_market_open_at_or_beyond_the_stop_cancels_uncounted(gap_open):
    res = _run([(gap_open, 96.0, 93.0, 95.5), FLAT], _plan())
    assert (res.outcome, res.cancel_reason, res.legs) == ("not_triggered", GAP_CANCEL, [])


def test_bearish_market_gap_up_through_the_stop_cancels():
    plan = _plan(direction="bearish", stop_loss=105.0, tp1=90.0)
    res = _run([(106.0, 107.0, 105.5, 106.0)], plan)
    assert (res.outcome, res.cancel_reason) == ("not_triggered", GAP_CANCEL)


def test_market_signal_on_the_last_bar_is_not_triggered_without_a_reason():
    res = simulate_exit(make_ohlcv([SIGNAL]), 0, _plan(), instrument=FREE)
    assert (res.outcome, res.cancel_reason) == ("not_triggered", None)


def test_market_entry_bar_checks_the_stop_first():
    res = _run([(100.0, 111.0, 94.0, 100.0)], _plan())
    assert (res.outcome, res.entry_index, res.exit_index) == ("loss", 1, 1)
    assert res.legs[0]["exit_price"] == 95.0 and res.r_total == -1.0


def test_market_entry_bar_ignores_the_target():
    # bar 1 trades through the 110 target after the 100 open; the walk starts at bar 2.
    res = _run([(100.0, 111.0, 99.0, 110.0), (112.0, 112.5, 111.0, 112.0)], _plan())
    assert (res.outcome, res.exit_index) == ("win", 2)
    assert res.legs[0]["exit_price"] == 112.0           # gapped through: the open


def test_v2_costs_net_the_market_trade():
    res = _run([(100.0, 100.5, 99.5, 100.0), (98.0, 99.0, 94.0, 96.0)], _plan(), V2)
    assert res.entry_price == 100.0
    assert res.r_total == round((95.0 * 0.999 - 100.05) / 5.05, 3)


# --- limit -------------------------------------------------------------------

def _limit(**kw):
    return _plan(entry_type="limit", trigger_price=100.0, stop_loss=98.0, tp1=104.0, **kw)


def test_limit_opening_through_the_limit_fills_at_the_better_open():
    res = _run([(99.5, 100.2, 99.0, 99.8), FLAT], _limit(), max_holding_days=1)
    assert (res.entry_index, res.entry_price) == (1, 99.5)


def test_limit_filled_at_or_beyond_the_stop_is_a_0r_entry_gap_scratch():
    res = _run([(97.5, 98.0, 97.0, 97.8)], _limit(), V2)
    assert (res.outcome, res.entry_price, res.r_total) == ("scratch", 97.5, 0.0)
    assert res.legs == [{"fraction": 1.0, "exit_price": 97.5, "r": 0.0,
                         "reason": ENTRY_GAP_SCRATCH}]


def test_fill_exactly_at_the_stop_never_reaches_walk_v2(monkeypatch):
    # FC4 review (a): costs.book refuses a non-positive signed risk, so a fill
    # at the stop must be scratched on the fill bar, never walked.
    def _boom(*a, **k):
        raise AssertionError("walk_v2 reached with an entry at the stop")
    monkeypatch.setattr(exit_sim_v2, "walk_v2", _boom)
    res = _run([(98.0, 98.5, 97.5, 98.2)], _limit(), V2)
    assert (res.outcome, res.entry_price, res.r_total) == ("scratch", 98.0, 0.0)
    assert res.legs[0]["reason"] == ENTRY_GAP_SCRATCH


def test_limit_fill_bar_reaching_the_stop_is_a_loss_at_the_stop():
    res = _run([(99.8, 100.0, 97.9, 98.5)], _limit())
    assert (res.outcome, res.entry_index, res.exit_index) == ("loss", 1, 1)
    assert res.legs[0]["exit_price"] == 98.0
    assert res.r_total == round((98.0 - 99.8) / 1.8, 3)


def test_cancellable_limit_keeps_its_unfilled_reasons():
    res = _run([(101.0, 106.0, 100.5, 105.0)], _limit(limit_cancel_level=105.0))
    assert (res.outcome, res.cancel_reason) == ("not_triggered", "cancelled")
    above = (101.0, 101.5, 100.5, 101.0)                 # never reaches the 100 limit
    res = _run([above] * 4, _limit(limit_cancel_level=105.0))
    assert (res.outcome, res.cancel_reason) == ("not_triggered", "expired")


# --- stop entry --------------------------------------------------------------

def _breakout(**kw):
    return _plan(entry_type="stop_entry", trigger_price=105.0, stop_loss=100.0, tp1=110.0,
                 **kw)


def test_stop_entry_opening_beyond_the_trigger_fills_at_the_open():
    res = _run([(106.0, 107.0, 105.5, 106.5), FLAT], _breakout(), max_holding_days=1)
    assert (res.entry_index, res.entry_price) == (1, 106.0)


def test_every_v2_stop_entry_checks_the_stop_on_its_fill_bar():
    # Controller amendment: fills at 105, trades down to 99 on the same bar.
    bars = [(104.0, 106.0, 99.0, 101.0), (101.0, 101.5, 100.5, 101.0)]
    res = _run(bars, _breakout())
    assert (res.outcome, res.entry_index, res.exit_index) == ("loss", 1, 1)
    assert res.legs[0]["exit_price"] == 100.0 and res.r_total == -1.0
    v1 = simulate_exit(make_ohlcv([SIGNAL, *bars]), 0, _breakout())
    assert v1.exit_index != 1                              # v1 never checks the fill bar


def test_stop_entry_fill_bar_ignores_the_target():
    res = _run([(104.0, 116.0, 104.0, 115.0), (115.0, 115.5, 114.0, 115.0)], _breakout())
    assert (res.outcome, res.exit_index) == ("win", 2)
    assert res.legs[0]["exit_price"] == 115.0


def test_stop_entry_expiry_and_invalidation_stay_reason_less():
    assert _run([FLAT] * 5, _breakout()).cancel_reason is None
    res = _run([(100.0, 100.5, 99.0, 99.5)], _breakout())
    assert (res.outcome, res.cancel_reason) == ("not_triggered", None)


def _compression(**kw):
    base = dict(strategy=COMPRESSION_SHORT, direction="bearish", entry_type="stop_entry",
                trigger_price=100.0, stop_loss=101.0, tp1=95.0, tp1_fraction=1.0,
                expiry_bars=1, horizon_key="2w")
    base.update(kw)
    return _plan(**base)


def test_compression_gap_fill_beyond_the_risk_cap_is_cancelled():
    plan = _compression()
    gap_open = plan.stop_loss / (1 + plan_stop_ceiling(plan) / 100.0) - 1.0
    res = _run([(gap_open, gap_open + 0.2, gap_open - 0.5, gap_open)], plan)
    assert (res.outcome, res.cancel_reason) == ("not_triggered", "risk_cap")


def test_compression_untouched_session_keeps_its_strict_expiry():
    res = _run([(100.5, 100.9, 100.2, 100.6), FLAT], _compression())
    assert (res.outcome, res.cancel_reason) == ("not_triggered", "expired")


# --- the seam ----------------------------------------------------------------

@pytest.mark.parametrize("plan", [_plan(), _limit(), _breakout()])
def test_v1_spec_and_no_spec_run_the_same_v1_code(plan):
    df = make_ohlcv([SIGNAL, (100.5, 106.0, 99.0, 104.0), (104.0, 111.0, 103.0, 110.0), FLAT])
    assert simulate_exit(df, 0, plan, scale_out=True, instrument=resolve("v1")) == \
        simulate_exit(df, 0, plan, scale_out=True)


@pytest.mark.parametrize("plan", [_plan(), _limit(), _breakout()])
def test_a_v2_spec_without_next_open_fills_is_refused(plan):
    # FC4 review (b): every entry type checks the fill model up front.
    odd = InstrumentSpec("v2", V1_FILLS, ZERO_COSTS)
    with pytest.raises(ValueError, match="next_open"):
        simulate_exit(make_ohlcv([SIGNAL, FLAT]), 0, plan, instrument=odd)


def test_hold_cap_is_resolved_as_in_v1():
    res = _run([FLAT] * 6, _plan(hold_cap_bars=2))
    assert (res.outcome, res.entry_index, res.exit_index) == ("timeout", 1, 3)
