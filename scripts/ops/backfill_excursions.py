#!/usr/bin/env python3
"""v228: upgrade every journal entry's MFE/MAE to the finest archived bars.

Calls the same per-ticker upgrade the bot's daily pass uses
(swingbot.core.analytics.excursion_upgrade) over the whole book, with no time
budget. Each entry's write is a conditional JSONB patch that only moves
`excursion_source` finer, never touches the partner's note, and writes nothing
when the figures are unchanged -- so the bot's pass and this script can meet
on the same entry safely.

Checkpointed per ticker under --checkpoint-dir (git-ignored logs/, a host
mount on the VM): a restart skips finished tickers and redoes an interrupted
one, which is safe because every upgrade is idempotent. The final report line
is printed last and saved to --report-file.

    python scripts/ops/backfill_excursions.py
    python scripts/ops/backfill_excursions.py --since 2026-10-01
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

#: Piped through stdin (`docker compose exec -T bot python - < script.py`)
#: there is no __file__; the container's working directory is the repo root.
ROOT = Path(__file__).resolve().parents[2] if "__file__" in globals() else Path.cwd()
sys.path.insert(0, str(ROOT))

from swingbot.core.analytics.excursion_upgrade import (  # noqa: E402
    UpgradeReport, pending_by_ticker, upgrade_ticker,
)
from swingbot.core.marketdata.data_store import DATA_DIR  # noqa: E402

#: Change it whenever what a finished ticker means changes; old checkpoints
#: are then ignored and their tickers redone.
FINGERPRINT = "v228-excursion-backfill-1"
DEFAULT_CHECKPOINT_DIR = Path("logs/backfill_excursions.ckpt")
DEFAULT_REPORT_FILE = Path("logs/backfill_excursions.report.txt")
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")


def checkpoint_name(ticker: str) -> str:
    """A filesystem-safe checkpoint filename; the real ticker lives inside."""
    return _UNSAFE.sub("_", ticker) + ".json"


def _restore(directory: Path) -> dict[str, dict]:
    """ticker -> counts for every checkpoint written by this code."""
    done: dict[str, dict] = {}
    for path in sorted(directory.glob("*.json")):
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(blob, dict) or blob.get("fingerprint") != FINGERPRINT:
            continue
        ticker, counts = blob.get("ticker"), blob.get("counts")
        if isinstance(ticker, str) and isinstance(counts, dict):
            done[ticker] = counts
    return done


def _save(directory: Path, ticker: str, counts: dict) -> None:
    target = directory / checkpoint_name(ticker)
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"fingerprint": FINGERPRINT, "ticker": ticker,
                               "counts": counts}), encoding="utf-8")
    tmp.replace(target)


def run(checkpoint_dir: Path, *, since: str | None = None,
        base_dir: str = DATA_DIR) -> UpgradeReport:
    """Upgrade the whole book (or entries closed since `since`), ticker by
    ticker, checkpointing each; returns the combined report."""
    checkpoint_dir = Path(checkpoint_dir)
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    pending = pending_by_ticker(since)
    restored = _restore(checkpoint_dir)
    todo = [ticker for ticker in sorted(pending) if ticker not in restored]
    print(f"resuming: {len(restored)}/{len(restored) + len(todo)} tickers restored",
          flush=True)
    report = UpgradeReport()
    for counts in restored.values():
        report.absorb(counts)
    for ticker in todo:
        per_ticker = UpgradeReport()
        upgrade_ticker(ticker, pending[ticker], per_ticker, base_dir=base_dir, deadline=None)
        counts = per_ticker.as_dict()
        _save(checkpoint_dir, ticker, counts)
        report.absorb(counts)
    shutil.rmtree(checkpoint_dir, ignore_errors=True)
    print(report.line(), flush=True)
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--checkpoint-dir", type=Path, default=DEFAULT_CHECKPOINT_DIR)
    parser.add_argument("--report-file", type=Path, default=DEFAULT_REPORT_FILE)
    parser.add_argument("--since", default=None,
                        help="only entries closed at or after this ISO date (default: whole book)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = run(args.checkpoint_dir, since=args.since)
    args.report_file.parent.mkdir(parents=True, exist_ok=True)
    args.report_file.write_text(report.line() + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
