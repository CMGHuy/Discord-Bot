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
from swingbot.core.infra.jsonio import atomic_write_json, read_json

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
        from swingbot.core.marketdata.universe import sector_map
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
            from swingbot.core.marketdata.data_store import get_intraday
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


def anchored_vwap(df: pd.DataFrame, anchor_idx: int) -> pd.Series:
    """Volume-weighted average price anchored at a specific bar -- the
    market's own average cost since that event. Institutions defend it;
    that's why it acts as support/resistance."""
    part = df.iloc[anchor_idx:]
    tp = (part["High"] + part["Low"] + part["Close"]) / 3.0
    return (tp * part["Volume"]).cumsum() / part["Volume"].cumsum()


def avwap_anchors(df: pd.DataFrame, lookback: int = 120) -> list:
    """Anchor bars that mean something: recent swing pivots + the highest-
    volume day (a capitulation/breakout bar everyone remembers).

    Pivots need `span` bars of confirmation on BOTH sides, so the scan
    stops `span` bars short of the end -- an unconfirmed low that is only
    a low because the data ran out is not a swing low. That also keeps
    this side of the no-lookahead rule: every bar this reads is at or
    before the frame's last bar, and no anchor depends on a bar that
    hadn't printed yet when the anchor formed."""
    n = len(df)
    start = max(0, n - lookback)
    lows, highs = df["Low"].values, df["High"].values
    anchors = set()
    span = 5
    pivots_lo = [i for i in range(max(start, span), n - span)
                 if lows[i] == min(lows[i - span:i + span + 1])]
    pivots_hi = [i for i in range(max(start, span), n - span)
                 if highs[i] == max(highs[i - span:i + span + 1])]
    anchors.update(pivots_lo[-2:])
    anchors.update(pivots_hi[-2:])
    anchors.add(start + int(df["Volume"].values[start:].argmax()))
    return sorted(anchors)


def pattern_quality_at_level(df: pd.DataFrame, idx: int, level: float,
                             direction: str = "bullish") -> int:
    """0-10 quality of the level-touch bar. Rewards conviction closes,
    participation (volume), and an actual rejection wick THROUGH the
    level -- the difference between a bounce and a drift.

    A SCORE COMPONENT (consumed by E37's composite), never a hard filter:
    a low score describes a weak touch, it does not veto a setup."""
    bar = df.iloc[idx]
    rng = float(bar["High"] - bar["Low"])
    if rng <= 0:
        return 0
    bull = direction == "bullish"

    # 1) close position in range: 0 (worst) .. 4 (closes at the favorable extreme)
    pos = (bar["Close"] - bar["Low"]) / rng
    pos = pos if bull else 1.0 - pos
    score = round(4 * pos)

    # 2) volume vs 20-bar average: >=2.5x -> 3, >=1.5x -> 2, >=1.0x -> 1
    vol_avg = float(df["Volume"].iloc[max(0, idx - 20):idx].mean() or 0)
    ratio = float(bar["Volume"]) / vol_avg if vol_avg > 0 else 0.0
    score += 3 if ratio >= 2.5 else 2 if ratio >= 1.5 else 1 if ratio >= 1.0 else 0

    # 3) wick rejection through the level: pierced it AND closed back beyond it.
    # Both halves matter -- piercing and CLOSING through is a break, not a
    # rejection, and must not score like a bounce.
    pierced = bar["Low"] <= level if bull else bar["High"] >= level
    reclaimed = bar["Close"] > level if bull else bar["Close"] < level
    if pierced and reclaimed:
        wick = (level - bar["Low"]) if bull else (bar["High"] - level)
        score += 3 if wick / rng >= 0.25 else 2
    return int(min(score, 10))
