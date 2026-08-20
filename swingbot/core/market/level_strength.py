"""How convincingly price has respected a level, and how recently (v36).

The per-bar classifier already exists as
edge.factors.pattern_quality_at_level -- it distinguishes a rejection (pierced
the level and closed back beyond it) from a break (closed through). This module
supplies what was missing: which bars touched the level at all, and how to
aggregate many touches into one grade that decays with age.

Pure functions, no config reads, so the backtest can call them directly.
"""
from __future__ import annotations

import pandas as pd

DEFAULT_TOLERANCE_PCT = 0.5


def find_touches(df: pd.DataFrame, level: float,
                 tolerance_pct: float = DEFAULT_TOLERANCE_PCT) -> list[int]:
    """Indices of bars whose range entered the band around `level`.

    The band is a PERCENTAGE of the level, not an absolute amount: a fixed
    band would be meaningless across a watchlist holding both a $20 and a
    $2000 ticker.
    """
    if df is None or len(df) == 0 or level <= 0:
        return []
    half = level * tolerance_pct / 100.0
    lo, hi = level - half, level + half
    lows = df["Low"].values
    highs = df["High"].values
    return [i for i in range(len(df)) if lows[i] <= hi and highs[i] >= lo]
