#!/usr/bin/env python3
"""One-time repair: re-journals closed trades whose journal R disagrees
with the trade's own final fill.

Before 41e9b65e (2026-08-20) update_open_trades() also closed v2
plan-linked trades, at the stop. It journaled them at -1.00R; the plan
manager then wrote the real poll fill (often an extended-hours print) over
the trade, and the journal kept the first number. Measured 2026-10-21 on
production: 54 of 528 journaled trades closed before 2026-08-20 disagree
by more than 0.05R, 1 of 248 after.

Each picked row is rebuilt with journal.build_entry() from the trade's
final record -- the same builder the live close path uses -- keeping the
partner's note. Nothing is written unless --apply is passed; the default
is a dry-run report of every field that would change.

    python scripts/ops/rejournal_fill_mismatch.py                  # dry run
    python scripts/ops/rejournal_fill_mismatch.py --apply          # writes
    python scripts/ops/rejournal_fill_mismatch.py --trade-id X --apply
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from swingbot.core.analytics import metrics  # noqa: E402

TOLERANCE_R = 0.05
#: Written by the store on every add, so never reported as a change.
_IGNORED = ("created_at",)


def find_mismatches(trades: list[dict], journal: dict[str, dict]) -> list[tuple[dict, dict]]:
    """(trade, journal entry) for every terminal trade whose journal R is
    more than TOLERANCE_R away from the R of its final fill."""
    out = []
    for t in trades:
        if t.get("status") not in ("win", "loss", "closed"):
            continue
        entry = journal.get(t.get("id"))
        fill_r = metrics.r_multiple(t)
        if entry is None or fill_r is None or entry.get("r_realized") is None:
            continue
        if abs(entry["r_realized"] - fill_r) > TOLERANCE_R:
            out.append((t, entry))
    return out


def merge_entry(rebuilt: dict, old: dict) -> dict:
    """The rebuilt entry with the partner's free-text note carried over."""
    return dict(rebuilt, note=old.get("note") or "")


def changed_fields(old: dict, new: dict) -> list[str]:
    return [k for k in new if k not in _IGNORED and old.get(k) != new.get(k)]


def main() -> None:
    from swingbot.core.analytics.journal import JournalStore, build_entry
    from swingbot.core.marketdata.data import get_daily_data
    from swingbot.core.tracking.performance import TradeLog

    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--trade-id", action="append",
                    help="Limit to this trade id (repeatable). Default: every mismatch.")
    ap.add_argument("--apply", action="store_true",
                    help="Write the repair. Default is a dry run that only reports.")
    args = ap.parse_args()

    store = JournalStore()
    journal = {e["trade_id"]: e for e in store.entries(cohort="all")}
    trades = TradeLog().get_trades(status=None, limit=None) or []
    found = find_mismatches(trades, journal)
    if args.trade_id:
        found = [(t, e) for t, e in found if t["id"] in args.trade_id]
    if not found:
        print("No journal rows disagree with their trade's fill.")
        return

    print(f"{len(found)} journal row(s) disagree with the fill by > {TOLERANCE_R}R:\n")
    for t, old in found:
        try:
            df = get_daily_data(t["ticker"])
        except Exception as exc:   # MFE/MAE degrade to None, as on the live path
            print(f"  {t['ticker']}: bars unavailable ({exc}); MFE/MAE will be None")
            df = None
        new = merge_entry(build_entry(t, df), old)
        diffs = ", ".join(f"{k}: {old.get(k)!r} -> {new.get(k)!r}"
                          for k in changed_fields(old, new) if k in
                          ("r_realized", "outcome", "closed_at", "exit_efficiency"))
        print(f"  {t['ticker']:<6} {t['id']}  {t.get('closed_at', '')[:10]}  {diffs}")
        print(f"         all changed: {', '.join(changed_fields(old, new))}")
        if args.apply:
            store.add(new)
    print("\nWritten." if args.apply else "\nDry run -- pass --apply to write.")


if __name__ == "__main__":
    main()
