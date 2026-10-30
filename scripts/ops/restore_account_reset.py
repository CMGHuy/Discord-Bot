#!/usr/bin/env python3
"""Undo one account reset (v189 A6) from its archive.

`!trades clear history`, `/trades-clear-history` and the admin "Clear history"
action archive every row they delete to data/archives/account-reset-<UTC>.json.
This re-inserts one archive's rows in one transaction, removes that reset's
reseed point and adds the restored realized P&L to every balance point written
since. It refuses when a later reset has run since: restore the newest archive
first. Nothing is written unless --apply is passed; the default is a dry run.

    python scripts/ops/restore_account_reset.py data/archives/account-reset-20261023T150000Z.json
    python scripts/ops/restore_account_reset.py data/archives/account-reset-20261023T150000Z.json --apply
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from swingbot.core.tracking.account_reset import restore_archive  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("archive", help="path to an account-reset-<UTC>.json archive")
    parser.add_argument("--apply", action="store_true", help="write (default: dry run)")
    args = parser.parse_args(argv)
    try:
        summary = restore_archive(args.archive, apply=args.apply)
    except (OSError, ValueError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2, sort_keys=True))
    if not args.apply:
        print("dry run: nothing written; rerun with --apply to restore", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
