"""v212 shared fill rule (spec § The rule 6, G2 tie rules): trade-through
primary, touch as the sensitivity, gap fills at the open, a gap through the
stop fills and is stopped, TP1 cancel inclusive, a bar reaching both L and
TP1 is cancelled."""
import pytest

from swingbot.core.planning.limit_entry_rule import (BarOutcome, bar_outcome, is_arm_limit,
                                                     tp1_reached)
from swingbot.core.planning.plan_types import PlanStatus, TradePlanV2

LONG = dict(direction="bullish", trigger_price=98.5, stop_loss=96.75, tp1=104.0)
SHORT = dict(direction="bearish", trigger_price=101.5, stop_loss=103.26, tp1=96.0)


def _plan(levels, **kw):
    base = dict(plan_id="p1", ticker="XYZ", created_at="2026-11-06", source="confluence",
                strategy="S/R Confluence", horizon_key="4w", entry_type="limit",
                entry_price=None, expiry_bars=3, tp1_fraction=0.5, tp2=None,
                breakeven_trigger_fraction=0.5, trail_atr_mult=2.5, quality_score=0,
                quality_breakdown=[], badge="WEAK", badge_stats={}, status=PlanStatus.PENDING,
                status_history=[], limit_cancel_level=levels["tp1"], limit_strict_fill=True,
                limit_entry_f=0.5, **levels)
    base.update(kw)
    return TradePlanV2(**base)


def _out(levels, o, h, l, **kw):
    return bar_outcome(_plan(levels), open_=o, high=h, low=l, **kw)


# mirrored bars: (open, high, low) for the long, then the short
CASES = {
    "trade_through": ((99.5, 100.0, 98.49), (100.5, 101.51, 100.0)),
    "touch_only": ((99.5, 100.0, 98.5), (100.5, 101.5, 100.0)),
    "gap_through_limit": ((98.0, 98.4, 97.5), (102.0, 102.5, 101.6)),
    "open_at_limit": ((98.5, 99.0, 98.2), (101.5, 101.8, 101.0)),
    "gap_through_stop": ((96.0, 97.0, 95.5), (104.0, 104.5, 103.0)),
    "open_at_stop": ((96.75, 97.5, 96.0), (103.26, 104.0, 103.0)),
    "tp1_exact": ((100.0, 104.0, 99.0), (100.0, 101.0, 96.0)),
    "both_l_and_tp1": ((100.0, 105.0, 98.0), (100.0, 102.0, 95.0)),
    "nothing": ((99.5, 100.5, 99.0), (100.5, 101.0, 100.0)),
}
SIDES = pytest.mark.parametrize("side,levels", [(0, LONG), (1, SHORT)])


@SIDES
def test_trade_through_fills_at_the_limit(side, levels):
    assert _out(levels, *CASES["trade_through"][side]) == BarOutcome("fill", levels["trigger_price"], False)


@SIDES
def test_a_bare_touch_fills_only_in_the_touch_sensitivity(side, levels):
    bar = CASES["touch_only"][side]
    assert _out(levels, *bar) == BarOutcome("none", None, False)
    assert _out(levels, *bar, touch=True) == BarOutcome("fill", levels["trigger_price"], False)


@SIDES
@pytest.mark.parametrize("case", ["gap_through_limit", "open_at_limit"])
def test_an_open_at_or_through_the_limit_fills_at_the_open(side, levels, case):
    bar = CASES[case][side]
    assert _out(levels, *bar) == BarOutcome("fill", bar[0], False)


@SIDES
@pytest.mark.parametrize("case", ["gap_through_stop", "open_at_stop"])
def test_an_open_at_or_through_the_stop_fills_and_is_gap_stopped(side, levels, case):
    bar = CASES[case][side]
    assert _out(levels, *bar) == BarOutcome("fill", bar[0], True)


@SIDES
def test_tp1_cancel_is_inclusive(side, levels):
    assert _out(levels, *CASES["tp1_exact"][side]) == BarOutcome("cancel", None, False)


