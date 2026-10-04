"""Permutation reality check: is the edge distinguishable from luck?

Circularly shifting entry dates severs the entry-signal/price-future link
while preserving entry count, autocorrelation and the exit engine -- if
the un-shifted expectancy doesn't beat ~95% of shifted runs, the
'component' is noise wearing a lab coat.

Run: python scripts/backtest/permutation_test.py --component-json '{...}' [--n 200]
     python scripts/backtest/permutation_test.py --arms stamped.json [--n 200 --seed 42]
"""
import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def permuted_expectancies(run_fn, n_perm: int = 200, seed: int = 42) -> list:
    rng = np.random.default_rng(seed)
    shifts = rng.integers(20, 200, size=n_perm)   # >= 20 bars so nothing 'almost' aligns
    return [float(run_fn(int(s))) for s in shifts]


def p_value(real_expectancy: float, permuted: list) -> float:
    if not permuted:
        return 1.0
    return float(np.mean([p >= real_expectancy for p in permuted]))


def _fold_run_fn(overrides: dict):
    """Returns run_fn(shift) -> pooled test expectancy with entries rolled."""
    import swingbot.core.backtesting.backtest as bt
    from swingbot.core.backtesting.backtest_wf import run_folds

    def run(shift: int) -> float:
        bt.ENTRY_SHIFT = shift
        try:
            r = run_folds(overrides)
            deltas = [f["component"]["expectancy_r"] for f in r["folds"]
                      if f["component"]["expectancy_r"] is not None]
            return sum(deltas) / len(deltas) if deltas else 0.0
        finally:
            bt.ENTRY_SHIFT = 0
    return run


SHIFT_RANGE = (20, 200)


def _sort_key(trade):
    return (trade.entry_date, trade.strategy, trade.horizon_key,
            trade.source or "", trade.direction or "")


def _labelled_by_ticker(baseline, removed_keys) -> list:
    groups: dict = {}
    for trade in sorted(baseline, key=lambda item: (item.ticker, _sort_key(item))):
        groups.setdefault(trade.ticker, []).append(trade)
    return [(trades, np.array([trade.key in removed_keys for trade in trades]))
            for trades in groups.values()]


def _null_component(groups, added, shift) -> list:
    kept = []
    for trades, labels in groups:
        rolled = np.roll(labels, shift % len(labels))
        kept.extend(trade for trade, gone in zip(trades, rolled) if not gone)
    return kept + list(added)


def arm_pair_permutation(baseline, component, n_perm: int = 200, seed: int = 42) -> dict:
    """P-value on standardised delta win rate for a stamped arm pair."""
    from swingbot.core.backtesting.acceptance import delta_standardised_win_rate, population_split

    split = population_split(baseline, component)
    groups = _labelled_by_ticker(baseline, {trade.key for trade in split["removed"]})
    observed = delta_standardised_win_rate(baseline, component)
    shifts = np.random.default_rng(seed).integers(*SHIFT_RANGE, size=n_perm)
    null = [delta_standardised_win_rate(
        baseline, _null_component(groups, split["added"], int(shift))) for shift in shifts]
    valid = [value for value in null if value is not None]
    p = None if observed is None or not valid else float(np.mean([value >= observed for value in valid]))
    return {"observed_delta_win_rate_pp": observed, "p_value": p, "n": int(n_perm),
            "n_valid": len(valid), "seed": seed, "shift_range": list(SHIFT_RANGE),
            "removed": len(split["removed"]), "added": len(split["added"]),
            "changed": len(split["changed"])}


def _arms_main(args) -> int:
    from swingbot.core.backtesting.acceptance import ArmTrade

    blob = json.loads(Path(args.arms).read_text(encoding="utf-8"))
    if not blob.get("provenance"):
        print("refused:unstamped -- --arms needs a measure_arms.py stamped file.", file=sys.stderr)
        return 1
    baseline = [ArmTrade(**row) for row in blob["baseline"]]
    component = [ArmTrade(**row) for row in blob["component"]]
    out = arm_pair_permutation(baseline, component, n_perm=args.n, seed=args.seed)
    out["verdict"] = ("REAL" if out["p_value"] is not None and out["p_value"] < 0.05
                      else "INDISTINGUISHABLE FROM LUCK")
    print(json.dumps(out, indent=1))
    return 0


def _parser():
    p = argparse.ArgumentParser()
    p.add_argument("--component-json", default="{}")
    p.add_argument("--n", type=int, default=200)
    p.add_argument("--arms", default=None)
    p.add_argument("--seed", type=int, default=42)
    return p


def _fold_main(args) -> int:
    run = _fold_run_fn(json.loads(args.component_json))
    real = run(0)
    permuted = permuted_expectancies(run, n_perm=args.n)
    pv = p_value(real, permuted)
    print(json.dumps({"real_expectancy": real, "p_value": pv,
                      "verdict": "REAL" if pv <= 0.05 else "INDISTINGUISHABLE FROM LUCK"},
                     indent=1))
    return 0


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    return _arms_main(args) if args.arms else _fold_main(args)


if __name__ == "__main__":
    sys.exit(main())
