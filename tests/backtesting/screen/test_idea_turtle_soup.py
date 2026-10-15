"""turtle_soup: low < the prior 20-bar low, that low >= 4 bars old, close back above it."""
import numpy as np
import pytest

from swingbot.core.backtesting.screen.ideas import turtle_soup
from tests.backtesting.screen.helpers import assert_prefix_stable, frame, random_walk


def _fixture(low25=95.0, low35=94.0, close35=100.0):
    """40 flat bars (C 100, L 99). Bar 25 sets a 95 low; bar 35 breaks it
    and closes at ``close35``."""
    closes = np.full(40, 100.0)
    lows = closes - 1.0
    lows[25], lows[35] = low25, low35
    closes[35] = close35
    return frame(closes, lows=lows)


def _positions(df):
    return np.flatnonzero(turtle_soup.events(df).to_numpy()).tolist()


def test_fires_on_the_reclaim_of_an_aged_low_only():
    # Bar 25 also breaks the channel, but the 99 low it breaks is one bar old.
    assert _positions(_fixture()) == [35]
    assert turtle_soup.events(_fixture()).name == "turtle_soup"


@pytest.mark.parametrize("close35, expected", [(95.01, [35]), (95.0, []), (94.5, [])])
def test_the_close_must_end_above_the_broken_low(close35, expected):
    assert _positions(_fixture(close35=close35)) == expected


def test_a_low_set_three_bars_back_is_too_young():
    closes = np.full(40, 100.0)
    lows = closes - 1.0
    lows[32], lows[35] = 95.0, 94.0          # age 3 at bar 35
    assert 35 not in _positions(frame(closes, lows=lows))
    lows[32], lows[31] = 99.0, 95.0          # age 4 at bar 35
    assert 35 in _positions(frame(closes, lows=lows))


def test_age_counts_to_the_latest_bar_holding_the_low():
    closes = np.full(40, 100.0)
    lows = closes - 1.0
    lows[20], lows[33], lows[35] = 95.0, 95.0, 94.0   # 95 retested 2 bars back
    assert 35 not in _positions(frame(closes, lows=lows))


def test_needs_a_full_channel_of_history():
    closes = np.full(15, 100.0)
    lows = closes - 1.0
    lows[2], lows[12] = 95.0, 94.0
    assert _positions(frame(closes, lows=lows)) == []


def test_reads_no_later_bar_on_the_fixture():
    assert _positions(_fixture()) == [35]   # non-vacuous
    assert_prefix_stable(turtle_soup.events, _fixture(), [20, 25, 34, 35, 36, 39])


def test_reads_no_later_bar_on_a_random_walk():
    assert turtle_soup.events(random_walk(500)).any()
    assert_prefix_stable(turtle_soup.events, random_walk(500), [30, 250, 499])
