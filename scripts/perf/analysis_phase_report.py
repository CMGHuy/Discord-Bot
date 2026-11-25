"""Analysis seconds per ticker from scan telemetry (v245, spec § Task 0 step 5).

Usage:
    python scripts/perf/analysis_phase_report.py [--since ISO | --since-deploy] [--path FILE]
On production, read-only, piped to the bot container (no swingbot import):
    bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python - --since-deploy" < scripts/perf/analysis_phase_report.py

Prints one JSON object: scans, p50 and p90 of phases_s.analysis / tickers
(p50 = median, p90 = nearest rank), the same p50 for analysis_prefix, the
cache hit rate, the largest rss_mb, and the verdict against TARGET_S.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
from datetime import datetime, timezone

DEFAULT_PATH = os.path.join("data", "scan_telemetry.jsonl")
TARGET_S = 0.7


def _when(stamp: str) -> datetime:
    """An ISO stamp or date as an aware UTC datetime ("Z" and naive accepted)."""
    parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def per_ticker_seconds(row: dict, phase: str = "analysis") -> float | None:
    """phases_s[phase] / tickers for one scan row, None when not measurable."""
    value = (row.get("phases_s") or {}).get(phase)
    tickers = row.get("tickers")
    if not isinstance(value, (int, float)) or not tickers:
        return None
    return value / tickers


def _p90(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.9 * len(ordered)) - 1)]


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def _scans(rows: list[dict], since: str | None) -> list[dict]:
    start = _when(since) if since else None
    out = [r for r in rows if "duration_s" in r and r.get("at")]
    return out if start is None else [r for r in out if _when(r["at"]) >= start]


def _hit_rate(scans: list[dict]) -> float | None:
    hits = sum(r.get("cache_hits") or 0 for r in scans)
    misses = sum(r.get("cache_misses") or 0 for r in scans)
    return hits / (hits + misses) if hits + misses else None


def summarise(rows: list[dict], since: str | None = None) -> dict:
    scans = _scans(rows, since)
    seconds = [s for s in map(per_ticker_seconds, scans) if s is not None]
    prefix = [s for s in (per_ticker_seconds(r, "analysis_prefix") for r in scans) if s is not None]
    rss = [r["rss_mb"] for r in scans if isinstance(r.get("rss_mb"), (int, float))]
    return {"scans": len(scans), "p50": _median(seconds), "p90": _p90(seconds),
            "prefix_p50": _median(prefix), "cache_hit_rate": _hit_rate(scans),
            "rss_mb_max": max(rss) if rss else None}


def verdict(summary: dict) -> str:
    if not summary.get("scans") or summary.get("p50") is None:
        return "NO DATA"
    return "MET" if summary["p50"] <= TARGET_S else "MISSED"


def last_deploy_at(rows: list[dict], component: str = "bot") -> str | None:
    stamps = [r["at"] for r in rows
              if r.get("type") == "deploy" and r.get("component") == component and r.get("at")]
    return max(stamps, key=_when) if stamps else None


def _read(path: str) -> tuple[list[dict], int]:
    rows, bad = [], 0
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                bad += 1
    return rows, bad


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--path", default=DEFAULT_PATH)
    parser.add_argument("--since", default=None, help="ISO timestamp or date (UTC)")
    parser.add_argument("--since-deploy", action="store_true", help="from the last bot deploy marker")
    args = parser.parse_args(argv)
    if not os.path.exists(args.path):
        print(f"no telemetry file at {args.path}", file=sys.stderr)
        return 1
    rows, bad = _read(args.path)
    since = last_deploy_at(rows) if args.since_deploy else args.since
    summary = summarise(rows, since)
    print(json.dumps({**summary, "since": since, "bad_lines": bad,
                      "target_s": TARGET_S, "verdict": verdict(summary)}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
