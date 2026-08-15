#!/usr/bin/env python3
"""Bulk OHLCV cache for every watchlist ticker at one timeframe, with a
per-ticker coverage report.

For routine top-ups prefer the bot's own auto-refresh
(`swingbot.core.marketdata.data_refresh`, wired to the `market_data_refresh` task loop)
or `refresh_all()` directly -- both are incremental. This script exists for
the cold-start/audit case: it re-fetches at full depth and PRINTS what each
ticker actually got versus its real listing date, which is how the Yahoo
depth ceiling was measured in the first place.

Writes market_data/{timeframe}/{TICKER}.csv via data_store.cache_path, so
anything cached here is immediately readable by get_intraday and the rest of
the bot.

HARD LIMIT (Yahoo's, not ours): 60m/1h bars are only served for the trailing
~730 days. There is no "since IPO" hourly history available from this source
at any price tier we use -- see the module docstring of
swingbot/core/marketdata/data_store.py. This script pulls the maximum Yahoo actually
has and reports each ticker's real coverage window so the gap is visible
rather than implied.

A ticker whose coverage starts AFTER the 730-day floor is genuinely complete
from its IPO/listing date; one that starts AT the floor is truncated by Yahoo.

    python scripts/data/fetch_intraday_cache.py                    # watchlist, hourly
    python scripts/data/fetch_intraday_cache.py --interval 30min   # 30min (60-day cap)
    python scripts/data/fetch_intraday_cache.py --force            # ignore existing cache
"""
import argparse
import datetime as dt
import json
import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd
import yfinance as yf

from swingbot.core.marketdata.data_store import (
    DATA_DIR,
    TIMEFRAMES,
    _normalize_columns,
    cache_path,
    load_from_disk,
    save_to_disk,
    timeframe_name,
    yf_interval,
)
from swingbot.core.marketdata.ticker_utils import candidate_symbols


def load_watchlist() -> list[str]:
    return json.loads((ROOT / "data" / "watchlist.json").read_text())


def max_days_for(timeframe: str) -> int:
    cfg = TIMEFRAMES[timeframe]
    if cfg["max_days"] is None:
        raise SystemExit(
            f"'{timeframe}' is a daily-or-coarser timeframe with full history; "
            "use the bot's auto-refresh or scripts/data/fetch_backtest_data.py."
        )
    return cfg["max_days"]


def _attempts(max_days: int):
    """Request shapes to try, widest first.

    `period=<max_days>d` empirically returns MORE than max_days of calendar
    history for established tickers (Yahoo appears to serve ~730 *trading*
    days), so it is tried first. But for a ticker that listed inside the
    window, yfinance clamps the start to the listing date and Yahoo then
    rejects the whole request ("range must be within the last 730 days") --
    so an explicit, safely-inside-the-window start/end is the fallback that
    makes recent IPOs work at all.
    """
    now = dt.datetime.now(dt.timezone.utc)
    safe_start = now - dt.timedelta(days=max_days - 2)
    return [
        {"period": f"{max_days}d"},
        {"start": safe_start.strftime("%Y-%m-%d"), "end": now.strftime("%Y-%m-%d")},
        {"period": "1y"},
    ]


def fetch_one(ticker: str, interval: str, max_days: int, retries: int = 2):
    """Return (df, resolved_symbol) or (None, reason)."""
    last_err = "no data returned"
    for symbol in candidate_symbols(ticker):
        for kwargs in _attempts(max_days):
            for attempt in range(retries):
                try:
                    df = yf.download(
                        symbol,
                        interval=yf_interval(interval),
                        auto_adjust=True,
                        progress=False,
                        **kwargs,
                    )
                except Exception as exc:
                    last_err = f"{type(exc).__name__}: {exc}"
                    time.sleep(2 * (attempt + 1))
                    continue
                if df is not None and not df.empty:
                    return _normalize_columns(df), symbol
                last_err = f"empty frame ({kwargs})"
                break
    return None, last_err


