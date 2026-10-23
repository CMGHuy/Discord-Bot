"""Range breakdown, close-confirmed, short (Schwab 2025). Frozen 2026-10-21 (v182).

A stock in its own downtrend (SMA50 falling, the prior close below it) has
spent 30 bars in a defined range (two touches of each side at least 5 bars
apart, no taller than 5 x ATR14). Today closes below the range's support S.
The screen's race enters short at the next open. The range and trend
definition is shared with range_breakdown_stop (_range_breakdown.py); the two
ideas are nested (every close event is a stop event) and screened as one
family.
"""
from __future__ import annotations

import pandas as pd

from swingbot.core.backtesting.screen.ideas import _range_breakdown as rb

CAP = 20
RACE = "fixed"
DIRECTION = "short"
PARAMS = {**rb.PARAMS, "trigger": "close[t] < S"}
SUMMARY = ("30-bar range (R - S <= 5 ATR14[t-1], two touches of each side "
           ">= 5 bars apart) in a falling SMA50 with the prior close below it; "
           "close[t] < S (short, next open)")
SOURCE = rb.SOURCE
FAMILY = rb.FAMILY


def _trigger(df: pd.DataFrame) -> pd.Series:
    """Bar t closes below the support of the 30 bars before it."""
    return df["Close"] < rb.support(df)


def events(df: pd.DataFrame) -> pd.Series:
    """Event at the close of t: the frozen setup and a close below S."""
    return (rb.setup(df) & _trigger(df)).rename("range_breakdown_close")


def control_events(df: pd.DataFrame) -> pd.Series:
    """The trend-only control (spec Part C): same trigger and trend clauses,
    no range clauses. Printed by the results doc, never gating."""
    return (rb.control_setup(df) & _trigger(df)).rename("range_breakdown_close_control")
