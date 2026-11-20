import numpy as np
import pandas as pd
import pytest

from tests.conftest import make_ohlcv
from swingbot.core.edge.frictions import (BORROW_RATE_ANNUAL, NET_R_SIDES, apply_frictions,
                                          borrow_r, commission_r, net_r_legs)


def test_slippage_direction_golden():
    assert apply_frictions(100.0, "buy", 5) == pytest.approx(100.05)
    assert apply_frictions(100.0, "sell", 5) == pytest.approx(99.95)
    assert apply_frictions(100.0, "buy", 0) == 100.0


def test_commission_r_golden():
    # $1 per side, $100 risk basis -> 2 x 1/100 = 0.02R round trip
    assert commission_r(risk_dollars=100.0, commission=1.0) == pytest.approx(0.02)


def test_backtest_frictions_reduce_r(monkeypatch):
    import swingbot.core.backtesting.backtest as bt
    df = make_ohlcv(np.full(80, 100.0), spread_pct=1.0)
    bull = pd.Series(False, index=df.index); bull.iloc[40] = True
    bear = pd.Series(False, index=df.index)
    monkeypatch.setattr(bt, "_vectorized_entries", lambda *a, **k: (bull, bear))
    clean = bt.run_backtest("TEST", df, "EMA Crossover", "2w", frictions=False)
    real = bt.run_backtest("TEST", df, "EMA Crossover", "2w", frictions=True)
    assert clean.trades and real.trades
    # same bars, worse arithmetic: friction expectancy strictly lower
    assert real.expectancy_r < clean.expectancy_r


def test_frictions_off_is_bit_identical_to_before(monkeypatch):
    import swingbot.core.backtesting.backtest as bt
    df = make_ohlcv(np.full(80, 100.0), spread_pct=1.0)
    bull = pd.Series(False, index=df.index); bull.iloc[40] = True
    monkeypatch.setattr(bt, "_vectorized_entries",
                        lambda *a, **k: (bull, pd.Series(False, index=df.index)))
    s = bt.run_backtest("TEST", df, "EMA Crossover", "2w", frictions=False)
    t = s.trades[0]
    assert t.entry == 100.0  # unslipped fill preserved when off


def test_borrow_rate_is_half_a_percent_a_year():
    assert BORROW_RATE_ANNUAL == 0.005


def test_borrow_r_golden_value():
    # $100 short for 73 calendar days at 0.5%/yr = $0.10; over $2 risk = 0.05R
    assert borrow_r(100.0, 2.0, 73) == pytest.approx(0.05, rel=1e-12)


def test_borrow_r_is_the_spec_expression_bit_for_bit():
    entry, risk, days = 87.375, 3.125, 11
    assert borrow_r(entry, risk, days) == entry * 0.005 / 365.0 * days / risk


def test_borrow_is_zero_for_a_same_day_exit():
    assert borrow_r(100.0, 2.0, 0) == 0.0


def test_borrow_counts_calendar_days_over_a_weekend():
    # Friday entry, Monday exit: three calendar days, not one session
    friday, monday = pd.Timestamp("2015-03-06"), pd.Timestamp("2015-03-09")
    days = (monday - friday).days
    assert days == 3
    assert borrow_r(100.0, 2.0, days) == pytest.approx(3 * borrow_r(100.0, 2.0, 1), rel=1e-12)


def test_borrow_r_is_vectorised_elementwise():
    entry = np.array([100.0, 50.0, 80.0])
    risk = np.array([2.0, 1.0, 4.0])
    days = np.array([0.0, 7.0, 30.0])
    out = borrow_r(entry, risk, days)
    assert isinstance(out, np.ndarray) and out.shape == (3,)
    assert out.tolist() == [borrow_r(e, r, d) for e, r, d in zip(entry, risk, days)]


def test_borrow_r_grows_with_price_and_time_and_shrinks_with_risk():
    base = borrow_r(100.0, 2.0, 10)
    assert borrow_r(200.0, 2.0, 10) == pytest.approx(2 * base)
    assert borrow_r(100.0, 2.0, 20) == pytest.approx(2 * base)
    assert borrow_r(100.0, 4.0, 10) == pytest.approx(base / 2)


# --- v238: net_r_legs, the one net-R function for arm rows ----------------------------

from swingbot import config  # noqa: E402
from swingbot.core.backtesting.screen import sides  # noqa: E402


@pytest.fixture
def costs(monkeypatch):
    """Pin the frictions defaults: 5 bps a side, $1 a side on a $100 basis = 0.02R."""
    monkeypatch.setattr(config, "SLIPPAGE_BPS", 5.0, raising=False)
    monkeypatch.setattr(config, "COMMISSION_PER_TRADE", 1.0, raising=False)
    monkeypatch.setattr(config, "COMMISSION_RISK_BASIS", 100.0, raising=False)


def _leg(price, fraction=1.0):
    return {"fraction": fraction, "exit_price": price, "r": 99.0, "reason": "tp1"}


def test_net_r_legs_long_single_leg_is_the_hand_computed_value(costs):
    # entry 100 slipped to 100.05, exit 106 slipped to 105.947, planned risk 3, commission 0.02
    expected = (106.0 * (1 - 0.0005) - 100.0 * (1 + 0.0005)) / 3.0 - 0.02
    assert net_r_legs(100.0, 97.0, "long", [_leg(106.0)], days=4) == pytest.approx(expected, abs=1e-12)


