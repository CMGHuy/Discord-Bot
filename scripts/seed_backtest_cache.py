#!/usr/bin/env python3
"""Bridge market_data/daily/ -> data/backtest_cache/, no network (plan v8, Task V1).

The live server has 25 years of daily OHLCV under market_data/daily/ (fetched
by swingbot.core.data_store, one CSV per ticker, columns
Date,Close,High,Low,Open,Volume) but every backtest/tuning/walk-forward
script reads data/backtest_cache/ (owned by swingbot.core.backtest_cache,
canonical Date-index + Open/High/Low/Close/Volume shape) -- the two-cache
trap documented in docs/claude/known-traps.md. This script is a pure local
transform between the two: it does NOT call yfinance and should never touch
the network. Do not use scripts/fetch_backtest_data.py for this -- it
re-downloads from Yahoo, which is unnecessary (the data is already on disk)
and, per docs/claude/known-traps.md's cache-overwrite trap, actively
dangerous for hourly (not used here, but the same destructive-overwrite
pattern applies to any bulk download-and-cache call).

Ticker sanitization is shared with both caches via
swingbot.core.data_store.safe_symbol (`GC=F` -> `GC_F.csv` in both), so this
script never hand-builds a path.

Never shrinks an existing data/backtest_cache/ file: if the destination
already has more bars than the market_data source would produce, the write
is refused and reported, not silently overwritten. Pass --force to override.

    python scripts/seed_backtest_cache.py              # bridge every watchlist ticker
    python scripts/seed_backtest_cache.py --dry-run     # report only, write nothing
    python scripts/seed_backtest_cache.py --force       # allow the destination to shrink
"""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from swingbot.core.backtest_cache import BACKTEST_MIN_BARS, CACHE_DIR, normalize_ohlcv
from swingbot.core.data_store import safe_symbol

DEFAULT_MARKET_DATA_DAILY = ROOT / "market_data" / "daily"


def load_watchlist() -> list[str]:
    return json.loads((ROOT / "data" / "watchlist.json").read_text())


def bridge_one(ticker: str, market_dir: Path, cache_dir: Path, *,
                force: bool = False, dry_run: bool = False) -> dict:
    """Bridge one ticker's market_data/daily CSV into cache_dir's canonical
    backtest_cache shape. Never shrinks an existing cache file unless
    force=True. Returns a result dict, never raises on missing/bad input."""
    src = market_dir / f"{safe_symbol(ticker)}.csv"
    if not src.exists():
        return {"ticker": ticker, "status": "missing", "bars": 0,
                "note": f"no market_data file at {src}"}

    raw = pd.read_csv(src, index_col="Date", parse_dates=True)
    if raw.empty:
        return {"ticker": ticker, "status": "missing", "bars": 0, "note": "empty source file"}

    df = normalize_ohlcv(raw)
    if df is None or df.empty:
        return {"ticker": ticker, "status": "missing", "bars": 0,
                "note": "normalize_ohlcv failed (missing OHLCV columns)"}

    dest = cache_dir / f"{safe_symbol(ticker)}.csv"
    if dest.exists() and not force:
        existing = pd.read_csv(dest, index_col="Date", parse_dates=True)
        if len(existing) > len(df):
            return {"ticker": ticker, "status": "refused_shrink", "bars": len(existing),
                     "note": f"cache already has {len(existing)} bars, "
                             f"market_data source has only {len(df)} -- pass --force to override"}

    short_note = "" if len(df) >= BACKTEST_MIN_BARS else f"only {len(df)} bars -- too short to backtest yet"
    if not dry_run:
        cache_dir.mkdir(parents=True, exist_ok=True)
        df.to_csv(dest)

    return {
        "ticker": ticker,
        "status": "short" if len(df) < BACKTEST_MIN_BARS else "ok",
        "bars": len(df),
        "note": short_note,
        "start": str(df.index.min().date()),
        "end": str(df.index.max().date()),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--market-data-dir", default=str(DEFAULT_MARKET_DATA_DAILY),
                     help=f"source directory (default {DEFAULT_MARKET_DATA_DAILY})")
    ap.add_argument("--cache-dir", default=str(CACHE_DIR),
                     help=f"destination directory (default {CACHE_DIR})")
    ap.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    ap.add_argument("--force", action="store_true",
                     help="allow the destination to shrink (normally refused)")
    args = ap.parse_args()

    market_dir = Path(args.market_data_dir)
    cache_dir = Path(args.cache_dir)
    tickers = sorted(load_watchlist())

    print(f"Bridging {len(tickers)} tickers: {market_dir} -> {cache_dir}  "
          f"(dry_run={args.dry_run}, force={args.force})\n", flush=True)

    counts = {"ok": 0, "short": 0, "missing": 0, "refused_shrink": 0}
    missing_tickers, refused_tickers = [], []

    for t in tickers:
        r = bridge_one(t, market_dir, cache_dir, force=args.force, dry_run=args.dry_run)
        counts[r["status"]] += 1
        if r["status"] == "missing":
            missing_tickers.append(t)
            print(f"  x {t}: {r['note']}", flush=True)
        elif r["status"] == "refused_shrink":
            refused_tickers.append(t)
            print(f"  ! {t}: {r['note']}", flush=True)
        else:
            verb = "would write" if args.dry_run else "wrote"
            flag = f" [{r['note']}]" if r["note"] else ""
            print(f"  + {t}: {verb} {r['bars']} bars ({r['start']} -> {r['end']}){flag}", flush=True)

    print(f"\nDone: {counts['ok']} ok, {counts['short']} too-short-to-backtest "
          f"(<{BACKTEST_MIN_BARS} bars), {counts['missing']} missing, "
          f"{counts['refused_shrink']} refused-shrink")
    if missing_tickers:
        print(f"  missing: {missing_tickers}")
    if refused_tickers:
        print(f"  refused-shrink (pass --force to override): {refused_tickers}")


if __name__ == "__main__":
    main()
