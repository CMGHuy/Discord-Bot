#!/usr/bin/env python3
"""One-time repair: gives an already-closed trade a real exit price when
it never got one recorded.

Before the fix to close_trade_manual() (see
swingbot/core/tracking/performance.py), every admin-UI "Close" button
click closed the trade with no exit_price at all -- pnl_pct/r_multiple
came back None forever, the account balance never saw the P&L, and the
Dashboard's Closed table fell back to its "still open, projecting toward
target/stop" view for a position that was actually over.

This scans data/trades.json for exactly that gap (status is terminal,
exit_price is null) and prices each one off the DAILY CLOSE on the date
it actually closed -- the same daily-bar convention the rest of this
paper-trade tracker already uses for its stop/target checks. Nothing is
written unless --apply is passed; the default is a dry-run report.

    python scripts/ops/backfill_manual_close_price.py                    # dry run, every gap
    python scripts/ops/backfill_manual_close_price.py --apply            # writes
    python scripts/ops/backfill_manual_close_price.py --trade-id X --apply
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from swingbot.core.marketdata.data import get_daily_data  # noqa: E402
from swingbot.core.tracking.performance import TradeLog  # noqa: E402


def _price_on(ticker: str, closed_at: str) -> float | None:
    """The daily bar's Close on (or the closest trading day before) the
    date `closed_at` falls on. None if no bar is available at or before
    that date at all."""
    day = datetime.fromisoformat(closed_at).date()
    df = get_daily_data(ticker, period="1y")
    on_or_before = df[df.index.date <= day]
    if on_or_before.empty:
        return None
    return float(on_or_before["Close"].iloc[-1])


def find_gaps(trades: list[dict]) -> list[dict]:
    """Every terminal trade that never got a real exit recorded."""
    return [
        t for t in trades
        if t.get("status") in ("win", "loss", "closed")
        and t.get("exit_price") is None
        and t.get("closed_at")
    ]


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--trade-id", action="append",
                     help="Limit to this trade id (repeatable). Default: every gap found.")
    ap.add_argument("--apply", action="store_true",
                     help="Write the backfill. Default is a dry run that only reports.")
    args = ap.parse_args()

    log_ = TradeLog()
    trades = log_.get_trades(status=None, limit=None) or []
    gaps = find_gaps(trades)
    if args.trade_id:
        gaps = [t for t in gaps if t["id"] in args.trade_id]

    if not gaps:
        print("No closed trades are missing an exit_price.")
        return

    print(f"{len(gaps)} closed trade(s) missing an exit_price:\n")
    for t in gaps:
        label = f"  {t['ticker']:<6} {t['id']}  closed {t['closed_at']}"
        try:
            price = _price_on(t["ticker"], t["closed_at"])
        except Exception as exc:
            print(f"{label}  -- price lookup failed: {exc}")
            continue
        if price is None:
            print(f"{label}  -- no historical bar found")
            continue
        tag = "" if args.apply else "  [DRY RUN]"
        print(f"{label}  -> exit_price {price:.2f}{tag}")
        if args.apply:
            ok = log_.backfill_exit_price(t["id"], price)
            print(f"    {'applied' if ok else 'skipped (no longer eligible)'}")

    if not args.apply:
        print("\nDry run only -- pass --apply to write these.")


if __name__ == "__main__":
    main()
