"""Splice a stale on-disk cache's older bars under a shallow live frame."""
import logging

import numpy as np
import pandas as pd

from swingbot.core.marketdata.history_splice import splice_cached_history

COLS = ["Open", "High", "Low", "Close", "Volume"]


def _frame(start, periods, base=100.0, tz=None, name="Date"):
    idx = pd.bdate_range(start, periods=periods, tz=tz)
    close = base + np.arange(periods, dtype="float64")
    df = pd.DataFrame({"Open": close, "High": close + 1, "Low": close - 1,
                       "Close": close, "Volume": 1000.0}, index=idx)
    df.index.name = name
    return df


def _pair():
    """cache = 300 bars from 2024-01-01; live = last 100 of the same bars
    (identical prices on the overlap) plus 2 newer bars."""
    full = _frame("2024-01-01", 302)
    return full.iloc[:300].copy(), full.iloc[200:].copy()


def test_splice_returns_cached_older_rows_plus_live():
    cached, live = _pair()
    out = splice_cached_history(live, cached, "AAPL")
    assert len(out) == 302
    assert out.index.is_monotonic_increasing and not out.index.has_duplicates
    assert out.index[0] == cached.index[0] and out.index[-1] == live.index[-1]
    assert list(out.columns) == COLS and out.index.tz is None
    assert (out.dtypes == "float64").all()


def test_live_wins_on_overlap_and_future_rows_never_come_from_cache():
    cached, live = _pair()
    live.loc[live.index[5], "Close"] = live.loc[live.index[5], "Close"] * 1.004  # within tolerance
    cached = cached.copy()
    cached.loc[cached.index[-1], "Close"] += 0.1       # cached bar inside the overlap
    out = splice_cached_history(live, cached, "AAPL")
    assert out.loc[live.index[5], "Close"] == live.loc[live.index[5], "Close"]
    assert out.loc[cached.index[-1], "Close"] == live.loc[cached.index[-1], "Close"]
    assert out.index.max() == live.index.max()          # partial bar stays last
    assert (out.iloc[-len(live):] == live).all().all()


def test_cached_rows_after_the_live_last_bar_are_never_used():
    cached, live = _pair()
    future = _frame("2030-01-01", 3)
    cached = pd.concat([cached, future])
    out = splice_cached_history(live, cached, "AAPL")
    assert out.index.max() == live.index.max()


def test_split_mismatch_returns_live_only_and_logs_info(caplog):
    cached, live = _pair()
    cached[["Open", "High", "Low", "Close"]] *= 2.0     # un-split cache vs split-adjusted live
    with caplog.at_level(logging.INFO):
        out = splice_cached_history(live, cached, "AAPL")
    assert out is live
    assert any("AAPL" in r.message and r.levelno == logging.INFO for r in caplog.records)


def test_no_cache_returns_live():
    _, live = _pair()
    assert splice_cached_history(live, None, "AAPL") is live
    assert splice_cached_history(live, live.iloc[0:0], "AAPL") is live


def test_cache_not_older_than_live_returns_live():
    cached, live = _pair()
    assert splice_cached_history(cached, live, "AAPL") is cached  # roles swapped: cache shorter


def test_tz_mismatch_returns_live():
    cached, live = _pair()
    cached.index = cached.index.tz_localize("UTC")
    assert splice_cached_history(live, cached, "AAPL") is live


def test_column_mismatch_returns_live():
    cached, live = _pair()
    cached["Adj Close"] = cached["Close"]
    assert splice_cached_history(live, cached, "AAPL") is live


def test_no_overlap_cannot_prove_basis_returns_live():
    cached = _frame("2020-01-01", 50)
    live = _frame("2024-01-01", 50)
    assert splice_cached_history(live, cached, "AAPL") is live


def test_live_attrs_survive():
    cached, live = _pair()
    live.attrs["source"] = "alpaca"
    assert splice_cached_history(live, cached, "AAPL").attrs["source"] == "alpaca"

def test_duplicate_and_unsorted_cache_index_is_normalised():
    cached, live = _pair()
    older = cached[cached.index < live.index.min()]
    dup = older.iloc[[10]].copy()
    dup["Close"] = dup["Close"] + 5.0                   # later duplicate row wins
    messy = pd.concat([cached.iloc[::-1], dup])         # reversed + a duplicate date
    out = splice_cached_history(live, messy, "AAPL")
    assert out.index.is_monotonic_increasing and not out.index.has_duplicates
    assert len(out) == 302
    assert out.loc[older.index[10], "Close"] == dup["Close"].iloc[0]


def test_mixed_dtype_volume_is_coerced_to_the_live_dtypes():
    cached, live = _pair()
    cached["Volume"] = cached["Volume"].astype("int64").astype(object)
    out = splice_cached_history(live, cached, "AAPL")
    assert (out.dtypes == live.dtypes).all()
    assert out["Volume"].dtype == "float64"


def test_truncating_live_never_changes_earlier_spliced_rows():
    """NO-LOOKAHEAD: the older slice depends only on live.index.min(), so for
    any cut k (keeping >= the overlap minimum) splice(live[:k]) equals the
    first len(older)+k rows of splice(live) -- later live bars cannot reach
    back and alter anything a bar at index <= k already saw."""
    cached, live = _pair()
    full = splice_cached_history(live, cached, "AAPL")
    n_older = len(cached[cached.index < live.index.min()])
    for k in (40, 77, 100):
        cut = splice_cached_history(live.iloc[:k], cached, "AAPL")
        pd.testing.assert_frame_equal(cut, full.iloc[:n_older + k])


def test_stale_cache_after_a_split_returns_live_unchanged_and_logs(caplog):
    cached, live = _pair()
    cached[["Open", "High", "Low", "Close"]] *= 2.0     # overlap close ratio ~0.5 live/cached
    with caplog.at_level(logging.INFO):
        out = splice_cached_history(live, cached, "SPLT")
    pd.testing.assert_frame_equal(out, live)
    assert any("SPLT" in r.message and "disagree" in r.message for r in caplog.records)
