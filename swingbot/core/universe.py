"""Tradeable-universe utilities: liquidity screening (this task), universe
files + loaders (E13), ETF tagging (E14), data-quality rules (E16).

Liquidity is what makes the E11 slippage assumption honest: 5 bps is a
reasonable model for a $20M+/day name, a fantasy for a $500k/day one.
"""
from __future__ import annotations

import pandas as pd

from swingbot import config


def _avg_dollar_vol(df: pd.DataFrame, window: int = 20) -> float:
    tail = df.tail(window)
    return float((tail["Close"] * tail["Volume"]).mean())


def liquidity_ok(df: pd.DataFrame, min_avg_dollar_vol: float | None = None,
                  min_price: float | None = None) -> bool:
    return liquidity_reason(df, min_avg_dollar_vol, min_price) is None


def liquidity_reason(df: pd.DataFrame, min_avg_dollar_vol: float | None = None,
                      min_price: float | None = None) -> str | None:
    """None when liquid; else a loggable reason string."""
    if df is None or len(df) < 20:
        return "insufficient history (<20 bars)"
    floor_dv = min_avg_dollar_vol if min_avg_dollar_vol is not None else \
        getattr(config, "UNIVERSE_MIN_DOLLAR_VOL", 20_000_000.0)
    floor_px = min_price if min_price is not None else \
        getattr(config, "UNIVERSE_MIN_PRICE", 5.0)
    last_close = float(df["Close"].iloc[-1])
    if last_close < floor_px:
        return f"price {last_close:.2f} < {floor_px:.2f} floor"
    dv = _avg_dollar_vol(df)
    if dv < floor_dv:
        return f"avg dollar vol ${dv/1e6:.1f}M < ${floor_dv/1e6:.0f}M floor"
    return None
