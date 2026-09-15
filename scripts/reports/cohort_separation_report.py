#!/usr/bin/env python3
"""v86 §6: did the cohort label separate outcomes, and what should it have
been keyed on instead?

Two questions, deliberately answered by two functions:

  label_separation()    the PRE-REGISTERED verdict. One shot. The thresholds
                        below were committed on 2026-09-14, before any
                        labelled plan had closed. Do not edit them to reach a
                        verdict -- an edited threshold is a new hypothesis and
                        needs its own pre-registration.
  feature_separation()  exploratory. Free to run, free to slice, and its
                        output may NOT be used to revise the verdict above.

Run: python scripts/reports/cohort_separation_report.py --journal data/journal.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

MIN_N_PER_GROUP = 150        # frozen 2026-09-14, spec §6
PASS_SEPARATION_R = -0.20    # ExpR(POOR) - ExpR(non-POOR) must be <= this


def _stats(rs: list[float]) -> dict:
    if not rs:
        return {"n": 0, "win_rate": 0.0, "expectancy_r": 0.0}
    return {"n": len(rs),
            "win_rate": round(100.0 * sum(1 for r in rs if r > 0) / len(rs), 2),
            "expectancy_r": round(sum(rs) / len(rs), 4)}


def _eligible(entries: list[dict], run_date: str) -> list[dict]:
    """Forward-only: a plan created on or before the freeze was never
    labelled by this table, and including it would let the table be scored
    against the trades that built it."""
    return [e for e in entries
            if e.get("r_realized") is not None
            and str(e.get("created_at", "")) > run_date]


def label_separation(entries: list[dict], run_date: str) -> dict:
    rows = _eligible(entries, run_date)
    poor = [float(e["r_realized"]) for e in rows if e.get("cohort_label") == "COHORT_POOR"]
    other = [float(e["r_realized"]) for e in rows
             if e.get("cohort_label") in ("COHORT_TYPICAL", "COHORT_STRONG")]

    s_poor, s_other = _stats(poor), _stats(other)
    separation = round(s_poor["expectancy_r"] - s_other["expectancy_r"], 4)

    if s_poor["n"] < MIN_N_PER_GROUP or s_other["n"] < MIN_N_PER_GROUP:
        verdict = "INSUFFICIENT_N"
    elif separation <= PASS_SEPARATION_R:
        verdict = "PASS"
    else:
        verdict = "FAIL"

    return {"verdict": verdict, "separation_r": separation,
            "n_poor": s_poor["n"], "n_other": s_other["n"],
            "poor": s_poor, "other": s_other,
            "min_n_per_group": MIN_N_PER_GROUP,
            "pass_separation_r": PASS_SEPARATION_R}


def feature_separation(entries: list[dict], feature: str) -> list[dict]:
    buckets: dict = {}
    for e in entries:
        if e.get("r_realized") is None:
            continue
        value = (e.get("risk_features") or {}).get(feature)
        buckets.setdefault(value, []).append(float(e["r_realized"]))
    return [dict(value=v, **_stats(rs)) for v, rs in
            sorted(buckets.items(), key=lambda kv: str(kv[0]))]


FEATURES = ("regime2_state", "confidence_level", "htf_agree", "confluence_count",
            "stop_width_atr", "atr_pct", "rs_percentile",
            "session_bucket", "days_to_earnings")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--journal", default="data/journal.json")
    ap.add_argument("--run-date", default=None,
                    help="registry freeze date; default: the cohort_run_date on the entries")
    args = ap.parse_args()

    entries = json.loads(Path(args.journal).read_text(encoding="utf-8"))
    run_date = args.run_date or next(
        (e["cohort_run_date"] for e in entries if e.get("cohort_run_date")), "")
    if not run_date:
        print("no cohort_run_date on any entry -- nothing was stamped yet.")
        return 1

    v = label_separation(entries, run_date)
    print(f"\n=== v86 §6 pre-registered verdict (freeze {run_date}) ===")
    print(f"POOR      n={v['poor']['n']:>5}  WR {v['poor']['win_rate']:>6.2f}%  "
          f"ExpR {v['poor']['expectancy_r']:+.4f}")
    print(f"non-POOR  n={v['other']['n']:>5}  WR {v['other']['win_rate']:>6.2f}%  "
          f"ExpR {v['other']['expectancy_r']:+.4f}")
    print(f"separation {v['separation_r']:+.4f}R  (PASS needs <= {PASS_SEPARATION_R:+.2f}R "
          f"with n >= {MIN_N_PER_GROUP} per group)")
    print(f"VERDICT: {v['verdict']}")
    if v["verdict"] == "PASS":
        print("PASS makes a suppression flip a CANDIDATE. It does not authorise one.")

    print("\n=== exploratory: per-feature separation (NOT part of the verdict) ===")
    for feature in FEATURES:
        rows = [r for r in feature_separation(entries, feature) if r["n"] >= 20]
        if not rows:
            continue
        print(f"\n{feature}")
        for r in rows:
            print(f"  {str(r['value']):>16}  n={r['n']:>5}  WR {r['win_rate']:>6.2f}%  "
                  f"ExpR {r['expectancy_r']:+.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
