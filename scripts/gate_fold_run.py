"""Fold runner CLI -- TRAIN data only (assert_train_only guards the replay
inside run_backtest whenever gate_eval/gate_min_tier is used, via G92).

Usage:
    python scripts/gate_fold_run.py --strategy "Break & Retest" [--min-tier A]
    python scripts/gate_fold_run.py --all [--min-tier A]
Writes docs/superpowers/results/2026-07-gate-folds-{slug}.json
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from swingbot.core.backtest import ALL_STRATEGIES  # noqa: E402
from swingbot.core.gate.folds import apply_fold_gate, run_folds  # noqa: E402

OUT_DIR = "docs/superpowers/results"


def _slug(name: str) -> str:
    return name.lower().replace(" ", "-").replace("&", "and").replace("/", "-")


def run_one(strategy: str, min_tier: str | None) -> dict:
    baseline = run_folds(strategy, gate_min_tier=None)
    result = {"strategy": strategy, "baseline": baseline}
    if min_tier:
        filtered = run_folds(strategy, gate_min_tier=min_tier)
        result["filtered"] = filtered
        result["gate"] = apply_fold_gate(filtered["folds"], baseline["folds"])
    for label in ("baseline", "filtered"):
        if label in result:
            print(f"\n{strategy} [{label}]")
            for f in result[label]["folds"]:
                print(f"  {f['year']}: n={f['n']} wr={f['wr']} exp={f['expectancy_r']}")
            print(f"  pooled: {result[label]['pooled']}")
    result.get("gate") and print(f"  fold gate: {result['gate']}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--min-tier", default=None)
    args = parser.parse_args()
    strategies = ALL_STRATEGIES if args.all else [args.strategy]
    if not strategies[0]:
        parser.error("--strategy or --all required")
    os.makedirs(OUT_DIR, exist_ok=True)
    for strategy in strategies:
        result = run_one(strategy, args.min_tier)
        result_slim = {k: v for k, v in result.items()}
        for label in ("baseline", "filtered"):
            if label in result_slim:
                result_slim[label] = {k: v for k, v in result_slim[label].items()
                                      if k != "trades"}
        path = os.path.join(OUT_DIR, f"2026-07-gate-folds-{_slug(strategy)}.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(result_slim, fh, indent=2)
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
