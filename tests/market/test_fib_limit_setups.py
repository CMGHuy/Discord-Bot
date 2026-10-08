"""v131: the Fibonacci Limit arming rule (entry_filters.fibonacci_limit_setups)."""
import numpy as np
import pandas as pd
import pytest

from swingbot.core.market import entry_filters as ef
from tests.helpers import make_ohlcv
from tests.market.test_fib_sr_confluence import _trending_frame

HZ = "4w"                                   # fib_lookback 42: the whole leg stays in the window
PAD = [(100.8, 101.0, 100.6, 100.8)] * 50
IMPULSE = [(100.2, 100.8, 100.0, 100.6), (102.0, 103.5, 101.8, 103.0),
           (105.0, 106.5, 104.8, 106.0), (107.5, 109.0, 107.3, 108.5),
           (109.0, 110.0, 108.8, 109.6)]    # swing low 100.0 at bar 50, swing high 110.0 at bar 54
HIGH_BAR = len(PAD) + len(IMPULSE) - 1      # 54
CELL = {"L": 0.618, "N": 3}


def _pull(closes):
    """Pullback bars that never trade below the 0.618 limit (103.82) or above 110."""
    return [(c + 0.3, c + 0.5, c - 0.2, c) for c in closes]


def _open_gates(df):
    on = pd.Series(True, index=df.index)
    return {"bull_regime": on, "trend50_bull": on, "atr_floor": on, "atr_calm": on}


@pytest.fixture
def gates_open(monkeypatch):
    """Hand-built frames are too short for MA200; the gates get their own test."""
    monkeypatch.setattr(ef, "compute_shared_gates", _open_gates)


def _arms(bars, params=CELL):
    frame = make_ohlcv(bars, start="2015-01-02")
    return [int(i) for i in np.nonzero(ef.fibonacci_limit_setups(frame, HZ, params)["arm"].to_numpy())[0]]


def test_arms_at_a_0_3_retracement_three_bars_after_the_high(gates_open):
    bars = PAD + IMPULSE + _pull([109.2, 108.6, 107.0])
    frame = make_ohlcv(bars, start="2015-01-02")
    setups = ef.fibonacci_limit_setups(frame, HZ, CELL)
    assert _arms(bars) == [HIGH_BAR + 3]
    row = setups.iloc[HIGH_BAR + 3]
    assert (row["swing_high"], row["swing_low"], row["swing_high_idx"]) == (110.0, 100.0, HIGH_BAR)
    assert row["limit_price"] == pytest.approx(110.0 - 0.618 * 10.0)


@pytest.mark.parametrize("closes", [
    [109.2, 108.6, 103.5, 103.5, 103.5],    # retracement 0.65 >= L
    [109.2, 108.6, 108.0, 108.0, 108.0],    # retracement 0.20 < 0.236
    [109.2, 108.6, 107.7, 107.7, 107.7],    # retracement 0.23 < 0.236
])
def test_does_not_arm_outside_the_zone(gates_open, closes):
    assert _arms(PAD + IMPULSE + _pull(closes)) == []


def test_arms_just_inside_the_shallow_edge(gates_open):
    assert _arms(PAD + IMPULSE + _pull([109.2, 108.6, 107.6])) == [HIGH_BAR + 3]


def test_does_not_arm_while_the_swing_high_is_under_three_bars_old(gates_open):
    assert _arms(PAD + IMPULSE + _pull([107.0, 107.0])) == []
    assert _arms(PAD + IMPULSE + _pull([107.0, 107.0, 107.0])) == [HIGH_BAR + 3]


def test_the_shallower_limit_shrinks_the_zone(gates_open):
    bars = PAD + IMPULSE + _pull([109.2, 108.6, 104.5])        # retracement 0.55
    assert _arms(bars, {"L": 0.618, "N": 3}) == [HIGH_BAR + 3]
    assert _arms(bars, {"L": 0.5, "N": 3}) == []


def test_does_not_re_arm_the_same_leg_after_the_order_expires(gates_open):
    bars = PAD + IMPULSE + _pull([109.2, 108.6, 107.0]) + _pull([107.0] * 8)
    assert _arms(bars) == [HIGH_BAR + 3]


