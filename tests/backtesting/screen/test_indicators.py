"""v140 screen indicators: hand-computed values and the truncation guard."""
import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting.screen import indicators
from tests.backtesting.screen.helpers import assert_prefix_stable, frame, random_walk


def _values(series):
    return [None if np.isnan(v) else round(float(v), 6) for v in series]


def test_wilder_mean_seeds_with_the_simple_mean_then_smooths():
    out = indicators.wilder_mean(pd.Series([1.0, 2.0, 3.0, 4.0, 5.0]), 2)
    assert _values(out) == [None, 1.5, 2.25, 3.125, 4.0625]


def test_wilder_mean_skips_leading_nans():
    out = indicators.wilder_mean(pd.Series([np.nan, 2.0, 4.0, 6.0]), 2)
    assert _values(out) == [None, None, 3.0, 4.5]


def test_wilder_mean_is_all_nan_when_too_short():
    out = indicators.wilder_mean(pd.Series([1.0, 2.0]), 3)
    assert out.isna().all()


def test_true_range_and_atr_hand_computed():
    df = frame([9.0, 10.0, 13.0], highs=[10.0, 11.0, 14.0], lows=[8.0, 9.0, 12.0])
    assert _values(indicators.true_range(df)) == [2.0, 2.0, 4.0]
    assert _values(indicators.atr(df, n=2)) == [None, 2.0, 3.0]


def test_rsi_hand_computed():
    out = indicators.rsi(pd.Series([10.0, 11.0, 10.0, 12.0, 13.0]), 2)
    assert _values(out) == [None, None, 50.0, 83.333333, 90.0]


def test_rsi_is_100_when_there_are_no_losses():
    out = indicators.rsi(pd.Series([1.0, 2.0, 3.0, 4.0]), 2)
    assert _values(out) == [None, None, 100.0, 100.0]


def test_sma_and_rolling_max():
    s = pd.Series([1.0, 3.0, 2.0, 5.0])
    assert _values(indicators.sma(s, 2)) == [None, 2.0, 2.5, 3.5]
    assert _values(indicators.rolling_max(s, 2)) == [None, 3.0, 3.0, 5.0]


@pytest.mark.parametrize("name, fn", [
    ("atr14", lambda d: indicators.atr(d)),
    ("rsi2", lambda d: indicators.rsi(d["Close"], 2)),
    ("sma200", lambda d: indicators.sma(d["Close"], 200)),
    ("max252", lambda d: indicators.rolling_max(d["High"], 252)),
])
def test_every_indicator_reads_no_later_bar(name, fn):
    df = random_walk(320)
    assert_prefix_stable(fn, df, [30, 210, 260, 319])
