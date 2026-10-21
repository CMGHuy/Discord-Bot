#!/usr/bin/env python3
"""v180 stage-3 badge check: score the Turtle Soup rows a stamped arm pair adds on the badge floor
(backtest-methodology.md § Badge scoring): win_rate >= 50 over win+loss, expectancy_r > 0, N >= 15,
scratches + timeouts <= 50% of closed. Descriptive output for the record; the verdict is the gate's."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from swingbot.core.backtesting.acceptance import ArmTrade  # noqa: E402
from swingbot.core.backtesting.arms import turtle_soup_report as rep  # noqa: E402
from swingbot.core.backtesting.arms.shift_permutation import NotAdditive, additive_added  # noqa: E402
from swingbot.core.market.strategy_types import TURTLE_SOUP  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--arms", required=True, type=Path)
    parser.add_argument("--out-json", type=Path, default=None)
    parser.add_argument("--min-n", type=int, default=rep.BADGE_MIN_N)
    return parser


def _load(path) -> tuple[dict, list, list] | None:
    try:
        blob = json.loads(Path(path).read_text(encoding="utf-8"))
        baseline = [ArmTrade(**row) for row in blob["baseline"]]
        component = [ArmTrade(**row) for row in blob["component"]]
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f"refused:malformed-arms -- {exc}", file=sys.stderr)
        return None
    return blob, baseline, component


def _print_badge(badge: dict) -> None:
    print(f"BADGE: {badge['verdict']}")
    for clause, ok in badge["clauses"].items():
        print(f"  {clause}: {'ok' if ok else 'FAIL'}")
    print(f"n={badge['n']} win_rate={badge['win_rate']} expectancy_r={badge['expectancy_r']} "
          f"scratch_timeout_share={badge['scratch_timeout_share']}")


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    loaded = _load(args.arms)
    if loaded is None:
        return 2
    blob, baseline, component = loaded
    try:
        added = [t for t in additive_added(baseline, component) if t.strategy == TURTLE_SOUP]
    except NotAdditive as exc:
        print(f"refused:not-additive -- {exc}", file=sys.stderr)
        return 2
    badge = {**rep.badge_check(added, min_n=args.min_n), "arms": str(args.arms),
             "stage": (blob.get("provenance") or {}).get("stage")}
    _print_badge(badge)
    if args.out_json is not None:
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        args.out_json.write_text(json.dumps(badge, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