def test_no_second_arm_while_an_order_is_live(gates_open):
    """A new leg whose high stays under the old one cannot appear here, so pin
    the order book directly: the leg changes but the first order is live."""
    candidate = np.array([True, True, True, True])
    leg = np.array([10.0, 11.0, 12.0, 13.0])
    low = np.full(4, 105.0)
    high = np.full(4, 108.0)
    limit = np.full(4, 104.0)
    cancel = np.full(4, 110.0)
    # Armed at 0 with life 2: live for bars 1 and 2, gone after bar 2's close,
    # so bar 2's close may arm again; that order is live through bar 4.
    assert list(ef._arm_orders(candidate, leg, low, high, limit, cancel, 2)) == [
        True, False, True, False]


@pytest.mark.parametrize("low, high, expect_free", [
    (103.9, 108.0, True),     # Low < limit: filled, no longer a resting order
    (104.0, 108.0, False),    # an exact touch does not fill
    (105.0, 110.1, True),     # High > swing high: cancelled
    (105.0, 110.0, False),    # an equal high does not cancel
])
def test_order_book_fill_and_cancel_edges(low, high, expect_free):
    order = (0, 104.0, 110.0)
    after = ef._order_after_bar(order, 1, low, high, 5)
    assert (after is None) is expect_free


def test_re_arms_on_a_new_leg(gates_open):
    leg_one = PAD + IMPULSE + _pull([109.2, 108.6, 107.0]) + _pull([107.0] * 8)
    new_high = [(110.5, 111.0, 110.2, 110.8)]
    leg_two = new_high + _pull([110.2, 109.5, 107.7]) + _pull([107.7] * 2)
    second_high = len(leg_one)
    assert _arms(leg_one + leg_two) == [HIGH_BAR + 3, second_high + 3]
    frame = make_ohlcv(leg_one + leg_two, start="2015-01-02")
    row = ef.fibonacci_limit_setups(frame, HZ, CELL).iloc[second_high + 3]
    assert (row["swing_high"], row["swing_low"], row["swing_high_idx"]) == (111.0, 100.0, second_high)


def test_gates_block_the_arm_on_real_indicators():
    frame = _trending_frame(400, 0.06, seed=2)
    setups = ef.fibonacci_limit_setups(frame, "2w")
    gates = ef.compute_shared_gates(frame)
    allowed = gates["bull_regime"] & gates["trend50_bull"] & gates["atr_floor"] & gates["atr_calm"]
    assert setups["arm"].any(), "fixture must arm for this to mean anything"
    assert not (setups["arm"] & ~allowed).any()


@pytest.mark.parametrize("horizon", ["2w", "4w"])
def test_truncation_invariance_every_cut(horizon):
    """No lookahead: row t of the full-frame result equals the last row of the
    result on df.iloc[:t+1], for every t."""
    frame = _trending_frame(300, 0.06, seed=2)
    full = ef.fibonacci_limit_setups(frame, horizon)
    for t in range(len(frame)):
        cut = ef.fibonacci_limit_setups(frame.iloc[:t + 1], horizon).iloc[-1]
        pd.testing.assert_series_equal(cut, full.iloc[t], check_names=False)


@pytest.mark.parametrize("horizon", ["2w", "4w"])
def test_price_and_cancel_functions_match_the_setup_frame(horizon):
    frame = _trending_frame(300, 0.06, seed=2)
    setups = ef.fibonacci_limit_setups(frame, horizon)
    for t in np.nonzero(setups["arm"].to_numpy())[0]:
        t = int(t)
        assert ef.fib_limit_price_at(frame, t, horizon, "bullish") == pytest.approx(
            setups["limit_price"].iloc[t])
        assert ef.fib_limit_cancel_at(frame, t, horizon, "bullish") == setups["swing_high"].iloc[t]
        # truncation: the frozen prices read bars <= t only
        assert ef.fib_limit_price_at(frame.iloc[:t + 1], t, horizon, "bullish") == pytest.approx(
            setups["limit_price"].iloc[t])


def test_price_function_is_bullish_only_and_refuses_a_short_window():
    frame = _trending_frame(300, 0.06, seed=2)
    assert ef.fib_limit_price_at(frame, 250, "2w", "bearish") is None
    assert ef.fib_limit_cancel_at(frame, 250, "2w", "bearish") is None
    assert ef.fib_limit_price_at(frame, 5, "2w", "bullish") is None
