"""V192-7: with a stored reclaim level X, an open at or beyond X toward the stop makes
the plan rest at E for session t+1: one tick through E fills at E +/- one adverse tick
and walks from that bar; no reclaim cancels gap_no_reclaim; a reclaim bar that also
reaches the stop is -1R. Bullish and bearish twins, and a sub-$1 plan."""
import pytest

from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.planning import exit_sim
from swingbot.core.planning import gap_reclaim as gr
from swingbot.core.planning import market_next_open as mno
from swingbot.core.planning.exit_sim import simulate_exit
from swingbot.core.planning.plan_types import PlanStatus
from tests.helpers import make_ohlcv
from tests.planning.test_plan_engine_model import _plan

SIGNAL = 30
J = SIGNAL + 1
FLAT = (100.0, 100.5, 99.5, 100.0)


def _bars(overrides=None, n=120, flat=FLAT):
    rows = [flat] * n
    for i, row in (overrides or {}).items():
        rows[i] = row
    return make_ohlcv(rows, start="2024-01-02")


def _bull(**kw):
    """E 100, stop 98.5, TP1 103; a_t 2.0 and g 0.25 put X at 99.50."""
    base = dict(source="confluence", strategy="S/R Confluence", direction="bullish",
                entry_type="market", trigger_price=100.0, stop_loss=98.5, tp1=103.0,
                tp2=106.0, tp1_fraction=0.5, status=PlanStatus.PENDING, waits_next_open=True,
                reclaim_atr=2.0, reclaim_level=99.5)
    base.update(kw)
    return _plan(**base)


def _bear(**kw):
    base = dict(direction="bearish", stop_loss=101.5, tp1=97.0, tp2=94.0, reclaim_level=100.5)
    base.update(kw)
    return _bull(**base)


def _observed(df, plan, scale_out=True):
    seen = []
    with mno.observing(seen.append):
        res = simulate_exit(df, SIGNAL, plan, scale_out=scale_out)
    assert len(seen) == 1
    return res, seen[0]


# --- under the threshold the baseline rule applies ----------------------------------

@pytest.mark.parametrize("make, bar", [
    (_bull, (99.51, 100.2, 99.4, 100.0)),       # gap 0.49 < 0.50
    (_bear, (100.49, 100.6, 99.8, 100.0)),
])
def test_a_gap_just_under_the_threshold_fills_at_the_open(make, bar):
    res, seen = _observed(_bars({J: bar}), make())
    assert seen.decision == gr.FILL_OPEN and seen.reclaimed is False
    assert res.entry_index == J and res.entry_price == bar[0]


@pytest.mark.parametrize("make, bar", [
    (_bull, (98.5, 100.2, 98.0, 99.0)),
    (_bear, (101.5, 102.0, 99.9, 101.0)),
])
def test_an_open_at_the_stop_cancels_before_the_veto(make, bar):
    res, seen = _observed(_bars({J: bar}), make())
    assert res.cancel_reason == gr.OPEN_THROUGH_STOP and seen.decision == gr.OPEN_THROUGH_STOP


# --- armed, no reclaim ---------------------------------------------------------------

@pytest.mark.parametrize("make, bar", [
    (_bull, (99.50, 99.90, 99.0, 99.6)),        # exactly at X, never back to E
    (_bull, (99.00, 100.00, 98.9, 99.8)),       # a bare touch of E is not a reclaim
    (_bear, (100.50, 101.0, 100.1, 100.4)),
    (_bear, (101.00, 101.1, 100.00, 100.2)),
])
def test_no_reclaim_cancels_gap_no_reclaim(make, bar):
    res, seen = _observed(_bars({J: bar}), make())
    assert res.outcome == "not_triggered"
    assert res.cancel_reason == gr.GAP_NO_RECLAIM == "gap_no_reclaim"
    assert res.legs == [] and res.entry_index is None
    assert seen.decision == gr.RECLAIM_WAIT
    assert seen.reclaimed is False and seen.ambiguous is False and seen.fill_price is None
    assert seen.open_price == bar[0] and seen.reclaim_level == make().reclaim_level


