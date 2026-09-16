#!/usr/bin/env python3
"""v87: is the 15m/5m archive actually growing?

Yahoo serves sub-hourly bars for ~60 days only; the bot's market_data_refresh
loop archives them forward, merge-only. This prints, per timeframe, how many
symbols are archived, the earliest and latest bar across the archive, the
median depth in sessions, and which symbols have fallen more than
STALE_SESSIONS behind the archive's newest bar.

Run on production (the archive lives there, not on the dev machine):

    python scripts/ops/intraday_archive_coverage.py
    python scripts/ops/intraday_archive_coverage.py --timeframes 5min

A week after rollout, `earliest` must be unchanged and `latest` current.
"""
from __future__ import annotations

import argparse
import os
import statistics
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from swingbot.core.marketdata.data_store import DATA_DIR, load_from_disk, timeframe_name  # noqa: E402

ARCHIVE_TIMEFRAMES = ("15min", "5min")
STALE_SESSIONS = 3


def _symbols(base_dir: str, tf: str) -> list[str]:
    folder = os.path.join(base_dir, tf)
    if not os.path.isdir(folder):
        return []
    return sorted(name[:-4] for name in os.listdir(folder) if name.endswith(".csv"))


def coverage(base_dir: str, timeframes=ARCHIVE_TIMEFRAMES) -> dict:
    report = {}
    for raw in timeframes:
        tf = timeframe_name(raw)
        spans = {}
        for symbol in _symbols(base_dir, tf):
            frame = load_from_disk(symbol, tf, base_dir=base_dir)
            if frame is None or frame.empty:
                continue
            dates = frame.index.normalize().unique()
            spans[symbol] = (dates.min().date(), dates.max().date(), len(dates))
        if not spans:
            report[tf] = {"symbols": 0, "earliest": None, "latest": None,
                          "median_sessions": None, "stale": []}
            continue
        newest = max(last for _, last, _ in spans.values())
        stale = sorted(s for s, (_, last, _) in spans.items()
                       if np.busday_count(last, newest) > STALE_SESSIONS)
        report[tf] = {
            "symbols": len(spans),
            "earliest": str(min(first for first, _, _ in spans.values())),
            "latest": str(newest),
            "median_sessions": statistics.median(n for _, _, n in spans.values()),
            "stale": stale,
        }
    return report


def render(report: dict) -> str:
    lines = []
    for tf, row in report.items():
        lines.append(f"{tf}: symbols={row['symbols']} earliest={row['earliest']} "
                     f"latest={row['latest']} median_sessions={row['median_sessions']}")
        if row["stale"]:
            lines.append(f"  stale (> {STALE_SESSIONS} sessions behind): {', '.join(row['stale'])}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-dir", default=str(ROOT / DATA_DIR))
    parser.add_argument("--timeframes", default=",".join(ARCHIVE_TIMEFRAMES))
    args = parser.parse_args(argv)
    timeframes = [t.strip() for t in args.timeframes.split(",") if t.strip()]
    print(render(coverage(args.base_dir, timeframes)), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
