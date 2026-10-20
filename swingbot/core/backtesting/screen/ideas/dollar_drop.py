"""Dollar drop (v174, frozen 2026-10-18): UUP 5-day return z <= -2.0
against its trailing 252 values, long the stock the next open.

Closer to Murphy (a falling dollar is bullish for equities), but a lagged
proxy for a trend claim: a dollar drop often accompanies a risk-on rally
already under way (spec § What the two shots can and cannot say). A fail
closes exactly this frozen definition.
"""
from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

from swingbot.core.backtesting.screen import context as pit

CONTEXT = ("UUP",)
CAP = 10
RACE = "fixed"
PARAMS = {"series": "UUP", "lookback": 5, "window": 252, "z": -2.0, "side": "long"}
SUMMARY = "UUP 5-day return z <= -2.0 vs its trailing 252 values"
SOURCE = ("Murphy (2004), Intermarket Analysis — shock proxy, "
          "see v174 § What the two shots can and cannot say")


def events(df: pd.DataFrame, context: Mapping[str, pd.DataFrame]) -> pd.Series:
    """True on every stock date whose own UUP bar has z <= -2.0. The z at t
    reads UUP bars dated <= t only; a stock date with no UUP bar is False."""
    close = context[PARAMS["series"]]["Close"]
    z = pit.trailing_z(close, PARAMS["lookback"], PARAMS["window"])
    gate = pit.z_gate(z, PARAMS["z"])
    return pit.context_on(df.index, gate).rename("dollar_drop")
