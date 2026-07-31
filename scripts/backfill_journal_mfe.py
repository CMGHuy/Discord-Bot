#!/usr/bin/env python3
"""Backfill corrupted MFE/MAE journal entries (plan v8, Task V3).

`mfe_r` was None/NaN in ~19% of journal entries and negative in a handful
more -- impossible by definition, since MFE (favorable excursion) cannot go
below zero. Root cause: `journal_trade_close` (analytics/journal.py) sources
its OHLCV via a LIVE, unguarded `yf.download()` call
(`swingbot.core.data.get_daily_data`) at the moment a trade closes. A
transient network failure there produces `df=None` -> `mfe_r=None`; a
transient bad/glitchy Yahoo snapshot can produce nonsensical values (one
live case computed mfe_r=-1845.95). Separately, `compute_mfe_mae` itself had
an asymmetric bug: `mae_r` was clamped to `>= 0` but `mfe_r` was not, so
same-day trades whose single daily bar never re-touched entry could
legitimately compute a small negative mfe_r (both bugs fixed together:
mfe_mae.py's clamp, and this script backfilling from the network-free local
cache instead of re-hitting a possibly-still-flaky live source).

This script recomputes ONLY the journal entries whose mfe_r is currently
None/NaN/negative, using `data/backtest_cache/` (bridged from market_data/
by Task V1 -- offline, deterministic, already covers every watchlist
ticker) instead of a live yfinance call. It reuses `journal.build_entry`
exactly -- the same function `journal_trade_close` calls -- so a backfilled
entry is indistinguishable from one written correctly the first time. The
one user-entered `note` field found in the live journal is preserved
across the rewrite; every other field is freshly recomputed (including
`tags`, since a corrupted mfe_r could have produced an incorrect
`near_miss_tp` tag).

A small number of entries cannot be fixed by this script: journal entries
whose `trade_id` has no matching record in trades.json at all (a separate,
newly-discovered data-integrity gap -- see plan v8 Task V45). Those are
reported, not silently skipped.

    python scripts/backfill_journal_mfe.py              # apply
    python scripts/backfill_journal_mfe.py --dry-run     # report only
"""
import argparse
import json
import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from swingbot import config
from swingbot.core.analytics.journal import JournalStore, build_entry
from swingbot.core.backtest_cache import cache_path


def is_corrupt(mfe_r) -> bool:
    """None, NaN, or negative -- the three impossible states for MFE."""
    if mfe_r is None:
        return True
    if isinstance(mfe_r, float) and math.isnan(mfe_r):
        return True
    return mfe_r < 0


def load_cached_daily(ticker: str) -> pd.DataFrame | None:
    """Read the ticker's bridged backtest_cache CSV. Network-free, unlike
    get_daily_data. Returns None (graceful degradation, matches
    build_entry's documented contract) if the file is missing or empty."""
    p = cache_path(ticker)
    if not p.exists():
        return None
    df = pd.read_csv(p, index_col="Date", parse_dates=True)
    return df if len(df) else None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    args = ap.parse_args()

    trades_path = Path(config.DATA_DIR) / "trades.json"
    trades_by_id = {t["id"]: t for t in json.loads(trades_path.read_text())}

    store = JournalStore()
    entries = store.entries()
    print(f"Loaded {len(entries)} journal entries, {len(trades_by_id)} trade records\n", flush=True)

    corrupt = [e for e in entries if is_corrupt(e.get("mfe_r"))]
    print(f"Found {len(corrupt)} entries with None/NaN/negative mfe_r\n", flush=True)

    fixed, no_trade, no_cache, unresolved = 0, [], [], []

    for e in corrupt:
        tid = e["trade_id"]
        trade = trades_by_id.get(tid)
        if trade is None:
            no_trade.append((tid, e.get("ticker"), e.get("opened_at", "")[:10]))
            continue

        df = load_cached_daily(trade["ticker"])
        if df is None:
            no_cache.append(trade["ticker"])
            continue

        fresh = build_entry(trade, df)
        fresh["note"] = e.get("note", "")  # preserve any user-entered note

        if is_corrupt(fresh["mfe_r"]):
            unresolved.append((tid, trade["ticker"], fresh["mfe_r"]))
            continue

        old_mfe = e.get("mfe_r")
        print(f"  {trade['ticker']:6s} {tid}: mfe_r {old_mfe} -> {fresh['mfe_r']}", flush=True)
        if not args.dry_run:
            store.add(fresh)
        fixed += 1

    print(f"\nDone: {fixed} fixed, {len(no_trade)} no-matching-trade-record, "
          f"{len(no_cache)} no-cache-for-ticker, {len(unresolved)} still-corrupt-after-recompute")
    if no_trade:
        print(f"\n  No matching trade record (separate issue, see plan v8 Task V45):")
        for tid, ticker, opened in no_trade:
            print(f"    {ticker:6s} {tid} opened {opened}")
    if no_cache:
        print(f"  Missing from backtest_cache: {sorted(set(no_cache))}")
    if unresolved:
        print(f"  Still corrupt after recompute (investigate individually): {unresolved}")

    if not args.dry_run:
        remaining = [e for e in store.entries() if is_corrupt(e.get("mfe_r"))]
        print(f"\nPost-backfill corrupt count: {len(remaining)} "
              f"(expected == {len(no_trade) + len(no_cache) + len(unresolved)})")


if __name__ == "__main__":
    main()
