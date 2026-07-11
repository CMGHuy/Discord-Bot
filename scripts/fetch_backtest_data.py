#!/usr/bin/env python3
"""One-time OHLCV cache for the redesign backtests. Downloads every
watchlist ticker 2018-06-01 -> 2025-12-31 (>=18 months warm-up before the
2020 train window: the regime gate needs 200-SMA + a 120-bar shift) and
saves one CSV per ticker under data/backtest_cache/. Re-running skips
tickers already cached; delete the folder to force a refresh."""
import json
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
import yfinance as yf

CACHE_DIR = ROOT / "data" / "backtest_cache"
START, END = "2018-06-01", "2025-12-31"


def load_watchlist() -> list[str]:
    return json.loads((ROOT / "data" / "watchlist.json").read_text())


def cache_path(ticker: str) -> Path:
    safe = ticker.replace("=", "_").replace("^", "_").replace("/", "_")
    return CACHE_DIR / f"{safe}.csv"


def load_cached(ticker: str) -> pd.DataFrame | None:
    p = cache_path(ticker)
    if not p.exists():
        return None
    df = pd.read_csv(p, index_col="Date", parse_dates=True)
    return df if len(df) else None


def fetch(ticker: str) -> pd.DataFrame | None:
    df = yf.download(ticker, start=START, end=END, auto_adjust=True, progress=False)
    if df is None or df.empty or len(df) < 260:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
    df.index = pd.to_datetime(df.index)
    df.index.name = "Date"
    return df


def main():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tickers = load_watchlist()
    ok, skipped, failed = 0, 0, []
    for t in sorted(tickers):
        if cache_path(t).exists():
            skipped += 1
            continue
        df = fetch(t)
        if df is None:
            print(f"  x {t}: no data")
            failed.append(t)
            continue
        df.to_csv(cache_path(t))
        ok += 1
        print(f"  + {t}: {len(df)} bars ({df.index[0].date()} -> {df.index[-1].date()})")
    print(f"\nDone: {ok} fetched, {skipped} already cached, {len(failed)} failed {failed or ''}")


if __name__ == "__main__":
    main()
