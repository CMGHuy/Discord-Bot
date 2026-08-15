"""Permutation reality check: is the edge distinguishable from luck?

Circularly shifting entry dates severs the entry-signal/price-future link
while preserving entry count, autocorrelation and the exit engine -- if
the un-shifted expectancy doesn't beat ~95% of shifted runs, the
'component' is noise wearing a lab coat.

Run: python scripts/permutation_test.py --component-json '{...}' [--n 200]
"""
import argparse
import json
import os
import sys

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
    import swingbot.core.backtest as bt
    from swingbot.core.backtest_wf import run_folds

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


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--component-json", default="{}")
    p.add_argument("--n", type=int, default=200)
    args = p.parse_args()
    run = _fold_run_fn(json.loads(args.component_json))
    real = run(0)
    permuted = permuted_expectancies(run, n_perm=args.n)
    pv = p_value(real, permuted)
    print(json.dumps({"real_expectancy": real, "p_value": pv,
                      "verdict": "REAL" if pv <= 0.05 else "INDISTINGUISHABLE FROM LUCK"},
                     indent=1))
