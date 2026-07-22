import numpy as np
import pandas as pd
import pytest

from tests.conftest import make_ohlcv
from swingbot.core.edge.gates import gap_stats, stop_beyond_gap_noise


def _with_gaps(gap_every=10, gap_pct=3.0, n=300):
    closes = np.full(n, 100.0)
    df = make_ohlcv(closes, spread_pct=1.0)
    open_col = df.columns.get_loc("Open")
    for i in range(gap_every, n, gap_every):
        df.iloc[i, open_col] = 100.0 * (1 + gap_pct / 100)
    return df


def test_gappy_ticker_has_fat_gap_tail():
    smooth = gap_stats(make_ohlcv(np.full(300, 100.0), spread_pct=1.0))
    gappy = gap_stats(_with_gaps())
    assert gappy["p90_gap_pct"] > smooth["p90_gap_pct"]
    assert gappy["p99_gap_pct"] >= gappy["p90_gap_pct"]
    assert gappy["n"] == 250   # lookback bound respected


def test_stop_inside_gap_noise_is_fragile():
    # stop 1.5% away, P90 gap 3% -> a coin flip, not risk control
    assert stop_beyond_gap_noise(1.5, 3.0) is False
    assert stop_beyond_gap_noise(4.0, 3.0) is True