@SIDES
def test_a_bar_reaching_both_the_limit_and_tp1_is_cancelled(side, levels):
    assert _out(levels, *CASES["both_l_and_tp1"][side]).kind == "cancel"


@SIDES
def test_a_quiet_bar_is_nothing(side, levels):
    assert _out(levels, *CASES["nothing"][side]).kind == "none"


@SIDES
def test_gap_through_the_stop_wins_over_a_tp1_print_on_the_same_bar(side, levels):
    o = 96.0 if side == 0 else 104.0
    assert _out(levels, o, 105.0, 95.0) == BarOutcome("fill", o, True)   # bar spans TP1 too


def test_no_open_skips_the_open_rules():
    # a live poll below the stop with no session open: trade-through at L, not a gap
    assert bar_outcome(_plan(LONG), open_=None, high=96.0, low=96.0) == BarOutcome("fill", 98.5, False)
    assert bar_outcome(_plan(LONG), open_=None, high=99.0, low=99.0).kind == "none"


def test_trade_through_needs_a_full_tick():
    assert _out(LONG, 99.5, 100.0, 98.495).kind == "none"       # half a tick under
    assert _out(LONG, 99.5, 100.0, 98.49).kind == "fill"


def test_tp1_reached_falls_back_to_tp1_without_a_cancel_level():
    plan = _plan(LONG, limit_cancel_level=None)
    assert tp1_reached(plan, 104.0, 99.0) and not tp1_reached(plan, 103.99, 99.0)


@pytest.mark.parametrize("kw,expected", [
    ({}, True),
    ({"limit_entry_f": None}, False),                       # v113 / v131 limits
    ({"entry_type": "market", "entry_price": 100.0}, False),
])
def test_is_arm_limit(kw, expected):
    assert is_arm_limit(_plan(LONG, **kw)) is expected


def test_non_arm_plans_are_refused():
    with pytest.raises(ValueError, match="arm limit"):
        bar_outcome(_plan(LONG, limit_entry_f=None), open_=99.0, high=99.5, low=98.0)


# L - tick (long) / L + tick (short) lands a hair off the printed price in float
# arithmetic: 1.13 - 0.01 == 1.1199999999999999, 1.12 + 0.01 == 1.1300000000000001
@pytest.mark.parametrize("limit,low", [(1.13, 1.12), (1.38, 1.37), (1.63, 1.62), (1.88, 1.87)])
def test_long_trade_through_one_tick_under_survives_float_noise(limit, low):
    levels = dict(direction="bullish", trigger_price=limit, stop_loss=1.0, tp1=2.0)
    assert _out(levels, limit + 0.05, limit + 0.1, low) == BarOutcome("fill", limit, False)


@pytest.mark.parametrize("limit,high", [(1.12, 1.13), (1.37, 1.38), (1.62, 1.63), (1.87, 1.88)])
def test_short_trade_through_one_tick_over_survives_float_noise(limit, high):
    levels = dict(direction="bearish", trigger_price=limit, stop_loss=2.0, tp1=1.0)
    assert _out(levels, limit - 0.05, high, limit - 0.1) == BarOutcome("fill", limit, False)


@SIDES
def test_trade_through_tolerance_edge_is_inclusive(side, levels):
    # an extreme exactly at L -/+ tick -/+ 1e-9 still fills (the tolerance edge itself)
    L = levels["trigger_price"]
    if side == 0:
        bar = (99.5, 100.0, L - 0.01 + 1e-9)
    else:
        bar = (100.5, L + 0.01 - 1e-9, 100.0)
    assert _out(levels, *bar) == BarOutcome("fill", L, False)


@SIDES
def test_tp1_cancel_wins_over_a_gap_through_the_limit_above_the_stop(side, levels):
    # open between stop and L (rule 3 would fill at the open), bar also reaches TP1
    bar = (98.0, 104.0, 97.5) if side == 0 else (102.0, 102.5, 96.0)
    assert _out(levels, *bar) == BarOutcome("cancel", None, False)
