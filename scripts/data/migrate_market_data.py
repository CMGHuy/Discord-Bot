#!/usr/bin/env python3
"""One-shot migration: market_data/{TICKER}/{interval}.csv
                   -> market_data/{timeframe}/{TICKER}.csv

The cache is now grouped by candle timeframe so a training run can point at
one folder ("daily", "hourly", ...) and get every symbol at that
granularity. This moves whatever the old per-ticker layout already had.

Idempotent: re-running after a successful migration finds nothing to do.
Refuses to clobber an existing destination unless --force.

    python scripts/data/migrate_market_data.py --dry-run
    python scripts/data/migrate_market_data.py
"""
import argparse
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from swingbot.core.data_store import (
    DATA_DIR,
    TIMEFRAMES,
    safe_symbol,
    timeframe_name,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-dir", default=DATA_DIR)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="overwrite a destination file that already exists")
    args = ap.parse_args()

    base = Path(args.base_dir)
    if not base.exists():
        print(f"{base}/ does not exist -- nothing to migrate.")
        return 0

    # A directory is 'old layout' if its name is NOT a timeframe folder.
    old_dirs = [d for d in base.iterdir()
                if d.is_dir() and d.name not in TIMEFRAMES]
    if not old_dirs:
        print("Already migrated -- no per-ticker directories found.")
        return 0

    moved = skipped = failed = 0
    for tdir in sorted(old_dirs):
        ticker = tdir.name
        for csv in sorted(tdir.glob("*.csv")):
            interval = csv.stem
            try:
                tf = timeframe_name(interval)
            except ValueError:
                print(f"  ? {ticker}/{csv.name}: unknown interval, left in place")
                skipped += 1
                continue

            dest_dir = base / tf
            dest = dest_dir / f"{safe_symbol(ticker)}.csv"
            if dest.exists() and not args.force:
                print(f"  = {ticker}/{csv.name} -> {tf}/{dest.name} EXISTS, skipped")
                skipped += 1
                continue

            if args.dry_run:
                print(f"  > {ticker}/{csv.name} -> {tf}/{dest.name}")
                moved += 1
                continue

            try:
                dest_dir.mkdir(parents=True, exist_ok=True)
                shutil.move(str(csv), str(dest))
                moved += 1
            except Exception as exc:
                print(f"  ! {ticker}/{csv.name}: {exc}")
                failed += 1

        # Remove the old ticker dir once empty (never recursively -- an
        # unexpected leftover file should survive and be visible).
        if not args.dry_run:
            try:
                if not any(tdir.iterdir()):
                    tdir.rmdir()
            except OSError:
                pass

    verb = "would move" if args.dry_run else "moved"
    print(f"\n{verb} {moved}, skipped {skipped}, failed {failed}")
    if not args.dry_run:
        for tf in sorted(TIMEFRAMES):
            d = base / tf
            if d.exists():
                print(f"  {tf:<9} {len(list(d.glob('*.csv')))} files")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
