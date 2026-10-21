"""sweep_reclaim_bos: sweep an aged swing low, reclaim it, then close above the swing high."""
import numpy as np
import pytest

from swingbot.core.backtesting.screen.ideas import sweep_reclaim_bos
from tests.backtesting.screen.helpers import assert_prefix_stable, frame, random_walk


def _fixture(closes_at=None, lows_at=None, n=60):
    """Flat bars (C 100, H 101, L 99). Bar 20 is a 110 swing high, bar 30 a
    90 swing low; bar 40 sweeps to 88 and closes at 100; bar 45 closes 111."""
    closes = np.full(n, 100.0)
    closes[45] = 111.0
    for bar, value in (closes_at or {}).items():
        closes[bar] = value
    highs, lows = closes + 1.0, closes - 1.0
    highs[20], lows[30], lows[40] = 110.0, 90.0, 88.0
    for bar, value in (lows_at or {}).items():
        lows[bar] = value
    return frame(closes, highs=highs, lows=lows)


def _positions(df):
    return np.flatnonzero(sweep_reclaim_bos.events(df).to_numpy()).tolist()


def test_fires_on_the_close_above_the_swing_high_after_the_reclaim():
    assert _positions(_fixture()) == [45]
    assert sweep_reclaim_bos.events(_fixture()).name == "sweep_reclaim_bos"


def test_no_sweep_no_event():
    assert _positions(_fixture(lows_at={40: 99.0})) == []


@pytest.mark.parametrize("unreclaimed, expected", [
    ((), [45]), ((40,), [45]), ((40, 41), [45]), ((40, 41, 42), [])])
def test_the_reclaim_must_come_within_two_bars_of_the_sweep(unreclaimed, expected):
    closes = {bar: 89.0 for bar in unreclaimed}
    lows = {bar: 88.0 for bar in unreclaimed}
    assert _positions(_fixture(closes_at=closes, lows_at=lows)) == expected


@pytest.mark.parametrize("bos_bar, expected", [(50, [50]), (51, [])])
def test_the_break_must_come_within_ten_bars_of_the_sweep(bos_bar, expected):
    df = _fixture(closes_at={45: 100.0, bos_bar: 111.0})
    df.loc[df.index[bos_bar], "Low"] = 110.0
    assert _positions(df) == expected


def test_the_close_must_end_above_the_swing_high():
    assert _positions(_fixture(closes_at={45: 110.0})) == []


def test_a_low_under_the_sweep_low_after_the_reclaim_cancels():
    still = {43: 89.0, 44: 89.0, 45: 89.0, 46: 111.0}
    held = _fixture(closes_at=still, lows_at={43: 88.5, 44: 88.5, 45: 88.5}, n=60)
    assert _positions(held) == [46]
    # 87 undercuts the 88 sweep low: cancelled, and the 90 low never re-arms.
    broken = _fixture(closes_at=still, lows_at={43: 87.0, 44: 88.5, 45: 88.5}, n=60)
    assert _positions(broken) == []


def test_reads_no_later_bar_on_the_fixture():
    assert _positions(_fixture()) == [45]   # non-vacuous
    assert_prefix_stable(sweep_reclaim_bos.events, _fixture(), [30, 33, 40, 44, 45, 59])


def test_reads_no_later_bar_on_a_random_walk():
    assert sweep_reclaim_bos.events(random_walk(500)).any()
    assert_prefix_stable(sweep_reclaim_bos.events, random_walk(500), [30, 250, 499])
