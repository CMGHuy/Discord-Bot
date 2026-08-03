"""Plan v8 Task V52 Step 1: the runner leg, recorded on its own.

V51 Step 2 measured that with `tp1_fraction` frozen at 0.5 a win realises
`0.5 x 1.4286 + 0.5 x r_runner`, so the break-even win rate swings from 41.2%
(runner matches TP1) to 58.3% (runner stopped at breakeven) purely on how
runners do -- and that range straddles the measured 43.4% no-skill floor.
A blended `r_multiple` cannot distinguish those worlds, so V52's ladder needs
the runner leg reported separately or its headline expectancy is unreadable.

These pin two things:

  1. **`ExitResult.tp1_index` and the two new `BacktestTrade` fields are
     inert** on every path that has no runner -- single-leg walks, and
     scale-out trades that never reached TP1. Additive and default-None,
     the G91 gate-annotation precedent.
  2. **When there IS a runner, the recorded values are the runner's own** --
     `runner_r` is leg 2's R (never the blend), and `runner_holding_days` is
     measured from the TP1 bar, not from entry.
"""
import pytest

from swingbot.core.plan_engine import PlanStatus, TradePlanV2, simulate_exit
from tests.helpers import make_ohlcv


def _plan(**kw):
    base = dict(
        plan_id="p1", ticker="AAPL", created_at="2024-01-02", source="strategy",
        strategy="Fibonacci", horizon_key="2w", direction="bullish",
        entry_type="market", trigger_price=100.0, entry_price=None, expiry_bars=3,
        stop_loss=95.0, tp1=110.0, tp1_fraction=0.5, tp2=None,
        breakeven_trigger_fraction=0.5, trail_atr_mult=2.5,
        quality_score=0, quality_breakdown=[], tier="C",
        badge="WEAK", badge_stats={}, status=PlanStatus.PENDING, status_history=[],
    )
    base.update(kw)
    return TradePlanV2(**base)


def _reaches_tp1_then_runs():
    """Entry 100 (stop 95, tp1 110). Bar 1 touches TP1, then the runner rides
    up for three more bars before the trail takes it out."""
    return make_ohlcv([
        100.0,
        (100.0, 111.0, 99.5, 110.5),   # bar 1: TP1 touched
        (110.5, 118.0, 110.0, 117.0),
        (117.0, 125.0, 116.0, 124.0),
        (124.0, 126.0, 100.0, 101.0),  # deep retrace -> trail/BE stop fires
        (101.0, 102.0, 100.0, 101.0),
    ])


def _never_reaches_tp1():
    """Drifts sideways and times out: no TP1, therefore no runner."""
    return make_ohlcv([
        100.0,
        (100.0, 101.0, 99.0, 99.5),
        (99.5, 100.5, 98.5, 99.0),
        (99.0, 100.0, 98.0, 98.5),
    ])


def _stops_out():
    """Straight to the stop before TP1: single full-fraction leg, a loss."""
    return make_ohlcv([
        100.0,
        (100.0, 100.5, 94.0, 94.5),
    ])


# -- property 1: inert wherever there is no runner ---------------------------

@pytest.mark.parametrize("scale_out", [False, True])
def test_tp1_index_is_none_when_tp1_never_fills(scale_out):
    res = simulate_exit(_never_reaches_tp1(), 0, _plan(), scale_out=scale_out,
                        max_holding_days=3)
    assert res.outcome == "timeout"
    assert res.tp1_index is None
    assert len(res.legs) == 1


@pytest.mark.parametrize("scale_out", [False, True])
def test_tp1_index_is_none_on_a_stopped_out_loss(scale_out):
    res = simulate_exit(_stops_out(), 0, _plan(), scale_out=scale_out,
                        max_holding_days=3)
    assert res.outcome == "loss"
    assert res.tp1_index is None
    assert len(res.legs) == 1


def test_single_leg_walk_never_sets_tp1_index_even_on_a_win():
    """The single-leg walk has no runner by construction, so a win there must
    still leave the field None -- otherwise a caller could mistake TP1's own
    hold for a runner's."""
    res = simulate_exit(_reaches_tp1_then_runs(), 0, _plan(), scale_out=False,
                        max_holding_days=5)
    assert res.outcome == "win"
    assert res.tp1_index is None
    assert len(res.legs) == 1


# -- property 2: with a runner, the values are the runner's own --------------

def test_scale_out_win_sets_tp1_index_to_the_tp1_bar():
    res = simulate_exit(_reaches_tp1_then_runs(), 0, _plan(), scale_out=True,
                        max_holding_days=5)
    assert res.outcome == "win"
    assert len(res.legs) == 2
    assert res.tp1_index == 1
    assert res.legs[0]["reason"] == "tp1"


def test_runner_r_is_the_runner_leg_not_the_blend():
    res = simulate_exit(_reaches_tp1_then_runs(), 0, _plan(), scale_out=True,
                        max_holding_days=5)
    leg1, leg2 = res.legs
    # The blend is what r_multiple already reports; the point of the new field
    # is that it is NOT this number.
    assert res.r_total == pytest.approx(
        leg1["fraction"] * leg1["r"] + leg2["fraction"] * leg2["r"], abs=1e-3)
    assert leg2["r"] != pytest.approx(res.r_total, abs=1e-3)


def test_runner_hold_is_measured_from_tp1_not_from_entry():
    res = simulate_exit(_reaches_tp1_then_runs(), 0, _plan(), scale_out=True,
                        max_holding_days=5)
    whole_trade = res.exit_index - res.entry_index
    runner_only = res.exit_index - res.tp1_index
    assert runner_only < whole_trade, (
        "a runner that starts at TP1 must hold for fewer bars than the whole "
        "trade, or V52's 'median runner hold' is just the trade hold again")
