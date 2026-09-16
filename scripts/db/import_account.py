#!/usr/bin/env python3
"""Import data/account.json: config blob plus its balance-history rows."""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from swingbot import config  # noqa: E402
from swingbot.core.db.repositories.account import AccountRepository  # noqa: E402
from swingbot.core.infra.jsonio import read_json  # noqa: E402
from scripts.db.import_common import record_checksum  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--source")
    args = parser.parse_args(argv)

    source = read_json(args.source or os.path.join(config.DATA_DIR, "account.json"), {})
    if not isinstance(source, dict):
        print("[account] source must be a JSON object", file=sys.stderr)
        return 1
    history = source.get("balance_history") or []
    print(f"[account] config keys: {len(source)}, history points: {len(history)}")
    if args.dry_run:
        print("[account] DRY RUN -- nothing written")
        return 0

    repo = AccountRepository()
    repo.save(source)
    expected = {key: value for key, value in source.items() if key != "balance_history"}
    config_ok = record_checksum(repo.load()) == record_checksum(expected)
    history_ok = len(repo.history()) == len(history)
    print(f"[account] config checksum: {'OK' if config_ok else 'MISMATCH'}")
    print(f"[account] history rows: {len(repo.history())} (expected {len(history)}) "
          f"{'OK' if history_ok else 'MISMATCH'}")
    return 0 if config_ok and history_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
