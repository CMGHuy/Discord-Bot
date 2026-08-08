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
go back decades; intraday (1h/1m) history is NOT available this far back.

--universe NAME (Task E15) is a SEPARATE, additive mode: it incrementally
updates market_data/ (watchlist + named universe, e.g. sp500) via
swingbot.core.data_store.update_cache -- fetching only new bars since each
symbol's last cached date, nightly-safe for 500+ symbols. This is a
DIFFERENT cache location from the default data/backtest_cache/ path above
(owned by swingbot.core.backtest_cache) and the two are NOT unified: today's
run_backtest_range.py / backtest_scenarios.py / this script's default mode
still only read data/backtest_cache/, not market_data/.
    python scripts/fetch_backtest_data.py --universe sp500"""
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


def load_universe_symbols(name: str) -> list[str]:
    """Watchlist ticker + named universe (e.g. sp500), deduped, sorted.
    Import kept local so the default no-flag path never touches this module."""
    from swingbot.core import universe
    symbols = set(load_watchlist()) | set(universe.universe_symbols(name))
    return sorted(symbols)


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
    # --universe is a SEPARATE, additive code path (Task E15). It does NOT
    # touch data/backtest_cache/ (owned by swingbot.core.backtest_cache and
    # read by run_backtest_range.py / backtest_scenarios.py / this script's
    # default no-flag mode above) -- it writes to market_data/ via
    # swingbot.core.data_store's incremental cache instead. The two caches
    # are NOT unified: today's grid/backtest scripts only read the former,
    # so --universe output isn't yet usable by them. This mirrors that gap
    # honestly rather than silently building an orphaned feature.
    ap.add_argument("--universe", metavar="NAME", default=None,
                     help="incrementally update market_data/ for watchlist + "
                          "named universe (e.g. 'sp500') via swingbot.core.data_store."
                          "update_cache -- a SEPARATE cache from the default "
                          "data/backtest_cache/ path above; not read by "
                          "run_backtest_range.py or other grid scripts yet")
    args = ap.parse_args()

    if args.universe:
        from swingbot.core.data_store import update_cache
        symbols = load_universe_symbols(args.universe)
        print(f"Incrementally updating market_data/ for {len(symbols)} symbols "
              f"(watchlist + universe='{args.universe}')\n"
              f"NOTE: this populates market_data/, a separate cache from "
              f"data/backtest_cache/ -- run_backtest_range.py and other grid "
              f"scripts do not read it yet.\n")
        result = update_cache(symbols)
        updated = sum(1 for n in result.values() if n > 0)
        total_new = sum(result.values())
        for sym, n in sorted(result.items()):
            if n:
                print(f"  + {sym}: {n} new bars")
        print(f"\nDone: {updated}/{len(symbols)} symbols updated, {total_new} new bars total")
        return

    start, end = args.start, _resolve_end(args.end)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tickers = load_watchlist()

    # The market-context benchmark (P0) is not necessarily on the watchlist,
    # but every backtest that gates on regime needs its history cached like
    # any other ticker. Without this the whole context channel is silently
    # unavailable in the one place that can actually measure it.
    from swingbot import config
    benchmark = config.MARKET_REGIME_TICKER
    if benchmark and benchmark not in tickers:
        tickers = list(tickers) + [benchmark]
        print(f"(+ {benchmark}: market-context benchmark, not on the watchlist)")

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