@pytest.mark.parametrize("make, later", [
    (_bull, (99.8, 101.0, 99.7, 100.8)),
    (_bear, (100.2, 100.3, 99.0, 99.2)),
])
def test_a_reclaim_on_a_later_session_does_not_count(make, later):
    first = (99.0, 99.9, 98.9, 99.5) if make is _bull else (101.0, 101.1, 100.1, 100.5)
    res, _ = _observed(_bars({J: first, J + 1: later}), make())
    assert res.cancel_reason == gr.GAP_NO_RECLAIM


# --- armed, reclaimed ---------------------------------------------------------------

@pytest.mark.parametrize("make, bar, fill", [
    (_bull, (99.2, 100.2, 99.1, 100.1), 100.01),
    (_bear, (100.8, 100.9, 99.8, 99.9), 99.99),
])
def test_a_reclaim_fills_one_tick_through_entry_and_walks_on(make, bar, fill):
    df = _bars({J: bar})
    plan = make()
    res, seen = _observed(df, plan)
    assert res.entry_index == J and res.entry_price == fill
    assert seen.decision == gr.RECLAIM_WAIT
    assert seen.reclaimed is True and seen.ambiguous is False and seen.fill_price == fill
    assert seen.gap_atr == pytest.approx(abs(100.0 - bar[0]) / 2.0)
    mhd = HORIZONS[plan.horizon_key]["max_holding_days"]
    assert res == exit_sim._walk_for(plan, True)(df, J, fill, plan, mhd)


@pytest.mark.parametrize("make, bar, stop", [
    (_bull, (99.0, 100.3, 98.4, 99.0), 98.5),
    (_bear, (101.0, 101.6, 99.9, 100.8), 101.5),
])
def test_an_ambiguous_reclaim_bar_is_a_full_loss(make, bar, stop):
    res, seen = _observed(_bars({J: bar}), make())
    assert seen.reclaimed is True and seen.ambiguous is True
    assert res.outcome == "loss" and res.r_total == -1.0
    assert res.entry_index == res.exit_index == J
    assert res.legs == [{"fraction": 1.0, "exit_price": stop, "r": -1.0, "reason": "stop"}]


@pytest.mark.parametrize("make, bar, fill", [
    (_bull, (99.4, 103.2, 99.3, 103.0), 100.01),
    (_bear, (100.6, 100.7, 96.8, 97.0), 99.99),
])
def test_a_reclaim_bar_that_reaches_tp1_is_the_tp1_win(make, bar, fill):
    plan = make(tp1_fraction=1.0)
    res, _ = _observed(_bars({J: bar}), plan, scale_out=False)
    rr = abs(plan.tp1 - fill) / abs(fill - plan.stop_loss)
    assert res.outcome == "win" and res.exit_index == J and res.r_total == round(rr, 3)


def test_the_reclaim_fill_keeps_the_hold_cap_session_one():
    plan = _bull(source="strategy", strategy="Fibonacci", hold_cap_bars=5)
    res, _ = _observed(_bars({J: (99.2, 100.2, 99.1, 100.1)}), plan)
    assert res.entry_index == J and res.exit_index == J + 5 - 1


def test_the_reclaim_fill_is_never_risk_capped():
    """A stored 1.4% ceiling that the plan's own 1.5% risk at E already breaches: the
    decision order puts RECLAIM_WAIT before RISK_CAP, so the reclaim still fills."""
    plan = _bull(stop_ceiling_pct=1.4)
    res, seen = _observed(_bars({J: (99.2, 100.2, 99.1, 100.1)}), plan)
    assert seen.reclaimed is True and res.entry_price == 100.01


def test_a_sub_dollar_plan_reclaims_on_the_small_tick():
    plan = _bull(trigger_price=0.85, stop_loss=0.835, tp1=0.88, tp2=None, tp1_fraction=1.0,
                 reclaim_atr=0.0123, reclaim_level=0.8469)
    flat = (0.85, 0.8505, 0.8495, 0.85)
    res, seen = _observed(_bars({J: (0.846, 0.8501, 0.8455, 0.8498)}, flat=flat), plan)
    assert seen.reclaimed is True and res.entry_price == 0.8501
    res, seen = _observed(_bars({J: (0.846, 0.85, 0.8455, 0.8498)}, flat=flat), plan)
    assert res.cancel_reason == gr.GAP_NO_RECLAIM
