"""Shock support break, short (v211, frozen 2026-11-05 in spec v209 § Track 2).

On a SHOCK_D date (_shock_breakdown.py) the stock closes below the lowest Low
of the 20 bars before it, and it is the first such close in this SHOCK
episode; the screen's race shorts the next open (fixed 1.5/3 ATR, 10-bar
cap). The control is every fresh 20-day-low close with the shock state
ignored (printed, never gating). One family with shock_failed_bounce_short; a
fail closes exactly this definition.
"""
from __future__ import annotations

import pandas as pd

from swingbot.core.backtesting.screen.ideas import _shock_breakdown as sb

CAP = 10
RACE = "fixed"
DIRECTION = "short"
CONTEXT = sb.CONTEXT
CONTEXT_KIND = "level"
FAMILY = sb.FAMILY
PARAMS = {**sb.SHOCK_PARAMS, "low_window": sb.LOW_WINDOW, "side": "short"}
SUMMARY = ("SHOCK_D on t (BREADTH_ATR1 >= 0.40 enters; <= 0.10 with ^VIX down "
           "releases) and close[t] < min(Low[t-20..t-1]), the first such close "
           "in the episode (short, next open)")
SOURCE = sb.SOURCE


def low_break(df: pd.DataFrame) -> pd.Series:
    """Close[t] below the lowest Low of the 20 bars before t (warm-up False)."""
    return (df["Close"] < sb.prior_low(df)).astype(bool)


def _first_per_episode(hits: pd.Series, episode: pd.Series) -> pd.Series:
    """Keep a hit only when no earlier bar of its episode was a hit."""
    n = hits.astype(int)
    return hits & (n.groupby(episode).cumsum() - n == 0)


def events(df: pd.DataFrame, context) -> pd.Series:
    """First close below the prior 20-day low in each SHOCK episode."""
    state = sb.ticker_state(df, context)
    out = _first_per_episode(low_break(df) & state["shock"], state["episode"])
    return out.rename("shock_support_break_short")


def control_events(df: pd.DataFrame) -> pd.Series:
    """Every fresh 20-day-low close, the shock state ignored."""
    brk = low_break(df)
    return (brk & ~brk.shift(1, fill_value=False)).rename("shock_support_break_short_control")
