#!/usr/bin/env python3
"""One-time OHLCV cache for the redesign backtests. Downloads every
watchlist ticker over a date range (default 2018-06-01 -> 2025-12-31, giving
>=18 months warm-up before the 2020 train window: the regime gate needs a
200-SMA + a 120-bar shift) and saves one CSV per ticker under
data/backtest_cache/. Re-running skips tickers already cached; pass --force
(or delete the folder) to overwrite and re-fetch.

Range is configurable:
    python scripts/fetch_backtest_data.py --start 2010-01-01 --end today --force
'today' / 'now' for --end resolves to the current date. yfinance daily bars
go back decades; intraday (1h/1m) history is NOT available this far back."""
import argparse
import datetime as dt
import json
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
import yfinance as yf

# Cache location, filename scheme, and CSV shape are owned by the core module
# so this bulk populator and the auto-cache-on-add path can never drift.
from swingbot.core.backtest_cache import CACHE_DIR, cache_path, normalize_ohlcv

START, END = "2018-06-01", "2025-12-31"


def load_watchlist() -> list[str]:
    return json.loads((ROOT / "data" / "watchlist.json").read_text())


def load_cached(ticker: str) -> pd.DataFrame | None:
    p = cache_path(ticker)
    if not p.exists():
        return None
    df = pd.read_csv(p, index_col="Date", parse_dates=True)
    return df if len(df) else None


def fetch(ticker: str, start: str, end: str) -> pd.DataFrame | None:
    df = yf.download(ticker, start=start, end=end, auto_adjust=True, progress=False)
    if df is None or df.empty or len(df) < 260:
        return None
    return normalize_ohlcv(df)


def _resolve_end(end: str) -> str:
    if end.lower() in ("today", "now"):
        # yfinance end is exclusive; +1 day to include the latest complete bar
        return (dt.date.today() + dt.timedelta(days=1)).isoformat()
    return end


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", default=START, help=f"start date YYYY-MM-DD (default {START})")
    ap.add_argument("--end", default=END, help=f"end date YYYY-MM-DD, or 'today' (default {END})")
    ap.add_argument("--force", action="store_true", help="re-fetch and overwrite already-cached tickers")
    args = ap.parse_args()
    start, end = args.start, _resolve_end(args.end)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tickers = load_watchlist()
    print(f"Fetching {len(tickers)} tickers | {start} -> {end} | force={args.force}\n")
    ok, skipped, failed = 0, 0, []
    for t in sorted(tickers):
        if cache_path(t).exists() and not args.force:
            skipped += 1
            continue
        df = fetch(t, start, end)
        if df is None:
            print(f"  x {t}: no data (<260 bars or empty)")
            failed.append(t)
            continue
        df.to_csv(cache_path(t))
        ok += 1
        print(f"  + {t}: {len(df)} bars ({df.index[0].date()} -> {df.index[-1].date()})")
    print(f"\nDone: {ok} fetched, {skipped} already cached, {len(failed)} failed {failed or ''}")


if __name__ == "__main__":
    main()
