"""4-week shadow forward-gate for fold-passing components (Task E40).

Run: python scripts/reports/shadow_component_report.py --component AVWAP_LEVELS_ENABLED
     python scripts/reports/shadow_component_report.py --component X --backfill

PROMOTION IS NOT AUTOMATIC. This prints a verdict; a human reads it and
decides whether to flip the flag. Nothing here writes config.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from swingbot.config import DATA_DIR  # noqa: E402

# The real shadow log is shadow_plans.jsonl (swingbot/core/shadow_log.py),
# not the "shadow_log.jsonl" the plan brief names -- there is no such file.
SHADOW_LOG = os.path.join(DATA_DIR, "shadow_plans.jsonl")

# Pre-registered promotion bar. The on-cohort must not be WORSE than the
# off-cohort ('>=', deliberately not '>'), on at least this many resolved
# entries. Changing either needs a new pre-registration.
MIN_ON_COHORT_N = 20


def shadow_component_report(lines: list, component: str) -> dict:
    """Pure: pair each cohort's would-be entries with their 10-day forward
    returns and compare. Lines whose forward return has not been resolved
    yet are excluded rather than counted as zero -- an unmatured window is
    no evidence, not neutral evidence."""
    cohorts = {"on": [], "off": []}
    for row in lines:
        if row.get("component") == component and row.get("variant") in cohorts \
                and row.get("fwd_return_10d") is not None:
            cohorts[row["variant"]].append(row["fwd_return_10d"])
    out = {}
    for k, v in cohorts.items():
        out[k] = {"n": len(v), "fwd_expectancy": (sum(v) / len(v)) if v else None}
    promotable = (out["on"]["fwd_expectancy"] is not None
                  and out["off"]["fwd_expectancy"] is not None
                  and out["on"]["n"] >= MIN_ON_COHORT_N
                  and out["on"]["fwd_expectancy"] >= out["off"]["fwd_expectancy"])
    out["verdict"] = "PROMOTE" if promotable else "HOLD"
    return out


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--component", required=True)
    p.add_argument("--path", default=SHADOW_LOG)
    p.add_argument("--backfill", action="store_true",
                   help="resolve matured 10-day forward returns before reporting")
    args = p.parse_args()

    if not os.path.exists(args.path):
        print(f"no shadow log at {args.path} -- nothing to report", file=sys.stderr)
        return 1

    if args.backfill:
        from swingbot.core.shadow_log import backfill_forward_returns
        print(f"resolved {backfill_forward_returns(args.path)} newly matured entries",
              file=sys.stderr)

    with open(args.path, encoding="utf-8") as f:
        lines = [json.loads(l) for l in f if l.strip()]
    report = shadow_component_report(lines, args.component)
    print(json.dumps(report, indent=1))
    if report["verdict"] == "PROMOTE":
        print(f"\n{args.component} cleared the forward gate. Promotion is a "
              f"HUMAN decision -- flip the flag yourself after reading this.",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
