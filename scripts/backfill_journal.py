"""One-time (or re-runnable) backfill: journal every already-closed trade
in trades.json that predates the auto-journal hook (Task A22), or that the
hook itself failed to journal for any reason. Idempotent -- JournalStore.add
replaces by trade_id, so re-running this after Task A22 is live is always
safe and simply does nothing for trades already journaled.

Run: python scripts/backfill_journal.py [--dry-run]
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from swingbot import config
from swingbot.core.analytics.journal import JournalStore, build_entry
from swingbot.core.performance import TradeLog

BACKTEST_CACHE_DIR = os.path.join(config.DATA_DIR, "backtest_cache")


def _fetch_with_cache_fallback(ticker: str):
    """Live fetch first; on any failure, fall back to the same cached CSV
    the backtest tooling already maintains at data/backtest_cache/{TICKER}.csv
    (columns Date,Open,High,Low,Close,Volume) so a backfill run doesn't
    need network access at all once that cache is warm."""
    try:
        from swingbot.core.data import get_daily_data
        return get_daily_data(ticker)
    except Exception:
        pass
    csv_path = os.path.join(BACKTEST_CACHE_DIR, f"{ticker.upper()}.csv")
    if os.path.exists(csv_path):
        import pandas as pd
        try:
            return pd.read_csv(csv_path, index_col="Date", parse_dates=True)
        except Exception:
            return None
    return None


def backfill(trades: list[dict], store: JournalStore, fetch_fn) -> tuple[int, int]:
    """Core, testable logic: journal every closed trade in `trades` not
    already present in `store`. Returns (backfilled, skipped) where
    `skipped` counts trades that are not closed (still open) OR already
    journaled -- both are legitimately "nothing to do here", just for
    different reasons, so this plan does not distinguish them in the
    return value (the CLI's printed summary can, if a future task wants
    that granularity)."""
    backfilled = skipped = 0
    for t in trades:
        if t.get("status") not in ("win", "loss", "closed"):
            skipped += 1
            continue
        if store.get(t.get("id")) is not None:
            skipped += 1
            continue
        df = fetch_fn(t["ticker"])
        entry = build_entry(t, df)
        store.add(entry)
        backfilled += 1
    return backfilled, skipped


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Report what would be backfilled without writing journal.json")
    args = parser.parse_args()

    trades = TradeLog().get_trades(status="all", limit=None)
    store = JournalStore()

    if args.dry_run:
        # A dry run must never touch disk -- back it with a throwaway
        # in-memory-only store pointed at a path that doesn't exist yet,
        # so JournalStore's own _load()/_save() calls are harmless no-ops
        # on a scratch file, never the real journal.json.
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            scratch = JournalStore(path=os.path.join(tmp, "scratch_journal.json"))
            backfilled, skipped = backfill(trades, scratch, _fetch_with_cache_fallback)
    else:
        backfilled, skipped = backfill(trades, store, _fetch_with_cache_fallback)

    print(f"backfilled {backfilled}, skipped {skipped}")


if __name__ == "__main__":
    main()
