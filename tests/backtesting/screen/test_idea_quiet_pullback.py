"""quiet_pullback: the uptrend RSI(2) < 10 trigger with no gap or volume spike on bars t-2..t."""
import numpy as np
import pytest

from swingbot.core.backtesting.screen import indicators
from swingbot.core.backtesting.screen.ideas import quiet_pullback, uptrend_pullback
from tests.backtesting.screen.helpers import assert_prefix_stable, frame, random_walk


N = 260


def _fixture(gap249=0.0, volumes=None):
    """The uptrend_pullback fixture (rise to bar 247, two -2 bars, RSI2 7.69
    at bar 249), each bar opening at the prior close: no gaps, volume 1e6.
    ``gap249`` moves bar 249's open off the prior close."""
    closes = np.r_[100 + 0.5 * np.arange(248), 221.5, 219.5,
                   220 + 0.5 * np.arange(10)]
    opens = np.r_[closes[0], closes[:-1]]
    opens[249] += gap249
    highs = np.maximum(opens, closes) + 1.0
    lows = np.minimum(opens, closes) - 1.0
    return frame(closes, opens=opens, highs=highs, lows=lows, volumes=volumes)


def _positions(df):
    return np.flatnonzero(quiet_pullback.events(df).to_numpy()).tolist()


def _prior_atr_at_249():
    return float(indicators.atr(_fixture(), 14).shift(1).iloc[249])


def test_fires_where_the_parent_fires_when_quiet():
    df = _fixture()
    assert _positions(df) == [249]
    assert np.flatnonzero(uptrend_pullback.events(df).to_numpy()).tolist() == [249]
    assert quiet_pullback.events(df).name == "quiet_pullback"


@pytest.mark.parametrize("bar", [247, 248, 249])
def test_a_volume_spike_on_any_of_the_last_three_bars_vetoes(bar):
    volumes = np.full(N, 1e6)
    volumes[bar] = 2.01e6
    assert _positions(_fixture(volumes=volumes)) == []


def test_a_spike_four_bars_back_does_not_veto():
    volumes = np.full(N, 1e6)
    volumes[246] = 5e6
    assert _positions(_fixture(volumes=volumes)) == [249]


@pytest.mark.parametrize("atr_mult, expected", [(-1.05, []), (1.05, []), (-0.95, [249])])
def test_a_gap_beyond_one_atr_either_way_vetoes(atr_mult, expected):
    gap = atr_mult * _prior_atr_at_249()
    assert _positions(_fixture(gap249=gap)) == expected


def test_reads_no_later_bar_on_the_fixture():
    assert _positions(_fixture()) == [249]   # non-vacuous
    assert_prefix_stable(quiet_pullback.events, _fixture(), [200, 247, 248, 249, 250, 257])


def test_reads_no_later_bar_on_a_random_walk():
    assert_prefix_stable(quiet_pullback.events, random_walk(500), [210, 300, 499])
