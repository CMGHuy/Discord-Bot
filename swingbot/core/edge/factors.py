"""Signal-quality factors: relative strength (this task), sector RS (E26),
multi-timeframe alignment (E27), breadth (E28), intraday confirmation
(E29), candle quality at levels (E34). Pure functions over DataFrames --
the scan supplies data, the fold harness supplies judgment."""
from __future__ import annotations

import datetime as dt
import os

import numpy as np
import pandas as pd

from swingbot import config
from swingbot.core.jsonio import atomic_write_json, read_json

RS_WINDOW = 63  # ~3 months of trading days
RS_CACHE_PATH = os.path.join(config.DATA_DIR, "universe", "rs_cache.json")


def relative_return(ticker_df: pd.DataFrame, spy_df: pd.DataFrame,
                    window: int = RS_WINDOW) -> float | None:
    if ticker_df is None or spy_df is None or len(ticker_df) < window + 1 or len(spy_df) < window + 1:
        return None
    t = float(ticker_df["Close"].iloc[-1] / ticker_df["Close"].iloc[-window - 1] - 1.0)
    s = float(spy_df["Close"].iloc[-1] / spy_df["Close"].iloc[-window - 1] - 1.0)
    return t - s


def rs_percentile(ticker_df: pd.DataFrame, spy_df: pd.DataFrame,
                  window: int = RS_WINDOW,
                  universe_rels: list | None = None) -> float:
    rel = relative_return(ticker_df, spy_df, window)
    if rel is None or not universe_rels:
        return 50.0
    rels = [r for r in universe_rels if r is not None]
    if not rels:
        return 50.0
    return float(round(100.0 * np.mean([rel >= r for r in rels]), 1))


def refresh_rs_cache(universe_dfs: dict, spy_df: pd.DataFrame) -> dict:
    cache = {"as_of": dt.date.today().isoformat(),
             "rels": {sym: relative_return(df, spy_df)
                      for sym, df in universe_dfs.items()}}
    atomic_write_json(RS_CACHE_PATH, cache)
    return cache


def load_rs_cache() -> dict:
    return read_json(RS_CACHE_PATH, {"as_of": None, "rels": {}})


def sector_rs_percentile(sector: str, sector_etf_dfs: dict, spy_df,
                         sector_of_etf: dict | None = None,
                         window: int = RS_WINDOW) -> float:
    if sector_of_etf is None:
        from swingbot.core.universe import sector_map
        sector_of_etf = sector_map("etfs")
    rels = {}
    for etf, df in sector_etf_dfs.items():
        rel = relative_return(df, spy_df, window)
        if rel is not None:
            rels[sector_of_etf.get(etf)] = rel
    mine = rels.get(sector)
    if mine is None or len(rels) < 2:
        return 50.0
    return float(round(100.0 * np.mean([mine >= r for r in rels.values()]), 1))


def rs_score(ticker_pctile: float, sector_pctile: float) -> float:
    """Combined RS: the stock carries most of the signal, its sector tide
    the rest. Weights are frozen constants, not tunables."""
    return 0.7 * ticker_pctile + 0.3 * sector_pctile


def weekly_frame(daily_df: pd.DataFrame) -> pd.DataFrame:
    return daily_df.resample("W-FRI").agg(
        {"Open": "first", "High": "max", "Low": "min",
         "Close": "last", "Volume": "sum"}).dropna()


def _swing_lows(series: pd.Series, span: int = 2) -> list:
    vals = series.values
    return [vals[i] for i in range(span, len(vals) - span)
            if vals[i] == min(vals[i - span:i + span + 1])]


def mtf_alignment(daily_df: pd.DataFrame, direction: str) -> int:
    """0-3: how many higher-timeframe boxes this direction ticks. Weekly
    context is resampled from daily -- same data, longer lens."""
    w = weekly_frame(daily_df)
    if len(w) < 15:
        return 0
    bull = direction == "bullish"
    score = 0

    ema10 = w["Close"].ewm(span=10, adjust=False).mean()
    ema_rising = ema10.iloc[-1] > ema10.iloc[-4]
    above = w["Close"].iloc[-1] > ema10.iloc[-1]
    if (above and ema_rising) if bull else (not above and not ema_rising):
        score += 1

    lows = _swing_lows(w["Low"].iloc[:-1])   # completed weeks only
    highs = [-v for v in _swing_lows(-w["High"].iloc[:-1])]
    if bull and len(lows) >= 2 and lows[-1] > lows[-2]:
        score += 1
    if not bull and len(highs) >= 2 and highs[-1] < highs[-2]:
        score += 1

    prev = w.iloc[-2]
    pivot = (prev["High"] + prev["Low"] + prev["Close"]) / 3.0
    daily_close = float(daily_df["Close"].iloc[-1])
    if (daily_close > pivot) if bull else (daily_close < pivot):
        score += 1
    return score


BREADTH_MIN_TICKERS = 20


def breadth_pct_above_50ema(universe_dfs: dict) -> float | None:
    """Market internals: % of the scanned universe above its own 50-EMA.
    An index made of its members, not of cap-weighted illusions."""
    above = total = 0
    for df in universe_dfs.values():
        if df is None or len(df) < 60:
            continue
        ema50 = df["Close"].ewm(span=50, adjust=False).mean()
        total += 1
        above += bool(df["Close"].iloc[-1] > ema50.iloc[-1])
    if total < BREADTH_MIN_TICKERS:
        return None
    return round(100.0 * above / total, 1)


def intraday_confirms(symbol: str, direction: str,
                      intraday_df: "pd.DataFrame | None" = None,
                      fetch=None) -> bool | None:
    """Last 1h close vs today's running VWAP. None = no data = NEUTRAL --
    this annotation may inform the operator, never gate an alert, and is
    deliberately absent from the backtest (no honest intraday history)."""
    if intraday_df is None:
        if fetch is None:
            from swingbot.core.data_store import get_intraday
            fetch = get_intraday
        intraday_df = fetch(symbol)
    if intraday_df is None or intraday_df.empty:
        return None
    last_day = intraday_df.index[-1].date()
    day = intraday_df[intraday_df.index.date == last_day]
    if day.empty or day["Volume"].sum() <= 0:
        return None
    tp = (day["High"] + day["Low"] + day["Close"]) / 3.0
    vwap = float((tp * day["Volume"]).cumsum().iloc[-1] / day["Volume"].cumsum().iloc[-1])
    above = float(day["Close"].iloc[-1]) >= vwap
    return above if direction == "bullish" else not above
