"""v174 context hook: other markets an idea may read, point in time.

An idea module that exports ``CONTEXT = ("TLT",)`` receives those frames as
``events(df, context)``. Everything here is pure: the trailing z of a
5-day return, the gate on it, and the exact-date alignment onto a stock's
own index. A value at t reads context bars dated <= t only, and a stock date
the context lacks is ``False``, never forward-filled (v174 spec § 1, § 3).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

#: First bar of backtest_cache_ext/SPY.csv: the context window starts here,
#: so 5 + 252 warm-up bars exist well before EVENT_START (2011-01-01).
CONTEXT_START = "2009-06-01"
LOOKBACK = 5
Z_WINDOW = 252
#: std(W) at or below this is the floating-point form of std(W) == 0.
STD_FLOOR = 1e-12


def r_lookback(close: pd.Series, lookback: int = LOOKBACK) -> pd.Series:
    """close(t) / close(t - lookback) - 1, by row offset (the contiguity
    check against SPY sessions makes the row offset a session offset)."""
    close = close.astype(float)
    return close / close.shift(lookback) - 1.0


def trailing_z(close: pd.Series, lookback: int = LOOKBACK,
               window: int = Z_WINDOW) -> pd.Series:
    """z(t) = (r(t) - mean(W)) / std(W, ddof=0), W = r[t-window .. t-1].

    W is trailing and excludes t. NaN when W is short, W or r(t) holds a
    NaN, or std(W) <= STD_FLOOR."""
    values = r_lookback(close, lookback).to_numpy(dtype=float)
    z = np.full(len(values), np.nan)
    if len(values) > window:
        win = sliding_window_view(values[:-1], window)   # win[i] = r[i .. i+window-1], t = i+window
        with np.errstate(invalid="ignore", divide="ignore"):
            mean = win.mean(axis=1)                      # NaN when W holds a NaN
            std = win.std(axis=1)                        # population std (ddof=0)
            cur = values[window:]
            ok = np.isfinite(cur) & np.isfinite(mean) & (std > STD_FLOOR)
            z[window:] = np.where(ok, (cur - mean) / np.where(ok, std, 1.0), np.nan)
    return pd.Series(z, index=close.index, name="z", dtype=float)


def z_gate(z: pd.Series, threshold: float) -> pd.Series:
    """z >= threshold for a positive threshold, z <= threshold otherwise.
    An undefined z is no event."""
    hit = z >= threshold if threshold > 0 else z <= threshold
    return hit.fillna(False).astype(bool)


def context_on(df_index: pd.DatetimeIndex, series: pd.Series) -> pd.Series:
    """A context series on a stock's dates, by exact date. A stock date the
    context lacks is False, never forward-filled; a context-only date is
    dropped."""
    return series.astype(bool).reindex(df_index, fill_value=False).astype(bool)


def near_mask(raw: np.ndarray, cap: int) -> np.ndarray:
    """True at i when some True position p in ``raw`` has |i - p| < cap
    (the restricted-null diagnostic drops these bars from the null pool)."""
    raw = np.asarray(raw, dtype=bool)
    n = len(raw)
    pos = np.flatnonzero(raw)
    marks = np.zeros(n + 1, dtype=int)            # +1 opens a run, -1 closes it
    np.add.at(marks, np.maximum(pos - cap + 1, 0), 1)
    np.add.at(marks, np.minimum(pos + cap, n), -1)
    return np.cumsum(marks[:n]) > 0
