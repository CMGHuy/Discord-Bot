"""
Market regime filter.

Swing trades don't happen in a vacuum -- a bullish setup on an individual
stock is more likely to work if the broader market is also trending up,
and more likely to fail if it's fighting a market-wide downtrend. This
module checks a benchmark index (default SPY) against its 200-day EMA to
classify the overall regime as bullish or bearish, and whether that trend
is strengthening or weakening.

This is a single blunt filter, not a full macro model -- it doesn't know
about sector rotation, rates, or individual stock beta to the index.
"""
import os
from dataclasses import dataclass

import pandas as pd

from swingbot import config as app_config
from .indicators import ema

# Kept as a module-level alias for anything importing DEFAULT_REGIME_TICKER
# directly, but get_market_regime() below reads app_config.MARKET_REGIME_TICKER
# live so a config.reload() takes effect immediately, not just at import time.
DEFAULT_REGIME_TICKER = app_config.MARKET_REGIME_TICKER


@dataclass
class RegimeResult:
    ticker: str
    trend: str          # "bullish" | "bearish"
    close: float
    ema200: float
    pct_above_ema: float
    ema_slope_pct: float   # % change in the EMA200 itself over the last ~20 days (rising vs falling)
    label: str


def get_market_regime(df: pd.DataFrame, ticker: str = None) -> RegimeResult:
    ticker = ticker or app_config.MARKET_REGIME_TICKER
    if len(df) < 220:
        raise ValueError(f"Not enough history on {ticker} to compute a 200-day EMA regime (need 220+ bars).")

    close = df["Close"]
    ema200 = ema(close, 200)

    last_close = float(close.iloc[-1])
    last_ema = float(ema200.iloc[-1])
    pct_above = (last_close - last_ema) / last_ema * 100

    slope_pct = (last_ema - float(ema200.iloc[-20])) / float(ema200.iloc[-20]) * 100

    trend = "bullish" if last_close > last_ema else "bearish"
    strength = "rising" if slope_pct > 0 else "falling"
    label = f"{'Bullish' if trend == 'bullish' else 'Bearish'} ({ticker} {pct_above:+.1f}% vs {strength} 200EMA)"

    return RegimeResult(
        ticker=ticker, trend=trend, close=round(last_close, 2), ema200=round(last_ema, 2),
        pct_above_ema=round(pct_above, 2), ema_slope_pct=round(slope_pct, 3), label=label,
    )
