"""V192-6: a market plan waiting for its next open fills at Open[t+1] in replay (both
measurement arms), with an open-through-stop and risk-cap cancel, a fill-bar check of
TP1-at-the-open, the stop and TP1 (stop-first), the normal walk after the fill bar, and
the fill session counted as session 1 of a hold cap. Bullish and bearish."""
import pytest

from swingbot.core.market.strategy_types import HORIZONS, TURTLE_SOUP
from swingbot.core.planning import exit_sim
from swingbot.core.planning import gap_reclaim as gr
from swingbot.core.planning import market_next_open as mno
from swingbot.core.planning import next_open_entry as noe
from swingbot.core.planning.exit_sim import simulate_exit
from swingbot.core.planning.params import PLAN_SHAPES
from swingbot.core.planning.plan_types import PlanStatus
from tests.helpers import make_ohlcv
from tests.planning.test_plan_engine_model import _plan

SIGNAL = 30
FLAT = (100.0, 100.5, 99.5, 100.0)     # never reaches 98.5 / 101.5 or 103 / 97


def _bars(overrides=None, n=120):
    rows = [FLAT] * n
    for i, row in (overrides or {}).items():
        rows[i] = row
    return make_ohlcv(rows, start="2024-01-02")


def _bull(**kw):
    base = dict(source="confluence", strategy="S/R Confluence", direction="bullish",
                entry_type="market", trigger_price=100.0, stop_loss=98.5, tp1=103.0,
                tp2=106.0, tp1_fraction=0.5, status=PlanStatus.PENDING, waits_next_open=True)
    base.update(kw)
    return _plan(**base)


def _bear(**kw):
    base = dict(direction="bearish", stop_loss=101.5, tp1=97.0, tp2=94.0)
    base.update(kw)
    return _bull(**base)


def _run(df, plan, scale_out=True):
    return simulate_exit(df, SIGNAL, plan, scale_out=scale_out)


# --- dispatch ---------------------------------------------------------------------

def test_a_pending_market_plan_without_the_marker_keeps_the_close_fill():
    df = _bars({SIGNAL + 1: (99.0, 99.6, 98.9, 99.2)})
    res = _run(df, _bull(waits_next_open=None))
    assert res.entry_index == SIGNAL and res.entry_price == 100.0


def test_turtle_soup_keeps_the_v180_path_even_with_the_marker():
    shape = PLAN_SHAPES[TURTLE_SOUP]
    plan = _bull(source="strategy", strategy=TURTLE_SOUP, horizon_key="2w",
                 tp1_fraction=shape["tp1_fraction"], hold_cap_bars=shape["hold_cap_bars"],
                 stop_loss=98.0, tp1=104.0, tp2=None)
    df = _bars({SIGNAL + 1: (99.5, 100.2, 99.4, 100.0)})
    expected = noe.next_open_exit(df, SIGNAL, plan, exit_sim._hold_cap_bars(plan, 10))
    assert simulate_exit(df, SIGNAL, plan, scale_out=True, max_holding_days=10) == expected


# --- the open ---------------------------------------------------------------------

@pytest.mark.parametrize("make, bar", [
    (_bull, (99.8, 100.3, 99.6, 100.0)),
    (_bear, (100.2, 100.4, 99.7, 100.0)),
])
def test_fills_at_the_next_open(make, bar):
    res = _run(_bars({SIGNAL + 1: bar}), make())
    assert res.entry_index == SIGNAL + 1 and res.entry_price == bar[0]
    assert res.outcome == "timeout"


@pytest.mark.parametrize("make, opens", [(_bull, [98.5, 97.0]), (_bear, [101.5, 103.0])])
def test_an_open_at_or_through_the_stop_cancels(make, opens):
    for bar_open in opens:
        bar = (bar_open, bar_open + 0.5, bar_open - 0.5, bar_open)
        res = _run(_bars({SIGNAL + 1: bar}), make())
        assert res.outcome == "not_triggered"
        assert res.cancel_reason == gr.OPEN_THROUGH_STOP == "open_through_stop"
        assert res.legs == [] and res.entry_index is None


