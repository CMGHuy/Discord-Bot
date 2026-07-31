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
from swingbot.core.gate.folds import (ablate_flags, apply_fold_gate,  # noqa: E402
                                      fold_windows, overfit_sentinel,
                                      run_folds)

OUT_DIR = "docs/superpowers/results"


def _slug(name: str) -> str:
    return name.lower().replace(" ", "-").replace("&", "and").replace("/", "-")


def _trades_by_fold(trades: list[dict]) -> dict:
    """Split a strategy's pooled (annotate-only) trade list back out by fold
    year, using entry_date -- run_folds itself only returns pooled trades,
    not a per-fold breakdown."""
    windows = fold_windows()
    out = {}
    for w in windows:
        year = str(w["year"])
        out[year] = [t for t in trades if str(t.get("entry_date", ""))[:4] == year]
    return out


def run_ablation(strategy: str) -> dict:
    """Annotate-only folds, then ablate_flags pooled + per fold."""
    print(f"\n=== {strategy}: ablation run (annotate-only) ===", flush=True)
    result = run_folds(strategy, gate_min_tier=None, verbose=True)
    trades = result["trades"]
    pooled = ablate_flags(trades)
    by_fold = _trades_by_fold(trades)
    per_fold = {year: ablate_flags(fold_trades) for year, fold_trades in by_fold.items()}
    print(f"  pooled ablation: {pooled}")
    for year, rows in per_fold.items():
        print(f"  {year} ablation: {rows}")
    return {"strategy": strategy, "pooled": pooled, "per_fold": per_fold}


def run_one(strategy: str, min_tier: str | None) -> dict:
    print(f"\n=== {strategy}: baseline run ===", flush=True)
    baseline = run_folds(strategy, gate_min_tier=None, verbose=True)
    result = {"strategy": strategy, "baseline": baseline}
    pct_kept = None
    sentinel_target = baseline
    if min_tier:
        print(f"=== {strategy}: filtered run (min_tier={min_tier}) ===", flush=True)
        filtered = run_folds(strategy, gate_min_tier=min_tier, verbose=True)
        result["filtered"] = filtered
        result["gate"] = apply_fold_gate(filtered["folds"], baseline["folds"])
        base_n = baseline["pooled"]["n"]
        filt_n = filtered["pooled"]["n"]
        pct_kept = round(100.0 * filt_n / base_n, 1) if base_n else None
        sentinel_target = filtered
    # G110: no separate TRAIN-period score exists in this fold runner (each
    # fold IS the test window; there is no distinct train_wr to compare
    # against here) -- train_wr stays None, so only the pct_kept/pooled-N
    # rules are live in this CLI's wiring.
    result["overfit_warnings"] = overfit_sentinel(sentinel_target, train_wr=None,
                                                  pct_kept=pct_kept)
    for label in ("baseline", "filtered"):
        if label in result:
            print(f"\n{strategy} [{label}]")
            for f in result[label]["folds"]:
                print(f"  {f['year']}: n={f['n']} wr={f['wr']} exp={f['expectancy_r']}")
            print(f"  pooled: {result[label]['pooled']}")
    result.get("gate") and print(f"  fold gate: {result['gate']}")
    for w in result["overfit_warnings"]:
        print(f"  OVERFIT SENTINEL: {w}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--min-tier", default=None)
    parser.add_argument("--ablate", action="store_true",
                        help="run per-flag ablation instead of the baseline/filtered fold report")
    args = parser.parse_args()
    strategies = ALL_STRATEGIES if args.all else [args.strategy]
    if not strategies[0]:
        parser.error("--strategy or --all required")
    os.makedirs(OUT_DIR, exist_ok=True)
    for si, strategy in enumerate(strategies, 1):
        print(f"\n########## strategy {si}/{len(strategies)}: {strategy} ##########",
              flush=True)
        if args.ablate:
            result_slim = run_ablation(strategy)
            path = os.path.join(OUT_DIR, f"2026-07-gate-ablation-{_slug(strategy)}.json")
        else:
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
