"""Turtle Soup, buy side (Connors & Raschke 1995). Trigger frozen 2026-10-15.

A failed breakdown below the 20-day channel: today trades under the prior
20-bar low, that low is at least four sessions old, and the close is back
above it. The book enters on a buy stop at the old low during the session;
the screen's race enters at the next open, so this reading is close-confirmed.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

CAP = 10
PARAMS = {"channel": 20, "min_age": 4}
SUMMARY = ("low < the prior 20-bar low, that low set >= 4 bars before t, "
           "close > that low (close-confirmed reclaim)")
SOURCE = "Connors & Raschke, Street Smarts (1995), Turtle Soup"


def _age_of_last_min(window: np.ndarray) -> float:
    """Bars from t back to the latest bar holding the window's minimum; the
    window ends at t-1, so its last bar has age 1."""
    latest = len(window) - 1 - int(np.argmin(window[::-1]))
    return float(len(window) - latest)


def events(df: pd.DataFrame) -> pd.Series:
    """Event at the close of t: a new 20-bar low that closed back above the
    aged prior low."""
    n = PARAMS["channel"]
    prior = df["Low"].shift(1)
    prior_low = prior.rolling(n, min_periods=n).min()
    age = prior.rolling(n, min_periods=n).apply(_age_of_last_min, raw=True)
    broke = df["Low"] < prior_low
    reclaimed = df["Close"] > prior_low
    aged = age >= PARAMS["min_age"]
    return (broke & reclaimed & aged).rename("turtle_soup")
