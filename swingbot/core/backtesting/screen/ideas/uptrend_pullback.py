"""Uptrend RSI(2) pullback (Connors & Alvarez 2008). Trigger: V140-7."""
from __future__ import annotations

import pandas as pd

CAP = 10
PARAMS = {"trend_sma": 200, "rsi_n": 2, "rsi_below": 10}
SUMMARY = "close > SMA200 and Wilder RSI(2) < 10"
SOURCE = "Connors & Alvarez (2008)"


def events(df: pd.DataFrame) -> pd.Series:
    raise NotImplementedError("V140-7 implements the uptrend_pullback trigger")
