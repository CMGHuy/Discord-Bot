"""v140 uptrend_pullback: close > SMA200 and Wilder RSI(2) < 10."""
import numpy as np

from swingbot.core.backtesting.screen.ideas import uptrend_pullback
from tests.backtesting.screen.helpers import assert_prefix_stable, frame, random_walk


def _fixture():
    """Rise 0.5 a bar to 223.5 at bar 247, two -2 bars (RSI2 20.0 then 7.69),
    then +0.5 bars again. RSI2 at 250 is 29.4."""
    closes = np.r_[100 + 0.5 * np.arange(248), 221.5, 219.5,
                   220 + 0.5 * np.arange(10)]
    return frame(closes)


def test_fires_on_the_second_down_bar_only():
    out = uptrend_pullback.events(_fixture())
    assert np.flatnonzero(out.to_numpy()).tolist() == [249]
    assert out.name == "uptrend_pullback"


def test_never_fires_below_the_200_bar_average():
    falling = frame(300 - 0.5 * np.arange(260))   # RSI2 is 0, close < SMA200
    assert not uptrend_pullback.events(falling).any()


def test_reads_no_later_bar_on_the_fixture():
    assert uptrend_pullback.events(_fixture()).any()   # non-vacuous
    assert_prefix_stable(uptrend_pullback.events, _fixture(), [200, 247, 248, 249, 250, 259])


def test_reads_no_later_bar_on_a_random_walk():
    assert_prefix_stable(uptrend_pullback.events, random_walk(500), [210, 300, 499])
