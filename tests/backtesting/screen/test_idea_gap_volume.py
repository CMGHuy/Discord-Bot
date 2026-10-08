"""v140 gap_volume: open >= prior close + 1.0 x prior ATR14, volume >= 2 x
the 50-bar mean ending the prior bar, close >= open."""
import numpy as np
import pytest

from swingbot.core.backtesting.screen.ideas import gap_volume
from tests.backtesting.screen.helpers import assert_prefix_stable, frame, random_walk


def _fixture(open70=103.0, vol70=3e6):
    """80 flat bars (O = C = 100, H 101, L 99, volume 1e6: ATR14 = 2).
    Bar 70 gaps and holds on volume. Bar 75 gaps on volume but closes below
    its open. Bar 78 gaps and holds on too little volume."""
    n = 80
    o, h = np.full(n, 100.0), np.full(n, 101.0)
    l, c, v = np.full(n, 99.0), np.full(n, 100.0), np.full(n, 1e6)
    for i, bar in {70: (open70, 105.0, 101.5, 104.0, vol70),
                   75: (110.0, 111.0, 107.0, 108.0, 4e6),
                   78: (110.0, 112.0, 109.0, 111.0, 1.5e6)}.items():
        o[i], h[i], l[i], c[i], v[i] = bar
    return frame(c, opens=o, highs=h, lows=l, volumes=v)


def _positions(df):
    return np.flatnonzero(gap_volume.events(df).to_numpy()).tolist()


def test_fires_only_on_the_gap_that_holds_on_volume():
    assert _positions(_fixture()) == [70]
    assert gap_volume.events(_fixture()).name == "gap_volume"


@pytest.mark.parametrize("open70, vol70, expected", [
    (102.01, 3e6, [70]),      # open just above prior close + 1.0 x ATR (100 + 2)
    (101.99, 3e6, []),        # just below (ATR is a float: no exact-equality probe)
    (103.0, 2e6, [70]),       # volume exactly 2 x the 50-bar mean (1e6): inclusive
    (103.0, 1.99e6, []),
])
def test_thresholds_sit_where_the_spec_puts_them(open70, vol70, expected):
    assert _positions(_fixture(open70, vol70)) == expected


def test_reads_no_later_bar_on_the_fixture():
    assert _positions(_fixture()) == [70]  # non-vacuous: an event is compared
    assert_prefix_stable(gap_volume.events, _fixture(), [60, 69, 70, 71, 75, 79])


def test_reads_no_later_bar_on_a_random_walk():
    assert_prefix_stable(gap_volume.events, random_walk(400), [60, 200, 399])
