"""v140 high52w: close >= 0.95 x 252-bar high, SMA50 > SMA200, first true
bar after >= 20 consecutive computable false bars (frozen reading F3)."""
import numpy as np

from swingbot.core.backtesting.screen.ideas import high52w
from tests.backtesting.screen.helpers import assert_prefix_stable, frame, random_walk


def _fixture(dip_bars=25):
    """Bars 0..329 rise 0.5 a bar (close 264.5, high 265.5 at 329), then a
    dip at 240 (< 0.95 x 265.5 = 252.2), then 260 (>= 252.2) to the end."""
    closes = np.r_[100 + 0.5 * np.arange(330), np.full(dip_bars, 240.0),
                   np.full(400 - 330 - dip_bars, 260.0)]
    return frame(closes)


def _event_positions(df):
    return np.flatnonzero(high52w.events(df).to_numpy()).tolist()


def test_fires_once_on_the_first_bar_back_near_the_high():
    assert _event_positions(_fixture()) == [355]


def test_does_not_fire_after_only_nineteen_false_bars():
    assert _event_positions(_fixture(dip_bars=19)) == []


def test_warm_up_bars_never_count_as_false():
    rise = frame(100 + 0.5 * np.arange(300))     # true from the first computable bar
    assert _event_positions(rise) == []


def test_series_shape():
    out = high52w.events(_fixture())
    assert out.dtype == bool and out.index.equals(_fixture().index)
    assert out.name == "high52w"


def test_reads_no_later_bar_on_the_fixture():
    assert_prefix_stable(high52w.events, _fixture(), [300, 340, 354, 355, 356, 399])


def test_reads_no_later_bar_on_a_random_walk():
    assert_prefix_stable(high52w.events, random_walk(700), [260, 400, 550, 699])
