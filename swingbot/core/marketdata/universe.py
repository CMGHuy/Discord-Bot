"""Tradeable-universe utilities: liquidity screening (this task), universe
files + loaders (E13), ETF tagging (E14), data-quality rules (E16).

Liquidity is what makes the E11 slippage assumption honest: 5 bps is a
reasonable model for a $20M+/day name, a fantasy for a $500k/day one.
"""
from __future__ import annotations

import json
import os

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


# --- Universe files + loaders (E13) ---------------------------------------
#
# Named universe files under UNIVERSE_DIR (data/universe/*.json), each a
# JSON list of {"symbol", "name", "sector", "etf"} rows. `sp500+etfs`-style
# names concatenate multiple files. Unknown/missing names load as [] so the
# scanner's SCAN_UNIVERSE-driven extension (engine.py's _sync_run_scan)
# degrades safely to "just the watchlist" if a file hasn't been generated.

UNIVERSE_DIR = os.path.join(config.DATA_DIR, "universe")
_REQUIRED_KEYS = {"symbol", "name", "sector", "etf"}


def load(name: str) -> list[dict]:
    """Load a universe file, validated + deduped by symbol. `sp500+etfs`
    concatenates. Unknown or missing -> [] (scanning falls back to watchlist)."""
    if "+" in name:
        seen, out = set(), []
        for part in name.split("+"):
            for row in load(part):
                if row["symbol"] not in seen:
                    seen.add(row["symbol"]); out.append(row)
        return out
    path = os.path.join(UNIVERSE_DIR, f"{name}.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    seen, out = set(), []
    for row in raw:
        if not isinstance(row, dict) or not _REQUIRED_KEYS <= set(row):
            continue
        sym = str(row["symbol"]).upper()
        if sym in seen:
            continue
        seen.add(sym)
        out.append({"symbol": sym, "name": row["name"],
                    "sector": row["sector"], "etf": bool(row["etf"])})
    return out


def universe_symbols(name: str) -> list[str]:
    return [r["symbol"] for r in load(name)]


def sector_map(name: str) -> dict:
    return {r["symbol"]: r["sector"] for r in load(name)}


# --- ETF tagging (E14) ------------------------------------------------------
#
# ETFs/index funds don't report earnings; the earnings-proximity gate in
# events.py short-circuits on this instead of hitting Yahoo with a lookup
# that can never succeed. Cached per process across both universe files so
# it works whether the symbol only appears in etfs.json or was also folded
# into sp500.json.

_ETF_CACHE: set | None = None


def is_etf(symbol: str) -> bool:
    global _ETF_CACHE
    if _ETF_CACHE is None:
        cache = set()
        for name in ("etfs", "sp500"):
            for row in load(name):
                if row["etf"]:
                    cache.add(row["symbol"])
        _ETF_CACHE = cache
    return symbol.upper() in _ETF_CACHE


# --- Data-quality validator (E16) -------------------------------------------
#
# A sibling screen to liquidity_reason above: bad data makes every downstream
# number a lie, so this flags a ticker's cached df rather than trusting it.
# Wired into the same three call sites as the E12 liquidity skip (scanning/
# engine.py's _sync_run_scan, and both ticker loops in
# scripts/backtest/run_backtest_range.py) -- skip + log, same pattern.

# ~2 years of trading days -- generously covers the slowest indicator any
# swing horizon uses (EMA200 for the 6-month horizon) plus margin, same
# order of magnitude as DEFAULT_HISTORY_PERIOD's cold-fetch window. The
# market_data/ cache is deliberately allowed to grow far deeper than this
# over time (data_refresh.py's archive-outgrows-the-provider-window
# design), so a whole-dataframe scan of an old ticker's cache hits decades
# of history no live scan reads -- and real data-provider artifacts do live
# back there (PFE has an 18-day identical-close run in 1977). Checking only
# the trailing window keeps this screen about "is the feed reliable right
# now", which is the question it exists to answer.
QUALITY_CHECK_LOOKBACK_BARS = 500


def data_quality_issues(df: pd.DataFrame, symbol: str) -> list[str]:
    """Bad data makes every downstream number a lie -- flag, skip, report."""
    issues: list[str] = []
    if df is None or len(df) < 30:
        return [f"{symbol}: <30 bars of history"]

    df = df.tail(QUALITY_CHECK_LOOKBACK_BARS)
    close = df["Close"]
    # 1) frozen feed: >5 consecutive identical closes
    runs = (close != close.shift()).cumsum()
    if int(close.groupby(runs).transform("size").max()) > 5:
        issues.append(f"{symbol}: >5 consecutive identical closes (frozen feed?)")

    # 2) unadjusted split: >40% single-bar move without a >=3x volume spike
    move = close.pct_change().abs()
    vol_ratio = df["Volume"] / df["Volume"].rolling(20).mean().shift(1)
    suspicious = (move > 0.40) & ~(vol_ratio >= 3.0)
    if suspicious.fillna(False).any():
        d = df.index[suspicious.fillna(False)][0].date()
        issues.append(f"{symbol}: >40% bar on {d} without volume spike (bad split adjust?)")

    # 3) non-positive prices
    if (df[["Open", "High", "Low", "Close"]] <= 0).any().any():
        issues.append(f"{symbol}: non-positive price values")

    # 4) calendar holes > 10 days
    deltas = df.index.to_series().diff().dt.days.dropna()
    if (deltas > 10).any():
        issues.append(f"{symbol}: gap of {int(deltas.max())} calendar days in the index")
    return issues
