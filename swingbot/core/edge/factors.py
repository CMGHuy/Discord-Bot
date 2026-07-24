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
