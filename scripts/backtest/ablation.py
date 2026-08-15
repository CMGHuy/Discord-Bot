# scripts/ablation.py
"""Leave-one-out ablation over the adopted component set.
Run: python scripts/ablation.py"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from swingbot.core.backtest_wf import run_folds  # noqa: E402

ADOPTED_PATH = "docs/superpowers/results/adopted_components.json"

if __name__ == "__main__":
    with open(ADOPTED_PATH, encoding="utf-8") as f:
        adopted: dict = json.load(f)          # {"REGIME_GATES_ENABLED": true, ...}

    full = run_folds(adopted)
    print(f"full system pooled Δ: {full['pooled_delta_expectancy_r']:+.4f}R")
    rows = []
    for key in adopted:
        subset = {k: v for k, v in adopted.items() if k != key}
        r = run_folds(subset)
        contribution = full["pooled_delta_expectancy_r"] - r["pooled_delta_expectancy_r"]
        rows.append((key, contribution))
        print(f"without {key:<32} contribution {contribution:+.4f}R")
    rows.sort(key=lambda x: x[1])
    weak = [k for k, c in rows if c < 0.01]
    print("\nremoval candidates (<0.01R):", weak or "none")