def test_net_r_legs_ignores_the_recorded_leg_r(costs):
    leg = _leg(106.0)
    other = dict(leg, r=-5.0)
    assert net_r_legs(100.0, 97.0, "long", [leg], days=4) == net_r_legs(100.0, 97.0, "long", [other], days=4)


@pytest.mark.parametrize("direction,stop,exit_price,days", [
    ("long", 97.0, 106.0, 4), ("long", 97.0, 95.0, 9),
    ("short", 103.0, 94.0, 10), ("short", 103.0, 104.5, 3),
])
def test_net_r_legs_matches_the_screen_net_r_on_a_single_leg(costs, direction, stop, exit_price, days):
    ours = net_r_legs(100.0, stop, direction, [_leg(exit_price)], days=days)
    screen = sides.net_r(100.0, exit_price, abs(100.0 - stop), direction=direction, days=days)
    assert ours == pytest.approx(float(screen), abs=1e-12)


def test_net_r_legs_risk_is_planned_not_re_based_on_the_fill(costs):
    got = net_r_legs(100.0, 97.0, "long", [_leg(106.0)], days=0)
    re_based_risk = 100.05 - 97.0
    re_based = (106.0 * (1 - 0.0005) - 100.05) / re_based_risk - 0.02
    assert got != pytest.approx(re_based, abs=1e-9)


def test_net_r_legs_two_legs_are_the_fraction_weighted_mean_of_one_leg_results(costs):
    for direction, stop, tp1, runner in (("long", 97.0, 103.0, 109.0), ("short", 103.0, 97.0, 91.0)):
        both = net_r_legs(100.0, stop, direction, [_leg(tp1, 0.5), _leg(runner, 0.5)], days=12)
        one = net_r_legs(100.0, stop, direction, [_leg(tp1)], days=12)
        two = net_r_legs(100.0, stop, direction, [_leg(runner)], days=12)
        assert both == pytest.approx(0.5 * one + 0.5 * two, abs=1e-12)


def test_net_r_legs_commission_comes_off_once_not_per_leg(costs):
    flat = [_leg(100.0, 0.25), _leg(100.0, 0.75)]
    # exit at the entry price: only the two slippages and one commission remain
    expected = (100.0 * (1 - 0.0005) - 100.0 * (1 + 0.0005)) / 3.0 - 0.02
    assert net_r_legs(100.0, 97.0, "long", flat, days=5) == pytest.approx(expected, abs=1e-12)


def test_net_r_legs_long_never_reads_days(costs):
    a = net_r_legs(100.0, 97.0, "long", [_leg(106.0)], days=0)
    b = net_r_legs(100.0, 97.0, "long", [_leg(106.0)], days=365)
    assert a == b


def test_net_r_legs_short_pays_borrow_over_calendar_days(costs):
    same_day = net_r_legs(100.0, 103.0, "short", [_leg(94.0)], days=0)
    held = net_r_legs(100.0, 103.0, "short", [_leg(94.0)], days=30)
    assert same_day - held == pytest.approx(borrow_r(100.0, 3.0, 30), abs=1e-12)
    assert borrow_r(100.0, 3.0, 30) == pytest.approx(100.0 * BORROW_RATE_ANNUAL / 365.0 * 30 / 3.0)


@pytest.mark.parametrize("alias,side", [("bullish", "long"), ("bearish", "short")])
def test_net_r_legs_takes_the_arm_direction_spellings(costs, alias, side):
    stop = 97.0 if side == "long" else 103.0
    assert (net_r_legs(100.0, stop, alias, [_leg(101.0)], days=7)
            == net_r_legs(100.0, stop, side, [_leg(101.0)], days=7))


def test_net_r_sides_maps_every_spelling():
    assert NET_R_SIDES == {"bullish": "long", "long": "long", "bearish": "short", "short": "short"}


def test_net_r_legs_returns_a_plain_float(costs):
    assert type(net_r_legs(100.0, 103.0, "short", [_leg(94.0)], days=3)) is float


@pytest.mark.parametrize("entry,stop,direction,legs,match", [
    (100.0, 97.0, "long", [], "leg"),
    (100.0, 100.0, "long", [_leg(106.0)], "stop distance"),
    (100.0, 97.0, "sideways", [_leg(106.0)], "direction"),
    (100.0, 97.0, "long", [_leg(106.0, 0.5), _leg(104.0, 0.4)], "fractions"),
    (100.0, 97.0, "long", [_leg(106.0, 0.6), _leg(104.0, 0.6)], "fractions"),
])
def test_net_r_legs_refuses_malformed_input(costs, entry, stop, direction, legs, match):
    with pytest.raises(ValueError, match=match):
        net_r_legs(entry, stop, direction, legs, days=1)


def test_net_r_legs_accepts_fractions_within_rounding(costs):
    legs = [_leg(103.0, 0.1), _leg(103.0, 0.2), _leg(103.0, 0.7)]     # 0.1+0.2+0.7 != 1.0 exactly
    assert net_r_legs(100.0, 97.0, "long", legs, days=2) == pytest.approx(
        net_r_legs(100.0, 97.0, "long", [_leg(103.0)], days=2), abs=1e-12)
