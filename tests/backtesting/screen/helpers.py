"""Synthetic OHLCV frames and the truncation guard for the v140 screen tests."""
from __future__ import annotations

import numpy as np
import pandas as pd


def frame(closes, *, start="2010-01-04", opens=None, highs=None, lows=None,
          volumes=None, index=None) -> pd.DataFrame:
    """An OHLCV frame. Defaults: Open = Close, High = Close + 1,
    Low = Close - 1, Volume = 1e6, business-day index from ``start``."""
    closes = np.asarray(closes, dtype=float)
    idx = (pd.DatetimeIndex(index) if index is not None
           else pd.bdate_range(start, periods=len(closes)))

    def pick(given, default):
        return default if given is None else np.asarray(given, dtype=float)

    return pd.DataFrame({
        "Open": pick(opens, closes),
        "High": pick(highs, closes + 1.0),
        "Low": pick(lows, closes - 1.0),
        "Close": closes,
        "Volume": pick(volumes, np.full(len(closes), 1e6)),
    }, index=idx)


def random_walk(n, seed=7, start="2010-01-04") -> pd.DataFrame:
    """A plausible daily price path: drift, gaps, volume noise."""
    rng = np.random.default_rng(seed)
    close = 100.0 * np.exp(np.cumsum(rng.normal(0.0004, 0.015, n)))
    open_ = np.r_[close[0], close[:-1]] * np.exp(rng.normal(0.0, 0.006, n))
    high = np.maximum(open_, close) * (1.0 + np.abs(rng.normal(0.0, 0.008, n)))
    low = np.minimum(open_, close) * (1.0 - np.abs(rng.normal(0.0, 0.008, n)))
    volume = rng.integers(500_000, 3_000_000, n).astype(float)
    return frame(close, start=start, opens=open_, highs=high, lows=low,
                 volumes=volume)


def assert_prefix_stable(fn, df, checkpoints, *, skip_last=False) -> None:
    """``fn(df.iloc[:t+1])`` equals ``fn(df)`` on bars ``<= t``: nothing the
    function says about bar t reads a later bar. ``skip_last`` leaves the
    truncated frame's final bar out of the comparison (frozen reading F1)."""
    full = pd.Series(fn(df), index=df.index)
    for t in checkpoints:
        part = pd.Series(fn(df.iloc[: t + 1]), index=df.index[: t + 1])
        stop = t if skip_last else t + 1
        pd.testing.assert_series_equal(
            part.iloc[:stop], full.iloc[:stop], check_names=False,
            check_exact=False, rtol=1e-12, atol=0.0, obj=f"prefix ending at bar {t}")
