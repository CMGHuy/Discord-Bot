"""Bond spike rebound (v174, frozen 2026-10-18): TLT 5-day return z >= +2.0
against its trailing 252 values, long the stock the next open.

A shock proxy, not Murphy's claim itself: in 2010-19 such a TLT rally was
mostly a flight-to-quality day, so long stocks after it tests a rebound
after a risk-off bond spike (spec § What the two shots can and cannot say).
A fail closes exactly this frozen definition.
"""
from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

from swingbot.core.backtesting.screen import context as pit

CONTEXT = ("TLT",)
CAP = 10
RACE = "fixed"
PARAMS = {"series": "TLT", "lookback": 5, "window": 252, "z": 2.0, "side": "long"}
SUMMARY = "TLT 5-day return z >= +2.0 vs its trailing 252 values"
SOURCE = ("Murphy (2004), Intermarket Analysis — shock proxy, "
          "see v174 § What the two shots can and cannot say")


def events(df: pd.DataFrame, context: Mapping[str, pd.DataFrame]) -> pd.Series:
    """True on every stock date whose own TLT bar has z >= +2.0. The z at t
    reads TLT bars dated <= t only; a stock date with no TLT bar is False."""
    close = context[PARAMS["series"]]["Close"]
    z = pit.trailing_z(close, PARAMS["lookback"], PARAMS["window"])
    gate = pit.z_gate(z, PARAMS["z"])
    return pit.context_on(df.index, gate).rename("bond_spike_rebound")
