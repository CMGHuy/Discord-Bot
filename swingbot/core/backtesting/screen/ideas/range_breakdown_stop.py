"""Range breakdown, resting sell stop, short (Schwab 2025). Frozen 2026-10-21 (v182).

The same frozen range and downtrend as range_breakdown_close
(_range_breakdown.py). Before bar t opens, a sell stop rests at the range's
support S, known from bars <= t-1, for one bar. It fills when bar t trades
below S (Low[t] < S, strict; a bar that only touches S does not fill). The
screen races it in level mode (ENTRY = "level"): entry on bar t at
min(Open[t], S), risk 1.5 x ATR14[t-1], the worst-case entry-bar stop rule
and 2 x stop-market slippage (v182 Part B).
"""
from __future__ import annotations

import pandas as pd

from swingbot.core.backtesting.screen.ideas import _range_breakdown as rb

CAP = 20
RACE = "fixed"
DIRECTION = "short"
ENTRY = "level"
PARAMS = {**rb.PARAMS, "trigger": "low[t] < S", "level": "S"}
SUMMARY = ("30-bar range (R - S <= 5 ATR14[t-1], two touches of each side "
           ">= 5 bars apart) in a falling SMA50 with the prior close below it; "
           "sell stop at S fills when low[t] < S (short, level entry)")
SOURCE = rb.SOURCE
FAMILY = rb.FAMILY


def levels(df: pd.DataFrame) -> pd.Series:
    """The sell stop's level for bar t: S over t-30..t-1."""
    return rb.support(df).rename("range_breakdown_stop_level")


def _trigger(df: pd.DataFrame) -> pd.Series:
    """Bar t trades below the resting level."""
    return df["Low"] < levels(df)


def events(df: pd.DataFrame) -> pd.Series:
    """Event on bar t: the frozen setup and a fill of the sell stop."""
    return (rb.setup(df) & _trigger(df)).rename("range_breakdown_stop")


def control_events(df: pd.DataFrame) -> pd.Series:
    """The trend-only control (spec Part C): same trigger and trend clauses,
    no range clauses. Printed by the results doc, never gating."""
    return (rb.control_setup(df) & _trigger(df)).rename("range_breakdown_stop_control")
