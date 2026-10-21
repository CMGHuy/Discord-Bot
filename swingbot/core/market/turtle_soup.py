"""v180: the live Turtle Soup trigger -- bar t sweeps an aged 20-bar low and closes back above it.

Frozen from the v140 screen (screen/ideas/turtle_soup.py, which live code never imports):
Low[t] < L and Close[t] > L, where L = min Low of bars t-20..t-1 and the LATEST bar in that
window holding L is >= MIN_AGE bars before t. NO-LOOKAHEAD: bar t reads bars <= t only.
A window with a NaN Low yields no signal (the screen's rolling min_periods rule)."""
from __future__ import annotations

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

CHANNEL = 20
MIN_AGE = 4


def sweep_frame(df: pd.DataFrame) -> pd.DataFrame:
    """prior_low (L), age (bars from the latest bar holding L to t) and the signal, per bar."""
    low = df["Low"].to_numpy(dtype=float)
    close = df["Close"].to_numpy(dtype=float)
    n = len(low)
    prior_low = np.full(n, np.nan)
    age = np.full(n, np.nan)
    if n > CHANNEL:
        windows = sliding_window_view(low[:-1], CHANNEL)        # windows[k]: bars k..k+19, prior to bar k+20
        valid = ~np.isnan(windows).any(axis=1)
        latest = CHANNEL - 1 - np.argmin(windows[:, ::-1], axis=1)   # latest bar holding the min
        prior_low[CHANNEL:] = np.where(valid, windows.min(axis=1), np.nan)
        age[CHANNEL:] = np.where(valid, CHANNEL - latest, np.nan)
    with np.errstate(invalid="ignore"):
        signal = (low < prior_low) & (close > prior_low) & (age >= MIN_AGE)
    return pd.DataFrame({"prior_low": prior_low, "age": age, "signal": signal}, index=df.index)


def turtle_soup_signal(df: pd.DataFrame) -> pd.Series:
    """The bullish signal series, named like the screen's events()."""
    return sweep_frame(df)["signal"].astype(bool).rename("turtle_soup")
