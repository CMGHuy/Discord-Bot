"""V192-13: live and replay agree on one waiting market plan -- E, a_t and X at
creation, and every outcome of the open decision. The replay is
exit_sim.simulate_exit (market_next_open); live is PlanManager. The one designed
difference: the replay fills a reclaim at E + one tick (the stop order's
slippage), live at E. DB-backed for the live half."""
import pandas as pd
import pytest

from swingbot.core.planning import gap_reclaim as gr
from swingbot.core.planning.builders import build_confluence_plan
from swingbot.core.planning.exit_sim import simulate_exit
from swingbot.core.planning.plan_engine import PlanStatus
from tests.helpers import make_ohlcv
from tests.planning.test_plan_manager_market_open import (OPEN, _bear, _bull, _env,  # noqa: F401
                                                         _et, _flags, _tr)
from tests.scanning.test_v192_scan_to_fill import (AFTER_CLOSE, _attach, _frame,  # noqa: F401
                                                   _scenario, knobs, v2_on)

SIGNAL = 30


@pytest.mark.parametrize("direction", ["bullish", "bearish"])
def test_e_a_t_and_x_are_the_same_live_and_in_replay(knobs, direction):
    knobs(True, 0.25)
    df = _frame()
    live = _attach(df, AFTER_CLOSE, direction)
    replay = build_confluence_plan(_scenario(direction), df, ticker="AAPL", horizon_key="4w",
                                   primary_strategy="S/R Confluence")
    assert (live.trigger_price, live.reclaim_atr, live.reclaim_level) == (
        replay.trigger_price, replay.reclaim_atr, replay.reclaim_level)
    assert live.reclaim_atr == gr.atr_at(df, len(df) - 1)


def _bars(next_bar):
    rows = [(100.0, 100.4, 99.6, 100.0)] * 60
    rows[SIGNAL + 1] = next_bar
    df = make_ohlcv(rows)
    df.index = pd.bdate_range(end="2026-12-31", periods=len(rows))
    return df


#: (case, plan maker, plan overrides, bar t+1 (O, H, L, C), live prices after the open)
CASES = [
    ("fill", _bull, {}, (99.8, 100.3, 99.6, 100.0), []),
    ("fill", _bear, {}, (100.2, 100.4, 99.7, 100.0), []),
    ("through_stop", _bull, {}, (98.0, 98.6, 97.8, 98.2), []),
    ("through_stop", _bear, {}, (102.0, 102.2, 101.4, 101.8), []),
    ("risk_cap", _bull, {}, (100.6, 101.0, 100.4, 100.8), []),
    ("gap_target", _bull, {"stop_ceiling_pct": 10.0}, (103.2, 103.6, 102.8, 103.2), []),
    ("gap_target", _bear, {"stop_ceiling_pct": 10.0}, (96.8, 97.2, 96.4, 96.8), []),
    ("reclaim", _bull, {"reclaim_level": 99.5, "reclaim_atr": 2.0},
     (99.0, 100.3, 98.9, 100.2), [100.01]),
    ("reclaim", _bear, {"reclaim_level": 100.5, "reclaim_atr": 2.0},
     (101.0, 101.1, 99.7, 99.8), [99.99]),
    ("no_reclaim", _bull, {"reclaim_level": 99.5, "reclaim_atr": 2.0},
     (99.0, 99.6, 98.9, 99.3), [99.3]),
    ("no_reclaim", _bear, {"reclaim_level": 100.5, "reclaim_atr": 2.0},
     (101.0, 101.1, 100.4, 100.7), [100.7]),
]


def _live(make, overrides, open_price, later):
    store, mgr = _env(make(**overrides), [open_price, *later])
    events = mgr.poll(OPEN)
    if later:
        late = _et(14, 10) if later[0] in (100.01, 99.99) else _et(14, 16, 5)
        events += mgr.poll(late)
    return store.get("p1"), events


@pytest.mark.parametrize("case, make, overrides, bar, later", CASES,
                         ids=[f"{c[0]}-{c[1].__name__}" for c in CASES])
def test_the_open_decision_is_the_same_live_and_in_replay(case, make, overrides, bar, later):
    replay = simulate_exit(_bars(bar), SIGNAL, make(**overrides), scale_out=True)
    live, events = _live(make, overrides, bar[0], later)
    transitions = _tr(events)
    if case == "fill":
        assert replay.entry_price == live.entry_price == bar[0]
        assert live.status == PlanStatus.ACTIVE
    elif case == "through_stop":
        assert replay.outcome == "not_triggered" and replay.cancel_reason == gr.OPEN_THROUGH_STOP
        assert "cancelled_open_through_stop" in transitions
    elif case == "risk_cap":
        assert replay.cancel_reason == gr.RISK_CAP and "cancelled_risk_cap" in transitions
    elif case == "gap_target":
        assert (replay.outcome, replay.r_total, replay.entry_price) == ("scratch", 0.0, bar[0])
        assert replay.legs[0]["reason"] == "gap_target"
        closed = [e for e in events if e.transition == "closed"]
        assert closed and closed[0].detail["leg"]["r"] == 0.0
        assert closed[0].detail["reason"] == "gap_target" and live.entry_price == bar[0]
    elif case == "reclaim":
        plan = make(**overrides)
        assert replay.entry_price == gr.reclaim_fill_price(plan)
        assert live.entry_price == plan.trigger_price
        assert transitions[0] == "gap_reclaim_order" and "filled" in transitions
    else:
        assert replay.cancel_reason == gr.GAP_NO_RECLAIM
        assert live.status == PlanStatus.CANCELLED and "cancelled_gap_no_reclaim" in transitions
