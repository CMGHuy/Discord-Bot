"""Export the analytics snapshot + journal to CSV/JSON for spreadsheet
analysis or an external dashboard.

Run: python scripts/export_analytics.py [--out exports/analytics]
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from swingbot.core.analytics.aggregate import DIMENSIONS
from swingbot.core.analytics.journal import JournalStore

STAT_ROW_COLUMNS = ["key", "n", "wins", "losses", "win_rate", "expectancy_r",
                    "avg_r", "profit_factor", "total_pnl"]
JOURNAL_COLUMNS = ["trade_id", "ticker", "strategy", "horizon_key", "direction", "tier",
                   "badge", "quality_score", "outcome", "r_realized", "mfe_r", "mae_r",
                   "exit_efficiency", "holding_days", "tags", "auto_lesson", "note",
                   "opened_at", "closed_at", "created_at"]


def export_all(snapshot: dict, out_dir: str) -> list[str]:
    """Write every export artifact for `snapshot` (+ the current journal)
    into `out_dir` (created if missing). Returns the list of written
    absolute paths, in write order, for the CLI to print."""
    os.makedirs(out_dir, exist_ok=True)
    written = []

    snap_path = os.path.join(out_dir, "snapshot.json")
    with open(snap_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, default=str)
    written.append(snap_path)

    equity_path = os.path.join(out_dir, "equity_curve.csv")
    with open(equity_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["date", "balance", "pnl"])
        writer.writeheader()
        writer.writerows(snapshot["equity_curve"]["points"])
    written.append(equity_path)

    for dim in DIMENSIONS:
        dim_path = os.path.join(out_dir, f"stats_by_{dim}.csv")
        with open(dim_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=STAT_ROW_COLUMNS)
            writer.writeheader()
            writer.writerows(snapshot["by"].get(dim, []))
        written.append(dim_path)

    journal_path = os.path.join(out_dir, "journal.csv")
    with open(journal_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=JOURNAL_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(JournalStore().entries())
    written.append(journal_path)

    return written


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="exports/analytics")
    args = parser.parse_args()

    from swingbot.core.analytics.snapshots import load_snapshot, refresh_snapshot

    snap = load_snapshot(max_age_seconds=10 ** 9)  # any age is fine for a manual export
    if snap is None:
        refresh_snapshot()
        snap = load_snapshot(max_age_seconds=10 ** 9)
    if snap is None:
        print("No trades to export yet.")
        return

    for path in export_all(snap, args.out):
        print(path)


if __name__ == "__main__":
    main()
