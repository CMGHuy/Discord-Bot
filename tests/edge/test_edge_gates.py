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


def test_earnings_blackout_window():
    from swingbot.core.edge.gates import in_earnings_blackout
    at = lambda distance: lambda symbol, now: distance
    assert in_earnings_blackout("NVDA", sessions=3, sessions_to_reaction_fn=at(1)) is True
    assert in_earnings_blackout("NVDA", sessions=3, sessions_to_reaction_fn=at(3)) is True
    assert in_earnings_blackout("NVDA", sessions=3, sessions_to_reaction_fn=at(4)) is False
    assert in_earnings_blackout("NVDA", sessions=3, sessions_to_reaction_fn=at(0)) is False
    assert in_earnings_blackout("NVDA", sessions=0, sessions_to_reaction_fn=at(1)) is False


def test_earnings_blackout_etf_exempt():
    from swingbot.core.edge.gates import in_earnings_blackout
    # default source is ETF-exempt (E14 returns None) -> never blacked out
    assert in_earnings_blackout("SPY", sessions=5) is False
