"""Uptrend RSI(2) pullback with no news footprint. Trigger frozen 2026-10-15.

Medhat & Novy-Marx: short-run reversal is a liquidity effect that news moves
contaminate. The screen has no point-in-time earnings dates for its
universe, so a news bar is read from price and volume, with the gap and
volume rules of gap_volume: a gap of more than one prior ATR14 either way,
or more than twice the 50-bar mean volume ending the prior bar.
"""
from __future__ import annotations

import pandas as pd

from swingbot.core.backtesting.screen import indicators

CAP = 10
PARAMS = {"trend_sma": 200, "rsi_n": 2, "rsi_below": 10, "quiet_bars": 3,
          "gap_atr": 1.0, "atr_n": 14, "volume_mult": 2.0, "volume_window": 50}
SUMMARY = ("close > SMA200 and Wilder RSI(2) < 10, and none of bars t-2..t "
           "gapped > 1.0 x prior ATR14 or traded > 2 x the 50-bar mean volume")
SOURCE = ("Connors & Alvarez (2008) trigger; Medhat & Novy-Marx news-free "
          "reversal, price/volume news proxy")


def _news_bar(df: pd.DataFrame) -> pd.Series:
    p = PARAMS
    prev_atr = indicators.atr(df, p["atr_n"]).shift(1)
    prev_volume = df["Volume"].rolling(
        p["volume_window"], min_periods=p["volume_window"]).mean().shift(1)
    gapped = (df["Open"] - df["Close"].shift(1)).abs() > p["gap_atr"] * prev_atr
    loud = df["Volume"] > p["volume_mult"] * prev_volume
    return gapped | loud


def events(df: pd.DataFrame) -> pd.Series:
    """Event at the close of t: an oversold bar in an uptrend whose last
    three bars carry no gap or volume spike."""
    p = PARAMS
    close = df["Close"]
    trend = close > indicators.sma(close, p["trend_sma"])
    oversold = indicators.rsi(close, p["rsi_n"]) < p["rsi_below"]
    news = _news_bar(df).astype(float).rolling(p["quiet_bars"], min_periods=1).max() > 0
    return (trend & oversold & ~news).rename("quiet_pullback")
