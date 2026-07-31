"""Shadow comparison report (G104). Usage: python scripts/gate_shadow_report.py [--since YYYY-MM-DD]"""
import argparse
import sys
import time

sys.path.insert(0, ".")

from swingbot.core.gate.persistence import (join_shadow_outcomes,
                                            shadow_cohorts)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", default=None)
    args = parser.parse_args()
    joined = join_shadow_outcomes()
    if args.since:
        cutoff = time.mktime(time.strptime(args.since, "%Y-%m-%d"))
        joined = [r for r in joined if r.get("ts", 0) >= cutoff]
    cohorts = shadow_cohorts(joined)
    print(f"joined decisions: {len(joined)}")
    print(f"would-have-blocked cohort: {cohorts['would_block']}")
    print(f"passed cohort:             {cohorts['passed']}")
    per_flag: dict[str, list] = {}
    for row in joined:
        for flag in row.get("fired_flags", []):
            per_flag.setdefault(flag, []).append(row)
    for flag, rows in sorted(per_flag.items()):
        wins = sum(r["outcome"] == "win" for r in rows)
        print(f"  {flag}: fired {len(rows)}x live, WR when taken "
              f"{100.0 * wins / len(rows):.0f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
