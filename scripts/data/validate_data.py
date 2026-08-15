#!/usr/bin/env python3
"""Report data-quality issues (Task E16) across the local OHLCV cache.

Dual-mode, mirroring the E15 precedent in fetch_backtest_data.py's
--universe flag -- two caches exist in this repo and they are NOT unified:

  * default (no flag): validates data/backtest_cache/ (owned by
    swingbot.core.marketdata.backtest_cache, flat {TICKER}.csv files) -- the cache
    that today's actual grid/backtest scripts (run_backtest_range.py,
    backtest_scenarios.py) read. This is the meaningful mode: running it
    over the real, populated cache.
  * --universe NAME: validates market_data/ (owned by
    swingbot.core.marketdata.data_store, grouped by candle timeframe as
    {timeframe}/{TICKER}.csv, e.g. market_data/daily/AAPL.csv) for the
    watchlist + a named universe (e.g. sp500) -- data_store.py's intended
    future cache for the expanded universe, not yet read by any backtest
    script (same disclosed gap as fetch_backtest_data.py's --universe mode).

Run:
    python scripts/data/validate_data.py
    python scripts/data/validate_data.py --universe sp500
"""
import argparse
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from swingbot.core.marketdata.universe import data_quality_issues  # noqa: E402


def _validate_backtest_cache() -> int:
    """Default mode: data/backtest_cache/, flat {TICKER}.csv files, read the
    same way scripts/data/fetch_backtest_data.py's own load_cached() does."""
    import pandas as pd
    from swingbot.core.marketdata.backtest_cache import CACHE_DIR

    bad = 0
    checked = 0
    for path in sorted(glob.glob(os.path.join(str(CACHE_DIR), "*.csv"))):
        symbol = os.path.splitext(os.path.basename(path))[0]
        df = pd.read_csv(path, index_col="Date", parse_dates=True)
        checked += 1
        issues = data_quality_issues(df, symbol)
        for i in issues:
            print("ISSUE:", i)
        bad += bool(issues)
    print(f"done -- {checked} symbol(s) checked in {CACHE_DIR}, {bad} with issues")
    return bad


def _validate_universe_cache(name: str) -> int:
    """--universe NAME mode: market_data/daily/{TICKER}.csv, for the
    watchlist + named universe symbols (mirrors fetch_backtest_data.py's
    E15 --universe mode). "1d" below resolves to the daily/ folder."""
    from swingbot.core.marketdata.data_store import DATA_DIR, load_from_disk
    from swingbot.core.marketdata import universe as universe_mod

    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "scripts", "data"))
    from fetch_backtest_data import load_watchlist  # noqa: E402

    symbols = sorted(set(load_watchlist()) | set(universe_mod.universe_symbols(name)))
    bad = 0
    checked = 0
    for symbol in symbols:
        df = load_from_disk(symbol, "1d", base_dir=DATA_DIR)
        if df is None:
            continue
        checked += 1
        issues = data_quality_issues(df, symbol)
        for i in issues:
            print("ISSUE:", i)
        bad += bool(issues)
    print(f"done -- {checked}/{len(symbols)} symbol(s) checked in {DATA_DIR} "
          f"(watchlist + universe='{name}'), {bad} with issues")
    return bad


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--universe", metavar="NAME", default=None,
                     help="validate market_data/ for watchlist + named universe "
                          "instead of the default data/backtest_cache/")
    args = ap.parse_args()

    if args.universe:
        n_bad = _validate_universe_cache(args.universe)
    else:
        n_bad = _validate_backtest_cache()
