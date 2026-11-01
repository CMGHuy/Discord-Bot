"""V192-4: the gap-toward-stop rule, one module for live and replay. Bullish and
bearish twins of every rule; sub-$1 tick; ATR14 through the creating bar only."""
import math

import pytest

from swingbot import config
from swingbot.core.market.indicators import atr as atr_indicator
from swingbot.core.market.strategy_types import TURTLE_SOUP
from swingbot.core.planning import gap_reclaim as gr
from swingbot.core.planning.plan_types import PlanStatus, plan_to_dict
from tests.helpers import make_ohlcv
from tests.planning.test_plan_engine_model import _plan


def _wave(n=40):
    rows, prev = [], 100.0
    for i in range(n):
        close = 100.0 + 3.0 * math.sin(i / 3.0)
        open_ = prev + 0.3 * math.sin(i * 1.3)
        rows.append((open_, max(open_, close) + 0.6, min(open_, close) - 0.6, close))
        prev = close
    return make_ohlcv(rows)


def _bull(**kw):
    base = dict(source="confluence", strategy="S/R Confluence", direction="bullish",
                entry_type="market", trigger_price=100.0, stop_loss=98.5, tp1=103.0,
                status=PlanStatus.PENDING, waits_next_open=True)
    base.update(kw)
    return _plan(**base)


def _bear(**kw):
    base = dict(direction="bearish", stop_loss=101.5, tp1=97.0, tp2=94.0)
    base.update(kw)
    return _bull(**base)


@pytest.fixture
def knobs(monkeypatch):
    def set_(next_open, g):
        monkeypatch.setattr(config, "MARKET_ENTRY_NEXT_OPEN", next_open)
        monkeypatch.setattr(config, "GAP_RECLAIM_ATR", g)
    return set_


# --- constants and tick -------------------------------------------------------

def test_names_are_the_frozen_strings():
    assert (gr.OPEN_THROUGH_STOP, gr.GAP_NO_RECLAIM, gr.RISK_CAP) == (
        "open_through_stop", "gap_no_reclaim", "risk_cap")
    assert (gr.FILL_OPEN, gr.RECLAIM_WAIT) == ("open", "reclaim_wait")
    assert (gr.ATR_PERIOD, gr.MIN_ATR_BARS) == (14, 15)


@pytest.mark.parametrize("price, tick", [(1.0, 0.01), (250.0, 0.01), (0.9999, 0.0001),
                                         (0.85, 0.0001)])
def test_tick_for(price, tick):
    assert gr.tick_for(price) == tick


# --- ATR at t -------------------------------------------------------------------

def test_atr_at_is_wilder_atr14_through_the_creating_bar():
    df = _wave()
    expected = float(atr_indicator(df.iloc[:31], 14).iloc[-1])
    assert gr.atr_at(df, 30) == pytest.approx(expected, rel=0, abs=1e-12)
    assert gr.atr_at(df, 30) == pytest.approx(float(atr_indicator(df, 14).iloc[30]), abs=1e-12)


def test_atr_at_ignores_bar_t_plus_1():
    """NO-LOOKAHEAD: mutate bar t+1 and every later bar; a_t and X do not move."""
    df = _wave()
    before = gr.atr_at(df, 30)
    level = gr.reclaim_level_for(100.0, before, 0.25, "bullish")
    moved = df.copy()
    moved.iloc[31:, moved.columns.get_loc("High")] = 500.0
    moved.iloc[31:, moved.columns.get_loc("Low")] = 1.0
    assert gr.atr_at(moved, 30) == before
    assert gr.reclaim_level_for(100.0, gr.atr_at(moved, 30), 0.25, "bullish") == level


@pytest.mark.parametrize("index", [0, 5, 13])
def test_atr_at_needs_fifteen_bars(index):
    assert gr.atr_at(_wave(), index) is None


def test_atr_at_fifteen_bars_is_usable():
    assert gr.atr_at(_wave(), 14) is not None


def test_atr_at_zero_or_nan_is_none():
    flat = make_ohlcv([(100.0, 100.0, 100.0, 100.0)] * 30)
    assert gr.atr_at(flat, 20) is None
    holed = _wave()
    holed.iloc[:, :] = float("nan")
    assert gr.atr_at(holed, 30) is None


def test_atr_at_beyond_the_frame_raises():
    with pytest.raises(IndexError):
        gr.atr_at(_wave(40), 40)


# --- X --------------------------------------------------------------------------

