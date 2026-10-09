"""52-week-high momentum (George & Hwang 2004). Trigger frozen 2026-10-08 (v140)."""
from __future__ import annotations

import pandas as pd

from swingbot.core.backtesting.screen import indicators

CAP = 60
PARAMS = {"near_high": 0.95, "lookback": 252, "fast_sma": 50, "slow_sma": 200,
          "quiet_bars": 20}
SUMMARY = ("close >= 0.95 x the 252-bar high with SMA50 > SMA200; first true "
           "bar after >= 20 consecutive computable false bars")
SOURCE = "George & Hwang (2004)"


def events(df: pd.DataFrame) -> pd.Series:
    """Event at the close of t. The quiet run counts only bars where the
    condition is computable (frozen reading F3)."""
    p = PARAMS
    close = df["Close"]
    top = indicators.rolling_max(df["High"], p["lookback"])
    fast = indicators.sma(close, p["fast_sma"])
    slow = indicators.sma(close, p["slow_sma"])
    known = top.notna() & fast.notna() & slow.notna()
    cond = known & (close >= p["near_high"] * top) & (fast > slow)
    quiet = (known & ~cond).astype(int).rolling(
        p["quiet_bars"], min_periods=p["quiet_bars"]).sum().shift(1)
    return (cond & (quiet == p["quiet_bars"])).rename("high52w")
