import pandas as pd
import pytest

from swingbot.core.market.level_strength import find_touches


def _bars(rows):
    """rows: list of (low, high, close)."""
    return pd.DataFrame({
        "Open": [r[2] for r in rows],
        "Low": [r[0] for r in rows],
        "High": [r[1] for r in rows],
        "Close": [r[2] for r in rows],
        "Volume": [1_000_000] * len(rows),
    })


def test_bar_entering_the_band_is_a_touch():
    df = _bars([(99.6, 101.0, 100.5), (105.0, 106.0, 105.5)])
    assert find_touches(df, level=100.0, tolerance_pct=0.5) == [0]


def test_bar_outside_the_band_is_not_a_touch():
    df = _bars([(105.0, 106.0, 105.5)])
    assert find_touches(df, level=100.0, tolerance_pct=0.5) == []


def test_band_is_a_percentage_of_the_level_not_absolute():
    """0.5% of 100 is 0.50; 0.5% of 1000 is 5.00. A fixed absolute band would
    make every level on a high-priced ticker untouchable."""
    df = _bars([(995.0, 1002.0, 1000.0)])
    assert find_touches(df, level=1000.0, tolerance_pct=0.5) == [0]


def test_multiple_touches_are_all_returned_in_order():
    df = _bars([(99.8, 100.2, 100.0), (110.0, 111.0, 110.5), (99.9, 100.4, 100.1)])
    assert find_touches(df, level=100.0, tolerance_pct=0.5) == [0, 2]


def test_zero_or_negative_level_returns_no_touches():
    assert find_touches(_bars([(99.8, 100.2, 100.0)]), level=0.0) == []


def test_empty_frame_returns_no_touches():
    assert find_touches(_bars([]), level=100.0) == []
