"""Tradeable-universe utilities: liquidity screening (this task), universe
files + loaders (E13), ETF tagging (E14), data-quality rules (E16).

Liquidity is what makes the E11 slippage assumption honest: 5 bps is a
reasonable model for a $20M+/day name, a fantasy for a $500k/day one.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import os
from dataclasses import dataclass

import pandas as pd

from swingbot import config


def _avg_dollar_vol(df: pd.DataFrame, window: int = 20) -> float:
    tail = df.tail(window)
    return float((tail["Close"] * tail["Volume"]).mean())


def _volume_is_not_shares(symbol: str) -> bool:
    from swingbot.core.marketdata.asset_class import classify
    return classify(symbol) in _VOLUME_NOT_SHARES


def _dollar_volume_exempt(symbol: str | None) -> bool:
    """v115: which symbols skip the dollar-volume floor. v109 spot metals
    (spot_metals.SPOT_PAIRS, the single source of truth) always do: their bars
    carry the future's contract volume, and the partner kept them scanning
    (2026-09-30). 4a649b36's futures/FX/index exemption applies only while
    LIQUIDITY_EXEMPT_NON_EQUITY is on (default off = the 09-22 floor)."""
    if symbol is None:
        return False
    from swingbot.core.marketdata.spot_metals import is_spot_metal
    if is_spot_metal(symbol):
        return True
    return bool(config.LIQUIDITY_EXEMPT_NON_EQUITY) and _volume_is_not_shares(symbol)


def liquidity_ok(df: pd.DataFrame, min_avg_dollar_vol: float | None = None,
                  min_price: float | None = None) -> bool:
    return liquidity_reason(df, min_avg_dollar_vol, min_price) is None


#: Asset classes whose Yahoo "Volume" is not a share count: futures report
#: contracts (SI=F is 5,000 oz each), FX and indices report 0. Close x Volume
#: is meaningless for them, so only the history and price floors apply.
#: v109: spot metals carry their future's contract volume unchanged.
_VOLUME_NOT_SHARES = frozenset({"future", "fx", "index", "spot_metal"})


def liquidity_reason(df: pd.DataFrame, min_avg_dollar_vol: float | None = None,
                      min_price: float | None = None,
                      symbol: str | None = None) -> str | None:
    """None when liquid; else a loggable reason string. Passing `symbol`
    always exempts v109 spot metals from the dollar-volume floor, and exempts
    futures/FX/indices only while LIQUIDITY_EXEMPT_NON_EQUITY is on (v115;
    default off)."""
    if df is None or len(df) < 20:
        return "insufficient history (<20 bars)"
    floor_dv = min_avg_dollar_vol if min_avg_dollar_vol is not None else \
        getattr(config, "UNIVERSE_MIN_DOLLAR_VOL", 20_000_000.0)
    floor_px = min_price if min_price is not None else \
        getattr(config, "UNIVERSE_MIN_PRICE", 5.0)
    last_close = float(df["Close"].iloc[-1])
    if last_close < floor_px:
        return f"price {last_close:.2f} < {floor_px:.2f} floor"
    if _dollar_volume_exempt(symbol):
        return None
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


# --- Dated short-lane snapshot (v118) ---------------------------------------
#
# Read-only adapter beside load(): the bearish extra lane needs "who was in the
# index on THIS date", never today's list projected backwards. None means the
# lane is skipped -- there is no fallback to the legacy sp500.json rows.

LIVE_SNAPSHOT_MAX_AGE_SESSIONS = 5  # fixed operational default, not a tuned knob
_SECTOR_HISTORY_FILE = "sp500_sector_history.csv"


@dataclass(frozen=True)
class ShortSnapshot:
    symbols: tuple[str, ...]
    membership_asof: str
    sector_of: dict[str, str]


def _sha256_file(path: str) -> str | None:
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return None


def _live_snapshot_meta_ok(meta: dict, day: str) -> bool:
    asof = meta.get("as_of")
    if not asof or asof > day or meta.get("source") != "manual_csv":
        return False
    digest = _sha256_file(os.path.join(UNIVERSE_DIR, "sp500.json"))
    if digest is None or meta.get("universe_sha256") != digest:
        return False
    from swingbot.core.market.session import nyse_calendar
    try:
        age = nyse_calendar().sessions_between(
            dt.date.fromisoformat(asof), dt.date.fromisoformat(day))
    except ValueError:
        return False
    return age is not None and age <= LIVE_SNAPSHOT_MAX_AGE_SESSIONS


def live_short_snapshot(day: str) -> ShortSnapshot | None:
    from swingbot.core.infra.jsonio import read_json
    meta = read_json(os.path.join(UNIVERSE_DIR, "sp500.snapshot.json"), {})
    if not isinstance(meta, dict) or not _live_snapshot_meta_ok(meta, day):
        return None
    rows = load("sp500")
    return ShortSnapshot(tuple(r["symbol"] for r in rows), meta["as_of"],
                         {r["symbol"]: r["sector"] for r in rows})


def _load_sector_intervals(path: str) -> dict[str, list[tuple[str, str, str]]]:
    from swingbot.core.marketdata.pit_membership import OPEN_END, normalize_symbol
    try:
        with open(path, newline="", encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
    except OSError:
        return {}
    out: dict[str, list[tuple[str, str, str]]] = {}
    for row in rows:
        sym = normalize_symbol(row.get("ticker") or "")
        start = (row.get("start_date") or "").strip()
        sector = (row.get("sector") or "").strip()
        if sym and start and sector:
            end = (row.get("end_date") or "").strip() or OPEN_END
            out.setdefault(sym, []).append((start, end, sector))
    return out


def _sector_on(day: str, spans: list[tuple[str, str, str]]) -> str | None:
    for start, end, sector in spans:
        if start <= day < end:
            return sector
    return None


def historical_short_snapshot(day: str) -> ShortSnapshot | None:
    from swingbot.core.marketdata.pit_membership import is_member, load_intervals
    intervals = load_intervals(os.path.join(UNIVERSE_DIR, "sp500_membership.csv"))
    sectors = _load_sector_intervals(os.path.join(UNIVERSE_DIR, _SECTOR_HISTORY_FILE))
    if not intervals or not sectors:
        return None
    symbols = tuple(sorted(s for s, spans in intervals.items() if is_member(day, spans)))
    sector_of = {s: sec for s in symbols
                 if (sec := _sector_on(day[:10], sectors.get(s, []))) is not None}
    return ShortSnapshot(symbols, day[:10], sector_of)


def short_snapshot(day: str, *, live: bool) -> ShortSnapshot | None:
    """Dated membership + sector for the bearish extra lane, or None (skip)."""
    return live_short_snapshot(day) if live else historical_short_snapshot(day)


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