@pytest.mark.parametrize("direction, atr, g, expected", [
    ("bullish", 1.234, 0.25, 99.69),      # 99.6915 floored
    ("bearish", 1.234, 0.25, 100.31),     # 100.3085 ceiled
    ("bullish", 2.0, 0.25, 99.5),         # exactly on the grid stays put
    ("bearish", 2.0, 0.25, 100.5),
    ("bullish", 1.0, 0.10, 99.9),
    ("bearish", 1.0, 0.50, 100.5),
])
def test_reclaim_level_rounds_away_from_entry(direction, atr, g, expected):
    assert gr.reclaim_level_for(100.0, atr, g, direction) == expected


def test_reclaim_level_sub_dollar_uses_the_small_tick():
    assert gr.reclaim_level_for(0.85, 0.0123, 0.25, "bullish") == 0.8469   # 0.846925 floored
    assert gr.reclaim_level_for(0.85, 0.0123, 0.25, "bearish") == 0.8531   # 0.853075 ceiled


# --- knob reads -----------------------------------------------------------------

@pytest.mark.parametrize("next_open, g, expected", [
    (False, 0.0, 0.0), (False, 0.25, 0.0), (True, 0.0, 0.0), (True, 0.25, 0.25)])
def test_effective_g(knobs, next_open, g, expected):
    knobs(next_open, g)
    assert gr.effective_g() == expected


def test_next_open_applies_only_to_market_plans_with_the_knob_on(knobs):
    knobs(False, 0.0)
    assert not gr.next_open_applies(_bull())
    knobs(True, 0.0)
    assert gr.next_open_applies(_bull())
    assert gr.next_open_applies(_bear(source="strategy", strategy="Fibonacci"))
    assert not gr.next_open_applies(_bull(entry_type="stop_entry"))
    assert not gr.next_open_applies(_bull(entry_type="limit"))
    assert not gr.next_open_applies(_bull(source="strategy", strategy=TURTLE_SOUP))


def test_waits_for_open_needs_the_persisted_marker():
    assert gr.waits_for_open(_bull())
    assert not gr.waits_for_open(_bull(waits_next_open=None)), (
        "a hand-built PENDING market plan keeps the close fill")
    assert not gr.waits_for_open(_bull(status=PlanStatus.ACTIVE))
    assert not gr.waits_for_open(_bull(entry_type="stop_entry"))


def test_waits_for_open_ignores_the_knob(knobs):
    """A plan resting since before a knob flip keeps its path (marker, not config)."""
    knobs(False, 0.0)
    assert gr.waits_for_open(_bull())


# --- the builder stamp ------------------------------------------------------------

def test_stamp_with_g_zero_sets_the_marker_only(knobs):
    knobs(True, 0.0)
    plan = _bull(waits_next_open=None, entry_price=100.0)
    gr.stamp_next_open(plan, _wave(), 30)
    assert plan.entry_price is None and plan.waits_next_open is True
    assert plan.reclaim_atr is None and plan.reclaim_level is None
    assert {"reclaim_atr", "reclaim_level", "reclaim_session"}.isdisjoint(plan_to_dict(plan))


@pytest.mark.parametrize("make, sign", [(_bull, -1), (_bear, 1)])
def test_stamp_with_g_stores_atr_and_level(knobs, make, sign):
    knobs(True, 0.25)
    df = _wave()
    plan = make(waits_next_open=None, entry_price=100.0)
    gr.stamp_next_open(plan, df, 30)
    a = gr.atr_at(df, 30)
    assert plan.reclaim_atr == a
    assert plan.reclaim_level == gr.reclaim_level_for(100.0, a, 0.25, plan.direction)
    assert (plan.reclaim_level - 100.0) * sign > 0
    assert plan.entry_price is None and plan.waits_next_open is True


def test_stamp_without_usable_atr_leaves_no_veto(knobs):
    """Fewer than 15 bars: the plan fills at the open like the baseline, never a crash."""
    knobs(True, 0.25)
    plan = _bull(waits_next_open=None)
    gr.stamp_next_open(plan, _wave(), 10)
    assert plan.waits_next_open is True
    assert plan.reclaim_atr is None and plan.reclaim_level is None


def test_stamp_ignores_a_lone_gap_knob(knobs):
    knobs(False, 0.25)
    plan = _bull(waits_next_open=None)
    gr.stamp_next_open(plan, _wave(), 30)
    assert plan.reclaim_level is None


# --- gap and the open decision ------------------------------------------------------

def test_gap_toward_stop_sign():
    assert gr.gap_toward_stop(_bull(), 99.0) == pytest.approx(1.0)
    assert gr.gap_toward_stop(_bull(), 101.0) == pytest.approx(-1.0)
    assert gr.gap_toward_stop(_bear(), 101.0) == pytest.approx(1.0)
    assert gr.gap_toward_stop(_bear(), 99.0) == pytest.approx(-1.0)