def listing_dates() -> dict:
    """First daily bar per ticker from the existing daily cache -- free, no
    network. The cache starts 2018-06-01, so a ticker whose daily history
    begins meaningfully after that listed then and its date is a real
    listing date; one starting at the cache floor listed at or before it and
    its true IPO is unknown from this source."""
    from swingbot.core.marketdata.backtest_cache import CACHE_DIR

    out = {}
    cache = Path(CACHE_DIR)
    if not cache.exists():
        return out
    for csv in cache.glob("*.csv"):
        try:
            idx = pd.read_csv(csv, index_col=0, parse_dates=True,
                              usecols=[0]).index
            if len(idx):
                out[csv.stem.upper()] = idx.min()
        except Exception:
            continue
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", default="1h")
    ap.add_argument("--force", action="store_true",
                    help="re-fetch even if a CSV already exists")
    ap.add_argument("--sleep", type=float, default=1.0,
                    help="seconds between tickers (rate-limit courtesy)")
    ap.add_argument("--base-dir", default=DATA_DIR)
    args = ap.parse_args()

    interval = timeframe_name(args.interval)   # accepts "1h" or "hourly"
    max_days = max_days_for(interval)
    tickers = load_watchlist()
    listed = listing_dates()
    # The daily cache's own earliest date across all tickers. A ticker
    # sitting ON that floor may simply be cache-truncated, so its first bar
    # is NOT evidence of a listing date; one clear of it genuinely listed then.
    cache_floor = min(listed.values()) if listed else pd.Timestamp("2018-06-01")

    print(f"tickers={len(tickers)} interval={interval} "
          f"yahoo_cap~{max_days}d dest={args.base_dir}/")
    print(f"{'TICKER':<8} {'ROWS':>7}  {'FROM':<12} {'TO':<12} {'LISTED':<12} NOTE")
    print("-" * 78)

    ok, failed, skipped, complete = [], [], [], []

    def report(ticker, df, note):
        start, end = df.index.min(), df.index.max()
        lst = listed.get(ticker.upper())
        # Only call it a real listing date if it is clear of the daily
        # cache's own 2018-06-01 floor -- otherwise we simply don't know.
        if lst is not None and lst > cache_floor + pd.Timedelta(days=5):
            lst_s = str(lst)[:10]
            # tz-naive compare; hourly index may carry an exchange tz
            if pd.Timestamp(str(start)[:10]) <= lst + pd.Timedelta(days=3):
                note = "COMPLETE from listing"
                complete.append(ticker)
        else:
            lst_s = "<=2018-06"
        print(f"{ticker:<8} {len(df):>7}  {str(start)[:10]:<12} "
              f"{str(end)[:10]:<12} {lst_s:<12} {note}")

    for ticker in tickers:
        path = Path(cache_path(ticker, interval, base_dir=args.base_dir))
        if path.exists() and not args.force:
            existing = load_from_disk(ticker, interval, base_dir=args.base_dir)
            if existing is not None and not existing.empty:
                skipped.append(ticker)
                report(ticker, existing, "cached (--force to refetch)")
                continue

        df, info = fetch_one(ticker, interval, max_days)
        if df is None:
            failed.append((ticker, info))
            print(f"{ticker:<8} {'-':>7}  {'-':<12} {'-':<12} "
                  f"{'-':<12} FAILED: {str(info)[:60]}")
            time.sleep(args.sleep)
            continue

        save_to_disk(df, ticker, interval, base_dir=args.base_dir)
        ok.append(ticker)
        report(ticker, df, "truncated by Yahoo cap"
               + (f" [resolved {info}]" if info != ticker else ""))
        time.sleep(args.sleep)

    print("-" * 78)
    print(f"done: {len(ok)} fetched, {len(skipped)} already cached, "
          f"{len(failed)} failed")
    if failed:
        print("failed tickers:")
        for t, why in failed:
            print(f"  {t}: {str(why)[:100]}")
    print(f"\n{len(complete)} ticker(s) have COMPLETE hourly history from "
          f"their listing date (they listed inside Yahoo's window):")
    print("  " + (", ".join(complete) if complete else "none"))
    print(f"\nEvery other ticker is TRUNCATED, not complete from IPO: Yahoo "
          f"serves\n{interval} bars for only ~{max_days} trading days. "
          f"Hourly history before that is\nnot available from this source "
          f"at any tier -- daily bars (fetch_backtest_data.py)\nare the only "
          f"full-history option.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
