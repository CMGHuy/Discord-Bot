"""v189 D1: one trade-level R (`metrics.r_multiple`) and one leg
contribution (`fraction x r`) that every leg sum uses.

Golden geometry (spec § Testing): 100 shares, entry 100, stop 95 (1R = $5),
TP1 110 on half the position (+2R), runner on the other half. Every value
below is hand-computed.
"""
import math

import pytest

from swingbot.core.analytics import metrics
from swingbot.core.tracking.performance import closed_r_multiple

TP1_LEG = {"fraction": 0.5, "exit_price": 110.0, "r": 2.0, "reason": "tp1"}
#: A price with a long binary expansion, so rounding would show.
ODD_PRICE = 101.0 + 1.0 / 3.0


def _trade(legs=None, *, exit_price=None, direction="bullish", entry=100.0, stop=95.0):
    trade = {"direction": direction, "entry": entry, "stop_loss": stop,
             "exit_price": exit_price, "shares": 100}
    if legs is not None:
        trade["legs"] = [dict(leg) for leg in legs]
    return trade


# --- leg_contribution_r ------------------------------------------------------

def test_leg_contribution_is_fraction_times_r():
    assert metrics.leg_contribution_r(TP1_LEG) == pytest.approx(1.0)
    assert metrics.leg_contribution_r({"fraction": 0.5, "r": -2.4}) == pytest.approx(-1.2)


@pytest.mark.parametrize("leg", [{"fraction": 0.5}, {"r": 2.0}, {}])
def test_leg_contribution_is_none_when_fraction_or_r_is_missing(leg):
    assert metrics.leg_contribution_r(leg) is None


# --- _blended_r_raw / r_multiple ---------------------------------------------

def test_blended_raw_is_unrounded_and_r_multiple_rounds_legs_only():
    # Runner at the v39 floor 106.666..: r = 1.3333.., net = 1 + 0.6666.. = 1.6666..
    floor = 100.0 + (2.0 / 3.0) * 10.0
    trade = _trade([TP1_LEG, {"fraction": 0.5, "exit_price": floor,
                              "r": (floor - 100.0) / 5.0, "reason": "tp1_runner_be"}],
                   exit_price=floor)
    assert metrics._blended_r_raw(trade) == pytest.approx(5.0 / 3.0, abs=1e-12)
    assert metrics.r_multiple(trade) == 1.67


def test_single_exit_r_multiple_stays_unrounded():
    trade = _trade(exit_price=ODD_PRICE)
    expected = (ODD_PRICE - 100.0) / 5.0
    assert metrics._blended_r_raw(trade) == expected
    assert metrics.r_multiple(trade) == expected


def test_missing_leg_r_is_derived_from_the_leg_exit_price():
    trade = _trade([{"fraction": 0.5, "exit_price": 110.0},
                    {"fraction": 0.5, "exit_price": 115.0}], exit_price=115.0)
    assert metrics._blended_r_raw(trade) == pytest.approx(2.5)
    assert metrics.r_multiple(trade) == 2.5


def test_bearish_legs_are_signed_in_the_trades_favour():
    trade = _trade([{"fraction": 0.5, "exit_price": 90.0},
                    {"fraction": 0.5, "exit_price": 102.0}],
                   direction="bearish", stop=105.0, exit_price=102.0)
    # (100-90)/5 = +2 on half, (100-102)/5 = -0.4 on half -> 0.8
    assert metrics.r_multiple(trade) == 0.8


@pytest.mark.parametrize("trade", [
    {"direction": "bullish", "entry": None, "stop_loss": 95.0, "exit_price": 110.0},
    {"direction": "bullish", "entry": 100.0, "stop_loss": None, "exit_price": 110.0},
    {"direction": "sideways", "entry": 100.0, "stop_loss": 95.0, "exit_price": 110.0},
    {"direction": "bullish", "entry": 100.0, "stop_loss": 100.0, "exit_price": 110.0},
    {"direction": "bullish", "entry": 100.0, "stop_loss": 95.0, "exit_price": None},
    {"direction": "bullish", "entry": 100.0, "stop_loss": 95.0,
     "legs": [{"fraction": 0.5, "r": None, "exit_price": None}]},
])
def test_uncomputable_trades_stay_none(trade):
    assert metrics._blended_r_raw(trade) is None
    assert metrics.r_multiple(trade) is None


# --- banked_contribution_r ---------------------------------------------------

def test_banked_contribution_sums_the_realized_legs():
    assert metrics.banked_contribution_r([TP1_LEG]) == pytest.approx(1.0)
    assert metrics.banked_contribution_r(
        [TP1_LEG, {"fraction": 0.5, "r": 3.0}]) == pytest.approx(2.5)


@pytest.mark.parametrize("legs", [None, [], [TP1_LEG, {"fraction": 0.5}]])
def test_banked_contribution_is_none_without_legs_or_with_a_missing_r(legs):
    assert metrics.banked_contribution_r(legs) is None


# --- open_trade_r ------------------------------------------------------------

def test_open_partial_blends_banked_and_live_runner():
    trade = _trade([TP1_LEG])
    # 1.0 banked + 0.5 x (113 - 100) / 5 = 1.0 + 1.3 = 2.3
    assert metrics.open_trade_r(trade, 113.0) == pytest.approx(2.3)


def test_open_trade_without_legs_is_the_whole_position_live_r():
    assert metrics.open_trade_r(_trade(), 103.0) == pytest.approx(0.6)


def test_open_bearish_partial_is_signed_per_direction():
    trade = _trade([{"fraction": 0.5, "exit_price": 90.0, "r": 2.0}],
                   direction="bearish", stop=105.0)
    # 1.0 + 0.5 x (100 - 97) / 5 = 1.3
    assert metrics.open_trade_r(trade, 97.0) == pytest.approx(1.3)


@pytest.mark.parametrize("quote", [None, math.nan, math.inf])
def test_open_trade_r_is_none_without_a_finite_quote(quote):
    assert metrics.open_trade_r(_trade([TP1_LEG]), quote) is None


def test_open_trade_r_is_none_without_a_risk_basis():
    assert metrics.open_trade_r(_trade([TP1_LEG], stop=100.0), 113.0) is None


def test_open_trade_r_is_none_when_a_banked_leg_has_no_r():
    assert metrics.open_trade_r(_trade([{"fraction": 0.5, "exit_price": 110.0}]), 113.0) is None


# --- performance.closed_r_multiple delegates ---------------------------------

def test_closed_r_multiple_is_metrics_r_multiple_rounded():
    legged = _trade([TP1_LEG, {"fraction": 0.5, "exit_price": 115.0, "r": 3.0}],
                    exit_price=115.0)
    single = _trade(exit_price=ODD_PRICE)
    assert closed_r_multiple(legged) == metrics.r_multiple(legged) == 2.5
    assert closed_r_multiple(single) == round(metrics.r_multiple(single), 2) == 0.27


def test_closed_r_multiple_passes_none_through():
    assert closed_r_multiple(_trade()) is None


def test_closed_r_multiple_no_longer_guesses_a_direction():
    """The old private copy treated any non-bullish direction as bearish;
    the one shared R returns None for a malformed direction (D1)."""
    assert closed_r_multiple(_trade(exit_price=110.0, direction=None)) is None