@pytest.mark.parametrize("make, bar_open", [(_bull, 101.0), (_bear, 99.0)])
def test_a_stop_past_the_ceiling_from_the_open_cancels(make, bar_open):
    """(101 - 98.5) / 101 = 2.5% and (101.5 - 99) / 99 = 2.5%, past the 2% confluence ceiling."""
    bar = (bar_open, bar_open + 0.3, bar_open - 0.3, bar_open)
    res = _run(_bars({SIGNAL + 1: bar}), make())
    assert res.outcome == "not_triggered" and res.cancel_reason == gr.RISK_CAP == "risk_cap"


def test_no_next_bar_is_not_triggered_without_a_reason():
    df = _bars(n=SIGNAL + 1)
    res = _run(df, _bull())
    assert res.outcome == "not_triggered" and res.cancel_reason is None


# --- the fill bar -------------------------------------------------------------------

@pytest.mark.parametrize("make, bar, stop", [
    (_bull, (99.8, 100.3, 98.4, 99.0), 98.5),
    (_bear, (100.2, 101.6, 99.9, 101.0), 101.5),
])
def test_a_stop_touch_on_the_fill_bar_is_a_full_loss(make, bar, stop):
    res = _run(_bars({SIGNAL + 1: bar}), make())
    assert res.outcome == "loss" and res.r_total == -1.0
    assert res.entry_index == res.exit_index == SIGNAL + 1
    assert res.legs == [{"fraction": 1.0, "exit_price": stop, "r": -1.0, "reason": "stop"}]


@pytest.mark.parametrize("make, bar", [
    (_bull, (99.8, 103.5, 98.4, 100.0)),
    (_bear, (100.2, 101.6, 96.5, 100.0)),
])
def test_stop_first_when_the_fill_bar_touches_both(make, bar):
    res = _run(_bars({SIGNAL + 1: bar}), make())
    assert res.outcome == "loss" and res.r_total == -1.0


@pytest.mark.parametrize("make, bar, rr", [
    (_bull, (99.8, 103.2, 99.6, 103.0), (103.0 - 99.8) / (99.8 - 98.5)),
    (_bear, (100.2, 100.4, 96.8, 97.0), (100.2 - 97.0) / (101.5 - 100.2)),
])
def test_tp1_on_the_fill_bar_single_leg_is_the_tp1_win(make, bar, rr):
    res = _run(_bars({SIGNAL + 1: bar}), make(tp1_fraction=1.0), scale_out=False)
    assert res.outcome == "win" and res.exit_index == SIGNAL + 1
    assert res.r_total == round(rr, 3)
    assert res.legs[0]["reason"] == "tp1" and res.legs[0]["exit_price"] == make().tp1


@pytest.mark.parametrize("make, bar", [
    (_bull, (99.8, 103.2, 99.6, 103.0)),
    (_bear, (100.2, 100.4, 96.8, 97.0)),
])
def test_tp1_on_the_fill_bar_scale_out_hands_the_runner_on_from_the_fill_bar(make, bar):
    df = _bars({SIGNAL + 1: bar})
    plan = make()
    res = _run(df, plan)
    j, fill = SIGNAL + 1, bar[0]
    is_bull = plan.direction == "bullish"
    mhd = HORIZONS[plan.horizon_key]["max_holding_days"]
    ctx = exit_sim._WalkCtx(df["High"].values, df["Low"].values, df["Close"].values, j, fill,
                            plan, is_bull, 1 if is_bull else -1, abs(fill - plan.stop_loss),
                            min(j + mhd, len(df) - 1), df["Open"].values)
    assert res == exit_sim._runner_result(ctx, exit_sim._runner_phase(df, ctx, j))
    assert res.legs[0] == {"fraction": 0.5, "exit_price": plan.tp1,
                           "r": round(abs(plan.tp1 - fill) / abs(fill - plan.stop_loss), 3),
                           "reason": "tp1"}


