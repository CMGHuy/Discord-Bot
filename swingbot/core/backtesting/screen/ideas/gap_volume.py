"""Gap + volume continuation (earnings/news gap drift). Trigger frozen 2026-10-08 (v140)."""
from __future__ import annotations

import pandas as pd

from swingbot.core.backtesting.screen import indicators

CAP = 20
PARAMS = {"gap_atr": 1.0, "atr_n": 14, "volume_mult": 2.0, "volume_window": 50}
SUMMARY = ("open >= prior close + 1.0 x prior ATR14, volume >= 2 x the 50-bar "
           "mean volume ending the prior bar, close >= open")
SOURCE = "earnings/news gap drift; volume as the news proxy"


def events(df: pd.DataFrame) -> pd.Series:
    """Event at the close of t: today's open gapped a full ATR above
    yesterday's close on double volume, and the gap held into the close."""
    p = PARAMS
    prev_close = df["Close"].shift(1)
    prev_atr = indicators.atr(df, p["atr_n"]).shift(1)
    prev_volume = df["Volume"].rolling(
        p["volume_window"], min_periods=p["volume_window"]).mean().shift(1)
    gap = df["Open"] >= prev_close + p["gap_atr"] * prev_atr
    loud = df["Volume"] >= p["volume_mult"] * prev_volume
    held = df["Close"] >= df["Open"]
    return (gap & loud & held).rename("gap_volume")
