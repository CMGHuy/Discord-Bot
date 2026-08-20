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


NEUTRAL_SCORE = 0.5


def grade_level(df: pd.DataFrame, level: float, direction: str,
                halflife_bars: int,
                tolerance_pct: float = DEFAULT_TOLERANCE_PCT) -> dict:
    """Aggregate every touch of `level` into one 0..1 grade.

    Rejections push the grade up, breaks push it down, and both decay with
    age on `halflife_bars`. A level with no touches returns NEUTRAL_SCORE and
    available=False -- absence of evidence is not evidence of weakness, and
    scoring it low would make the system prefer merely OLD levels.
    """
    from swingbot.core.edge.factors import pattern_quality_at_level

    touches = find_touches(df, level, tolerance_pct)
    if not touches:
        return {"score": NEUTRAL_SCORE, "touches": 0, "rejections": 0,
                "breaks": 0, "available": False}

    last = len(df) - 1
    bull = direction == "bullish"
    weighted, total_weight = 0.0, 0.0
    rejections = breaks = 0

    for idx in touches:
        bar = df.iloc[idx]
        pierced = bar["Low"] <= level if bull else bar["High"] >= level
        reclaimed = bar["Close"] > level if bull else bar["Close"] < level
        weight = 0.5 ** ((last - idx) / max(1, halflife_bars))

        if pierced and reclaimed:
            rejections += 1
            # pattern_quality_at_level scores 0-10 with no negative band, so
            # it grades HOW WELL the level held; the break case supplies the
            # negative signal below rather than editing a shared function.
            quality = pattern_quality_at_level(df, idx, level, direction) / 10.0
            weighted += weight * quality
        elif pierced and not reclaimed:
            breaks += 1
            weighted += weight * 0.0
        else:
            weighted += weight * NEUTRAL_SCORE
        total_weight += weight

    score = weighted / total_weight if total_weight else NEUTRAL_SCORE
    return {"score": max(0.0, min(1.0, score)), "touches": len(touches),
            "rejections": rejections, "breaks": breaks, "available": True}