@pytest.mark.parametrize("make, bar_open", [(_bull, 103.2), (_bear, 96.8)])
def test_an_open_beyond_tp1_is_a_0r_gap_target_scratch(make, bar_open):
    """v180's _bar_exit convention; a wide stored ceiling lets the open fill at all."""
    bar = (bar_open, bar_open + 0.4, bar_open - 0.4, bar_open)
    res = _run(_bars({SIGNAL + 1: bar}), make(stop_ceiling_pct=10.0))
    assert res.outcome == "scratch" and res.r_total == 0.0
    assert res.entry_price == bar_open and res.exit_index == SIGNAL + 1
    assert res.legs == [{"fraction": 1.0, "exit_price": bar_open, "r": 0.0,
                         "reason": noe.GAP_TARGET_REASON}]


# --- after the fill bar ---------------------------------------------------------------

@pytest.mark.parametrize("make, bar, later", [
    (_bull, (99.8, 100.3, 99.6, 100.0), (99.5, 99.6, 98.4, 98.6)),
    (_bear, (100.2, 100.4, 99.7, 100.0), (100.5, 101.6, 100.4, 101.4)),
])
def test_the_walk_starts_after_the_fill_bar(make, bar, later):
    df = _bars({SIGNAL + 1: bar, SIGNAL + 3: later})
    plan = make()
    res = _run(df, plan)
    mhd = HORIZONS[plan.horizon_key]["max_holding_days"]
    assert res == exit_sim._walk_for(plan, True)(df, SIGNAL + 1, bar[0], plan, mhd)
    assert res.outcome == "loss" and res.exit_index == SIGNAL + 3


def test_a_confluence_plan_without_a_cap_walks_max_holding_days_after_the_fill():
    df = _bars({SIGNAL + 1: (99.8, 100.3, 99.6, 100.0)})
    res = _run(df, _bull())
    assert res.outcome == "timeout"
    assert res.exit_index == SIGNAL + 1 + HORIZONS["4w"]["max_holding_days"]


def test_the_fill_session_is_session_one_of_a_hold_cap():
    plan = _bull(source="strategy", strategy="Fibonacci", hold_cap_bars=5)
    assert exit_sim._counts_fill_session(plan)
    assert not exit_sim._counts_fill_session(_bull(waits_next_open=None, hold_cap_bars=5))
    res = _run(_bars({SIGNAL + 1: (99.8, 100.3, 99.6, 100.0)}), plan)
    assert res.outcome == "timeout" and res.exit_index == SIGNAL + 1 + 5 - 1


# --- the observer -----------------------------------------------------------------

def test_observer_sees_every_decision():
    seen = []
    with mno.observing(seen.append):
        _run(_bars({SIGNAL + 1: (99.8, 100.3, 99.6, 100.0)}), _bull())
        _run(_bars({SIGNAL + 1: (98.0, 98.4, 97.5, 98.2)}), _bull())
        _run(_bars(n=SIGNAL + 1), _bull())
    _run(_bars({SIGNAL + 1: (99.8, 100.3, 99.6, 100.0)}), _bull())   # outside: not observed
    assert [d.decision for d in seen] == [gr.FILL_OPEN, gr.OPEN_THROUGH_STOP, "no_bar"]
    first = seen[0]
    assert (first.ticker, first.strategy, first.horizon_key, first.source, first.direction) == (
        "AAPL", "S/R Confluence", "4w", "confluence", "bullish")
    assert first.signal_date == str(_bars().index[SIGNAL].date())
    assert (first.entry, first.stop, first.open_price, first.fill_price) == (100.0, 98.5, 99.8, 99.8)
    assert first.reclaimed is False and first.ambiguous is False
    assert first.atr is None and first.reclaim_level is None and first.gap_atr is None
    assert seen[1].fill_price is None and seen[2].open_price is None


def test_gap_atr_is_the_gap_over_the_stored_atr():
    seen = []
    with mno.observing(seen.append):
        _run(_bars({SIGNAL + 1: (99.8, 100.3, 99.6, 100.0)}), _bull(reclaim_atr=0.8))
    assert seen[0].gap_atr == pytest.approx(0.2 / 0.8)


def test_observers_nest_and_unwind_on_error():
    outer, inner = [], []
    with mno.observing(outer.append):
        with pytest.raises(RuntimeError):
            with mno.observing(inner.append):
                raise RuntimeError("boom")
        _run(_bars({SIGNAL + 1: (99.8, 100.3, 99.6, 100.0)}), _bull())
    assert len(outer) == 1 and inner == []
