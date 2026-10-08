"""Causal indicators for the v140 idea screen.

Every value at bar t reads bars <= t only (pinned by a truncation test).
Wilder smoothing is seeded with the simple mean of the first n valid values,
then y[t] = ((n - 1) * y[t-1] + x[t]) / n.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def wilder_mean(values: pd.Series, n: int) -> pd.Series:
    """Wilder's running mean; NaN until n valid values have been seen."""
    out = pd.Series(np.nan, index=values.index, dtype=float)
    valid = values.notna().to_numpy()
    if not valid.any():
        return out
    first = int(np.argmax(valid))
    seed_at = first + n - 1
    if seed_at >= len(values):
        return out
    tail = values.iloc[seed_at:].astype(float).copy()
    tail.iloc[0] = float(values.iloc[first:seed_at + 1].mean())
    out.iloc[seed_at:] = tail.ewm(alpha=1.0 / n, adjust=False).mean().to_numpy()
    return out


def true_range(df: pd.DataFrame) -> pd.Series:
    """max(H - L, |H - prev C|, |L - prev C|); bar 0 is H - L."""
    prev = df["Close"].shift(1)
    ranges = pd.concat([df["High"] - df["Low"], (df["High"] - prev).abs(),
                        (df["Low"] - prev).abs()], axis=1)
    return ranges.max(axis=1)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    """Wilder ATR(n)."""
    return wilder_mean(true_range(df), n)


def rsi(close: pd.Series, n: int) -> pd.Series:
    """Wilder RSI(n); 100 where the average loss is zero."""
    delta = close.diff()
    gain = wilder_mean(delta.clip(lower=0.0), n)
    loss = wilder_mean((-delta).clip(lower=0.0), n)
    with np.errstate(divide="ignore", invalid="ignore"):
        value = 100.0 - 100.0 / (1.0 + gain / loss)
    return value.where(loss != 0, 100.0).where(gain.notna())


def sma(values: pd.Series, n: int) -> pd.Series:
    """Simple moving average over the last n bars, t included."""
    return values.rolling(n, min_periods=n).mean()


def rolling_max(values: pd.Series, n: int) -> pd.Series:
    """Maximum over the last n bars, t included."""
    return values.rolling(n, min_periods=n).max()
