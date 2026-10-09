"""Uptrend RSI(2) pullback (Connors & Alvarez 2008). Trigger frozen 2026-10-08 (v140)."""
from __future__ import annotations

import pandas as pd

from swingbot.core.backtesting.screen import indicators

CAP = 10
PARAMS = {"trend_sma": 200, "rsi_n": 2, "rsi_below": 10}
SUMMARY = "close > SMA200 and Wilder RSI(2) < 10"
SOURCE = "Connors & Alvarez (2008)"


def events(df: pd.DataFrame) -> pd.Series:
    """Event at the close of t: an oversold bar inside a long-term uptrend."""
    close = df["Close"]
    trend = indicators.sma(close, PARAMS["trend_sma"])
    osc = indicators.rsi(close, PARAMS["rsi_n"])
    return ((close > trend) & (osc < PARAMS["rsi_below"])).rename("uptrend_pullback")
