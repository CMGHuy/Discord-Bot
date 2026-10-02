#!/usr/bin/env python3
"""Read-only evaluation of the v106 Alpaca soak's acceptance clauses.

Run inside the bot container (stdin, so it works before an image rebuild):
  docker compose exec -T bot python - [--start D] [--end D] < scripts/ops/v106_soak_check.py

Reads scan telemetry (data/scan_telemetry.jsonl) and applies plan v106 T13
Step 6's measurement definitions, fixed 2026-09-27 and never retuned:
  (a) every `cold_fetch_s` timing pooled: p95 < 3 s, with >= 20 timings
      (fewer is UNMEASURED, never a pass);
  (b) sum yfinance-fallback / sum (alpaca + yfinance-fallback) over
      `data_sources` and `price_sources` pooled: < 5 %;
  (c) (errors + data_skips) / tickers: no worse than the 0.01299 baseline.
Clause (d) (parity) was settled in T13 Step 3 and is not re-read here.

Defaults are soak attempt 2: trading days 2026-10-01 .. 2026-10-07 (UTC
dates). The verdict line says INTERIM until the window's last day has closed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys

import numpy as np

START, END = "2026-10-01", "2026-10-07"
A_P95_MAX, A_MIN_TIMINGS = 3.0, 20
B_MAX = 0.05
C_BASELINE = 0.01299
CLOSE_UTC = dt.time(20, 0)          # 16:00 New York in EDT


def scan_rows(lines, start: str, end: str) -> list:
    """Scan rows (those with a numeric `duration_s`) whose UTC date is in
    [start, end]; deploy markers and unparsable lines are skipped."""
    rows = []
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, dict) or not isinstance(row.get("duration_s"), (int, float)):
            continue
        if start <= str(row.get("at", ""))[:10] <= end:
            rows.append(row)
    return rows


def clause_a(rows: list) -> dict:
    timings = [float(t) for r in rows for t in (r.get("cold_fetch_s") or [])]
    if len(timings) < A_MIN_TIMINGS:
        return {"n": len(timings), "p95": None, "max": None, "verdict": "UNMEASURED"}
    p95 = float(np.percentile(timings, 95))
    return {"n": len(timings), "p95": round(p95, 2), "max": round(max(timings), 2),
            "verdict": "PASS" if p95 < A_P95_MAX else "FAIL"}


def clause_b(rows: list) -> dict:
    counts = [r[k] for r in rows for k in ("data_sources", "price_sources")
              if isinstance(r.get(k), dict)]
    misses = sum(int(d.get("yfinance-fallback", 0)) for d in counts)
    asked = misses + sum(int(d.get("alpaca", 0)) for d in counts)
    if not asked:
        return {"misses": 0, "asked": 0, "rate": None, "verdict": "UNMEASURED"}
    rate = misses / asked
    return {"misses": misses, "asked": asked, "rate": round(rate, 4),
            "verdict": "PASS" if rate < B_MAX else "FAIL"}


def clause_c(rows: list) -> dict:
    bad = sum(int(r.get("errors", 0)) + int(r.get("data_skips", 0)) for r in rows)
    tickers = sum(int(r.get("tickers", 0)) for r in rows)
    if not tickers:
        return {"bad": 0, "tickers": 0, "ratio": None, "verdict": "UNMEASURED"}
    ratio = bad / tickers
    return {"bad": bad, "tickers": tickers, "ratio": round(ratio, 5),
            "verdict": "PASS" if round(ratio, 5) <= C_BASELINE else "FAIL"}


def evaluate(rows: list) -> dict:
    return {"scans": len(rows), "a": clause_a(rows), "b": clause_b(rows), "c": clause_c(rows)}


def overall(result: dict, final: bool) -> str:
    verdicts = [result[k]["verdict"] for k in ("a", "b", "c")]
    if "FAIL" in verdicts:
        status = "FAIL"
    elif "UNMEASURED" in verdicts:
        status = "UNMEASURED"
    else:
        status = "PASS"
    return f"{'FINAL' if final else 'INTERIM'} {status}"


def is_final(end: str, now: dt.datetime) -> bool:
    closed = dt.datetime.combine(dt.date.fromisoformat(end), CLOSE_UTC, dt.timezone.utc)
    return now >= closed


def format_result(label: str, result: dict) -> str:
    a, b, c = result["a"], result["b"], result["c"]
    return (f"{label:<10} scans={result['scans']:<4} "
            f"(a) n={a['n']} p95={a['p95']} max={a['max']} {a['verdict']} | "
            f"(b) {b['misses']}/{b['asked']} rate={b['rate']} {b['verdict']} | "
            f"(c) {c['bad']}/{c['tickers']} ratio={c['ratio']} {c['verdict']}")


def report(rows: list, end: str, now: dt.datetime) -> list:
    lines = []
    for day in sorted({str(r["at"])[:10] for r in rows}):
        lines.append(format_result(day, evaluate([r for r in rows if str(r["at"]).startswith(day)])))
    pooled = evaluate(rows)
    lines.append(format_result("POOLED", pooled))
    lines.append(f"VERDICT: {overall(pooled, is_final(end, now))}")
    return lines


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default=START)
    ap.add_argument("--end", default=END)
    ap.add_argument("--path", default=None)
    args = ap.parse_args(argv)
    path = args.path
    if path is None:
        from swingbot.core.scanning.telemetry import TELEMETRY_PATH
        path = TELEMETRY_PATH
    with open(path, encoding="utf-8") as f:
        rows = scan_rows(f, args.start, args.end)
    print(f"v106 soak {args.start}..{args.end}  (thresholds: a p95<{A_P95_MAX}s n>={A_MIN_TIMINGS}, "
          f"b<{B_MAX:.0%}, c<={C_BASELINE})")
    print("\n".join(report(rows, args.end, dt.datetime.now(dt.timezone.utc))))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, "/app")
    sys.exit(main())
