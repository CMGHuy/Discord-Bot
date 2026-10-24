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


def _signed_gaps(n=300, up_pct=2.0, down_pct=6.0):
    """Close flat at 100; even rows open up_pct above the prior close, odd rows
    open down_pct below it -> 250 gaps in the 251-row tail, 125 of them up."""
    idx = pd.bdate_range(start="2025-06-02", periods=n)
    opens = [100.0 * (1 + up_pct / 100) if i % 2 == 0 else 100.0 * (1 - down_pct / 100)
             for i in range(n)]
    closes = [100.0] * n
    return pd.DataFrame({"Open": opens, "High": [max(o, 100.0) * 1.01 for o in opens],
                         "Low": [min(o, 100.0) * 0.99 for o in opens], "Close": closes,
                         "Volume": [1_000_000.0] * n}, index=idx)


def test_up_gap_p99_measures_only_the_adverse_side_for_a_short():
    stats = gap_stats(_signed_gaps())
    assert stats["p99_gap_pct"] == pytest.approx(6.0)        # absolute: the down gaps dominate
    assert stats["p99_up_gap_pct"] == pytest.approx(2.0)     # up-gaps only
    assert stats["n_up"] == 125
    assert stats["n"] == 250


def test_existing_keys_are_unchanged_by_the_new_ones():
    stats = gap_stats(_with_gaps())
    assert stats["n"] == 250
    assert stats["p99_gap_pct"] >= stats["p90_gap_pct"]
    assert set(stats) == {"p90_gap_pct", "p99_gap_pct", "n", "p99_up_gap_pct", "n_up"}


def test_no_up_gaps_gives_none_not_zero():
    stats = gap_stats(_signed_gaps(up_pct=-1.0))             # every gap is a down gap
    assert stats["p99_up_gap_pct"] is None
    assert stats["n_up"] == 0


def test_flat_opens_are_not_up_gaps():
    stats = gap_stats(make_ohlcv(np.full(300, 100.0), spread_pct=1.0))
    assert stats["n_up"] == 0 and stats["p99_up_gap_pct"] is None


def test_empty_frame_carries_the_new_keys():
    empty = pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
    assert gap_stats(empty) == {"p90_gap_pct": 0.0, "p99_gap_pct": 0.0, "n": 0,
                                "p99_up_gap_pct": None, "n_up": 0}


def test_up_gap_lookback_bound_respected():
    df = _signed_gaps(n=400)
    df.iloc[:100, df.columns.get_loc("Open")] = 150.0          # huge up gaps OUTSIDE the 250-bar window
    assert gap_stats(df)["p99_up_gap_pct"] == pytest.approx(2.0)
