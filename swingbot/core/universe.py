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
