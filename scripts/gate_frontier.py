"""Frontier CLI over annotated TRAIN trades.

Usage: python scripts/gate_frontier.py [--strategy "Break & Retest"]
Reruns run_folds (annotate-only), prints per-strategy frontier tables,
writes docs/superpowers/results/2026-07-gate-frontier-{slug}.json and a
G95 tier-cut proposal file when one is supported.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from swingbot.core.backtest import ALL_STRATEGIES  # noqa: E402
from swingbot.core.gate.folds import run_folds  # noqa: E402
from swingbot.core.gate.frontier import (best_cut, frontier,  # noqa: E402
                                         propose_tier_cuts, write_proposal,
                                         wr_by_decile)

OUT_DIR = "docs/superpowers/results"


def _slug(name):
    return name.lower().replace(" ", "-").replace("&", "and").replace("/", "-")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", default=None)
    args = parser.parse_args()
    strategies = [args.strategy] if args.strategy else list(ALL_STRATEGIES)
    os.makedirs(OUT_DIR, exist_ok=True)
    for si, strategy in enumerate(strategies, 1):
        print(f"\n########## strategy {si}/{len(strategies)}: {strategy} ##########",
              flush=True)
        trades = run_folds(strategy, verbose=True)["trades"]
        rows = frontier(trades)
        chosen = best_cut(rows, min_n=30, max_signal_loss_pct=40.0)
        proposal = propose_tier_cuts(rows)
        print(f"\n== {strategy} ==")
        print(f"{'cut':>4} {'N':>5} {'kept%':>6} {'WR':>6} {'LB':>6} {'exp':>6} {'tr/mo':>6}")
        for r in rows:
            print(f"{r['cut']:>4} {r['n_kept']:>5} {r['pct_kept']:>6} "
                  f"{r['wr'] if r['wr'] is not None else '—':>6} "
                  f"{r['wilson_lb']:>6} "
                  f"{r['expectancy_r'] if r['expectancy_r'] is not None else '—':>6} "
                  f"{r['trades_per_month']:>6}")
        print(f"best cut (N>=30, <=40% loss): {chosen}")
        artifact = {"strategy": strategy, "frontier": rows,
                    "deciles": wr_by_decile(trades),
                    "best_cut": chosen, "proposal": proposal}
        path = os.path.join(OUT_DIR, f"2026-07-gate-frontier-{_slug(strategy)}.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(artifact, fh, indent=2)
        print(f"wrote {path}")
        if proposal:
            print(f"proposal -> {write_proposal(proposal, kind=f'gate-tiers-{_slug(strategy)}')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
