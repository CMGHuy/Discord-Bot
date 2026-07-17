"""Shadow-mode parity report (plan Task 87): reads shadow_plans.jsonl and
prints per-day + cumulative summaries comparing v2 plans against the legacy
scenario numbers they'd replace. Informational only -- always exits 0. The
Task 88 cutover gate reads `invariant_violations` (must be 0) from here."""
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _pct_delta(v2, legacy):
    if not legacy:
        return None
    return abs(v2 - legacy) / legacy * 100


def _invariant_ok(plan: dict) -> bool:
    is_bull = plan["direction"] == "bullish"
    stop, entry, tp1 = plan["stop_loss"], plan["trigger_price"], plan["tp1"]
    if is_bull:
        return stop < entry < tp1
    return stop > entry > tp1


def summarize(records: list[dict]) -> dict:
    n = len(records)
    entry_deltas, stop_deltas, tp_deltas = [], [], []
    badges = Counter()
    tiers = Counter()
    violations = []
    for r in records:
        plan, legacy = r["plan"], r["legacy"]
        ed = _pct_delta(plan["trigger_price"], legacy.get("entry"))
        sd = _pct_delta(plan["stop_loss"], legacy.get("stop"))
        td = _pct_delta(plan["tp1"], legacy.get("tp"))
        if ed is not None:
            entry_deltas.append((ed, r))
        if sd is not None:
            stop_deltas.append(sd)
        if td is not None:
            tp_deltas.append(td)
        badges[plan.get("badge")] += 1
        tiers[plan.get("tier")] += 1
        if not _invariant_ok(plan):
            violations.append({"ticker": r.get("ticker"), "ts_scan": r.get("ts_scan")})

    def _stats(vals):
        if not vals:
            return {"median": None, "p95": None}
        arr = np.array(vals, dtype=float)
        return {"median": float(np.median(arr)), "p95": float(np.percentile(arr, 95))}

    top10 = sorted(entry_deltas, key=lambda x: x[0], reverse=True)[:10]
    return {
        "n": n,
        "entry_delta_pct": _stats([d for d, _ in entry_deltas]),
        "stop_delta_pct": _stats(stop_deltas),
        "tp1_delta_pct": _stats(tp_deltas),
        "badges": dict(badges),
        "tiers": dict(tiers),
        "invariant_violations": len(violations),
        "violation_details": violations,
        "top_divergences": [{"ticker": r.get("ticker"), "ts_scan": r.get("ts_scan"),
                             "entry_delta_pct": round(d, 2)} for d, r in top10],
    }


def _load_records() -> list[dict]:
    records = []
    for suffix in (".1", ""):   # rotation file first, then the live file
        path = DATA_DIR / f"shadow_plans.jsonl{suffix}"
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _print_summary(label: str, s: dict) -> None:
    print(f"\n=== {label} (N={s['n']}) ===")
    print(f"entry delta%: median={s['entry_delta_pct']['median']} p95={s['entry_delta_pct']['p95']}")
    print(f"stop  delta%: median={s['stop_delta_pct']['median']} p95={s['stop_delta_pct']['p95']}")
    print(f"tp1   delta%: median={s['tp1_delta_pct']['median']} p95={s['tp1_delta_pct']['p95']}")
    print(f"badges: {s['badges']}  tiers: {s['tiers']}")
    print(f"INVARIANT VIOLATION count: {s['invariant_violations']}")
    for v in s["violation_details"][:10]:
        print(f"  violation: {v}")
    print("top divergences:")
    for d in s["top_divergences"]:
        print(f"  {d}")


def main():
    records = _load_records()
    if not records:
        print("no shadow records found")
        return 0
    by_day: dict = {}
    for r in records:
        day = r.get("ts_scan", "")[:10]
        by_day.setdefault(day, []).append(r)
    for day in sorted(by_day):
        _print_summary(f"day {day}", summarize(by_day[day]))
    _print_summary("CUMULATIVE", summarize(records))
    return 0


if __name__ == "__main__":
    sys.exit(main())
