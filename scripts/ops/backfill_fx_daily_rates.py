#!/usr/bin/env python3
"""v205: fill fx_daily_rates for every past Berlin day the FX pair files allow.

One-off and idempotent. The row for day D is the last positive daily close
dated strictly before D (bar at most 7 days old), the same rule the
refresher's 08:00 snap uses, so a backfilled day equals the day's snap. It
writes insert-if-absent, so a snapped row is never overwritten and a re-run
writes 0. It reads the pair files in market_data/daily/ as they stand and never
fetches. Nothing is printed but counts.

Run on production once, after `alembic upgrade head` created the table
(docs/deploy/DEPLOY_HETZNER.md, "v205: daily FX rates"):

    bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T admin \
        python scripts/ops/backfill_fx_daily_rates.py --dry-run"
    bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T admin \
        python scripts/ops/backfill_fx_daily_rates.py"

Exit codes: 0 done, 2 bad arguments.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from swingbot.core.marketdata import fx_snap  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", type=date.fromisoformat,
                    help="First Berlin day, YYYY-MM-DD. Default: the day after each pair's first bar.")
    ap.add_argument("--end", type=date.fromisoformat,
                    help="Last Berlin day, YYYY-MM-DD. Default: Berlin today.")
    ap.add_argument("--dry-run", action="store_true", help="Print the planned counts; write nothing.")
    return ap


def main(argv: list[str] | None = None) -> int:
    ap = _parser()
    args = ap.parse_args(argv)
    if args.start and args.end and args.start > args.end:
        ap.error("--start is after --end")
    if args.dry_run:
        rows = fx_snap.planned_rows(start=args.start, end=args.end)
        pairs = Counter(f"{row['base']}{row['account']}" for row in rows)
        for pair, count in sorted(pairs.items()):
            print(f"{pair} planned={count}")
        print(f"planned={len(rows)} (dry run: nothing written)")
        return 0
    print(f"written={fx_snap.backfill(start=args.start, end=args.end)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
