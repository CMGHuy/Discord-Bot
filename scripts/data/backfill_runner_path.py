#!/usr/bin/env python3
"""v142: one-off backfill of `runner_path` onto closed partial plans.

Walks every CLOSED plan whose status_history holds PARTIAL, skips any already
stamped (idempotent), and computes the stamp from the live scan's daily disk
cache (`market_data/daily`, `runner_path.cached_daily_bars`) -- never a
network fetch: a cold fetch blocks for ~18.5s per batch and the stamp is not
worth one. Writes nothing unless --apply is passed.

    python scripts/data/backfill_runner_path.py            # dry run: counts only
    python scripts/data/backfill_runner_path.py --apply    # writes source="backfill"

Production (after the v142 deploy):
    bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python scripts/data/backfill_runner_path.py"
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from swingbot.core.analytics import runner_path as rp  # noqa: E402

log = logging.getLogger(__name__)


def candidates(plans: list) -> list:
    """Closed plans that went through PARTIAL -- the only ones with a runner."""
    return [plan for plan in plans if plan.status == "CLOSED"
            and any(entry.get("status") == "PARTIAL" for entry in plan.status_history or [])]


def _bars_for(ticker: str, bars_fn, frames: dict):
    """One disk read per ticker; an unreadable cache is a miss, not a crash."""
    if ticker not in frames:
        try:
            frames[ticker] = bars_fn(ticker)
        except Exception as exc:
            print(f"  {ticker}: cache read failed ({exc})")
            frames[ticker] = None
    return frames[ticker]


def _compute(plan, bars_fn, frames: dict):
    """The stamp, or None when it cannot be computed -- one malformed plan
    (bad timestamp, NaN bars) must not abort an --apply run."""
    try:
        return rp.compute_runner_path(plan, _bars_for(plan.ticker, bars_fn, frames),
                                      source="backfill")
    except Exception:
        log.warning("runner_path compute failed for %s", plan.plan_id, exc_info=True)
        return None


def _write(store, plan_id: str, path: dict) -> bool:
    """Re-read before writing: a live close may have stamped it since the snapshot."""
    fresh = store.get(plan_id)
    if fresh is None or fresh.runner_path is not None:
        return False
    fresh.runner_path = path
    store.update(fresh)
    return True


def backfill(store, bars_fn, *, apply: bool) -> dict:
    """Stamp every unstamped candidate; returns stamped / skipped / unavailable."""
    counts = {"stamped": 0, "skipped": 0, "unavailable": 0}
    frames: dict = {}
    for plan in candidates(store.all()):
        if plan.runner_path is not None:
            counts["skipped"] += 1
            continue
        path = _compute(plan, bars_fn, frames)
        if path is None:
            counts["unavailable"] += 1
            print(f"  unavailable: {plan.plan_id} {plan.ticker}")
        elif apply and not _write(store, plan.plan_id, path):
            counts["skipped"] += 1
        else:
            counts["stamped"] += 1
    return counts


def main(argv=None, *, store=None, bars_fn=None) -> dict:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true",
                        help="Write the stamps. Default is a dry run that only counts.")
    args = parser.parse_args(argv)
    if store is None:
        from swingbot.core.planning.plan_store import PlanStore
        store = PlanStore()
    counts = backfill(store, bars_fn or rp.cached_daily_bars, apply=args.apply)
    mode = "APPLIED" if args.apply else "DRY RUN"
    print(f"{mode}: stamped={counts['stamped']} skipped={counts['skipped']} "
          f"unavailable={counts['unavailable']}")
    if not args.apply:
        print("Dry run only -- pass --apply to write.")
    return counts


if __name__ == "__main__":
    main()