@pytest.mark.parametrize("open_price, expected", [
    (99.51, gr.FILL_OPEN),          # gap 0.49 < g x a_t = 0.50: fills like the baseline
    (99.50, gr.RECLAIM_WAIT),       # exactly at X
    (99.00, gr.RECLAIM_WAIT),       # beyond X
    (98.51, gr.RECLAIM_WAIT),
    (98.50, gr.OPEN_THROUGH_STOP),  # at the stop
    (97.00, gr.OPEN_THROUGH_STOP),  # through it
    (100.1, gr.FILL_OPEN),          # gap away from the stop, within risk cap
    (101.0, gr.RISK_CAP),           # gap away increases stop distance above 2%
    (103.0, gr.RISK_CAP),           # (103 - 98.5) / 103 = 4.4% > the 2% confluence ceiling
])
def test_decide_at_open_bullish(open_price, expected):
    assert gr.decide_at_open(_bull(reclaim_level=99.50), open_price) == expected


@pytest.mark.parametrize("open_price, expected", [
    (100.49, gr.FILL_OPEN),
    (100.50, gr.RECLAIM_WAIT),
    (101.00, gr.RECLAIM_WAIT),
    (101.49, gr.RECLAIM_WAIT),
    (101.50, gr.OPEN_THROUGH_STOP),
    (103.00, gr.OPEN_THROUGH_STOP),
    (99.9, gr.FILL_OPEN),
    (99.0, gr.RISK_CAP),
    (97.0, gr.RISK_CAP),            # (101.5 - 97) / 97 = 4.6%
])
def test_decide_at_open_bearish(open_price, expected):
    assert gr.decide_at_open(_bear(reclaim_level=100.50), open_price) == expected


def test_without_a_level_the_baseline_fills_any_gap_short_of_the_stop():
    assert gr.decide_at_open(_bull(), 98.6) == gr.FILL_OPEN
    assert gr.decide_at_open(_bear(), 101.4) == gr.FILL_OPEN
    assert gr.decide_at_open(_bull(), 98.5) == gr.OPEN_THROUGH_STOP


def test_a_stored_ceiling_drives_the_risk_cap():
    plan = _bull(stop_ceiling_pct=5.0)
    assert gr.decide_at_open(plan, 103.0) == gr.FILL_OPEN


# --- the reclaim -----------------------------------------------------------------

def test_reclaim_needs_one_tick_through_entry_bullish():
    plan = _bull(reclaim_level=99.5)
    assert not gr.reclaim_touched(plan, high=100.0, low=98.9)     # a bare touch of E
    assert gr.reclaim_touched(plan, high=100.01, low=98.9)
    assert gr.reclaim_fill_price(plan) == 100.01


def test_reclaim_needs_one_tick_through_entry_bearish():
    plan = _bear(reclaim_level=100.5)
    assert not gr.reclaim_touched(plan, high=101.2, low=100.0)
    assert gr.reclaim_touched(plan, high=101.2, low=99.99)
    assert gr.reclaim_fill_price(plan) == 99.99


def test_reclaim_sub_dollar_tick():
    bull = _bull(trigger_price=0.85, stop_loss=0.835, tp1=0.88, reclaim_level=0.8469)
    assert not gr.reclaim_touched(bull, high=0.85, low=0.84)
    assert gr.reclaim_touched(bull, high=0.8501, low=0.84)
    assert gr.reclaim_fill_price(bull) == 0.8501
    bear = _bear(trigger_price=0.85, stop_loss=0.865, tp1=0.82, tp2=None, reclaim_level=0.8531)
    assert gr.reclaim_touched(bear, high=0.86, low=0.8499)
    assert gr.reclaim_fill_price(bear) == 0.8499


@pytest.mark.parametrize("index", [14, 20, 30])
def test_atr_and_reclaim_level_match_a_frame_truncated_at_t(index):
    full = _wave()
    truncated = full.iloc[:index + 1]
    assert gr.atr_at(full, index) == gr.atr_at(truncated, index)
    for direction in ("bullish", "bearish"):
        assert gr.reclaim_level_for(100, gr.atr_at(full, index), .25, direction) == (
            gr.reclaim_level_for(100, gr.atr_at(truncated, index), .25, direction))


def test_atr_at_empty_frame_raises():
    with pytest.raises(IndexError):
        gr.atr_at(_wave().iloc[:0], 0)
