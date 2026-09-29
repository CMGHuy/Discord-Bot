"""Frozen OHLCV for the backtest parity tests (2018-06-01..2025-12-30).

Byte copies of ``data/backtest_cache/{TSLA,DOCU,DELL}.csv`` taken 2026-09-28.
That cache is gitignored, so tests reading it skipped on CI; these files ship
with the repo and never move under a cache refresh.

``PARITY_CASES`` lists every (ticker, strategy, horizon) that yields at least
one trade and one comparable sizing bar on this data, chosen so every
strategy x {4w, 3m} pair the scanner can emit is exercised. Excluded:

* pairs ``STRATEGY_GATES`` masks by horizon (VWAP 3m, Support/Resistance 4w,
  MACD 4w, Volume Profile 4w/3m, Break & Retest 4w) -- no signal can exist;
* Elliott Wave 3m -- zero raw entry signals on all 75 cached tickers.

A strategy change that empties a case fails the test that asserts trades
exist; pick a replacement ticker rather than re-adding a skip.
"""
from pathlib import Path

import pandas as pd

OHLCV_DIR = Path(__file__).resolve().parent / "ohlcv"

PARITY_CASES = [
    ("TSLA", "EMA Crossover", "4w"), ("DELL", "EMA Crossover", "3m"),
    ("TSLA", "VWAP", "4w"), ("DOCU", "VWAP", "4w"), ("DELL", "VWAP", "4w"),
    ("DOCU", "Fibonacci", "4w"), ("DELL", "Fibonacci", "4w"),
    ("TSLA", "Fibonacci", "3m"), ("DOCU", "Fibonacci", "3m"),
    ("TSLA", "Support/Resistance", "3m"), ("DOCU", "Support/Resistance", "3m"),
    ("DELL", "Support/Resistance", "3m"),
    ("DOCU", "RSI", "4w"), ("DOCU", "RSI", "3m"),
    ("TSLA", "MACD", "3m"), ("DOCU", "MACD", "3m"),
    ("TSLA", "Elliott Wave", "4w"), ("DOCU", "Elliott Wave", "4w"), ("DELL", "Elliott Wave", "4w"),
    ("TSLA", "MA Ribbon", "4w"), ("DOCU", "MA Ribbon", "4w"), ("DELL", "MA Ribbon", "4w"),
    ("DELL", "MA Ribbon", "3m"),
    ("DELL", "Break & Retest", "3m"),
    ("TSLA", "RSI Divergence", "4w"), ("DOCU", "RSI Divergence", "4w"), ("DELL", "RSI Divergence", "4w"),
    ("TSLA", "RSI Divergence", "3m"), ("DOCU", "RSI Divergence", "3m"), ("DELL", "RSI Divergence", "3m"),
]


def load_ohlcv(ticker: str) -> pd.DataFrame:
    return pd.read_csv(OHLCV_DIR / f"{ticker}.csv", index_col="Date", parse_dates=True)
