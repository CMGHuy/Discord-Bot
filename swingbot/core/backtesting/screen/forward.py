"""Reported-only drift for the v140 screen (spec § forward.py).

Mean excess forward return in ATR units at h in HORIZONS, event minus its
matched null, and per-year Spearman rank correlation between the event
indicator and the h-bar forward return. Printed beside the verdict; the
verdict never reads it. numpy/pandas only (scipy is not a dependency).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

HORIZONS = (5, 10, 20, 60)
MIN_RANK_N = 3


def forward_atr(df: pd.DataFrame, atr, h: int) -> np.ndarray:
    """(close[t+h] - close[t]) / ATR14[t]; NaN where t+h is past the frame."""
    close = df["Close"].to_numpy(dtype=float)
    a = pd.Series(atr).to_numpy(dtype=float)
    out = np.full(len(close), np.nan)
    if h < len(close):
        with np.errstate(divide="ignore", invalid="ignore"):
            out[: len(close) - h] = (close[h:] - close[: len(close) - h]) / a[: len(close) - h]
    return out


def excess_drift(fwd, event_pos, groups) -> list:
    out = []
    for pos, group in zip(event_pos, groups):
        null = fwd[np.asarray(group, dtype=int)]
        null = null[np.isfinite(null)]
        if np.isfinite(fwd[pos]) and null.size:
            out.append(float(fwd[pos] - null.mean()))
    return out


def spearman(x, y) -> float | None:
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    if len(x) < MIN_RANK_N:
        return None
    rx = pd.Series(x).rank().to_numpy()
    ry = pd.Series(y).rank().to_numpy()
    if rx.std() == 0 or ry.std() == 0:
        return None
    return float(np.corrcoef(rx, ry)[0, 1])


def yearly_rank_corr(years, indicator, fwd) -> dict:
    years = np.asarray(years)
    indicator = np.asarray(indicator, dtype=float)
    fwd = np.asarray(fwd, dtype=float)
    ok = np.isfinite(fwd)
    return {int(y): spearman(indicator[ok & (years == y)], fwd[ok & (years == y)])
            for y in np.unique(years[ok])}
