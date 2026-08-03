#!/usr/bin/env python3
"""Turn the per-strategy V52 selectivity JSONs into the ladder tables (plan v8
V52 Steps 2-5). Reads only what `tune_selectivity.py` wrote -- it re-ranks
nothing and re-decides nothing, so the tables cannot disagree with the run.

The ladder gates are applied here exactly as pre-registered in
docs/superpowers/results/2026-08-03-v52-selectivity-ladder.md:

    Stage 1  Wilson LB > 60      Stage 2  LB > 70      Stage 3  LB > 80

always on the INDEPENDENT sample, never the point estimate, and never on a
cell below `min_cell_n`.

Usage: python scripts/summarize_v52_grid.py docs/superpowers/results/v52
"""
import json
import sys
from pathlib import Path

RUNGS = ((1, 60.0), (2, 70.0), (3, 80.0))


def _f(v, spec, dash="—"):
    return format(v, spec) if v is not None else dash


def eligible(rows, min_n):
    """A cell may be adopted only with enough independent evidence behind it.
    Cells under the bar are still reported -- they just cannot win."""
    return [r for r in rows if r["n_independent"] >= min_n and r["win_rate"] is not None]


def main():
    outdir = Path(sys.argv[1] if len(sys.argv) > 1
                  else "docs/superpowers/results/v52")
    files = sorted(outdir.glob("*.json"))
    if not files:
        sys.exit(f"no grid JSONs in {outdir}")
    payloads = [json.loads(p.read_text()) for p in files]
    min_n = payloads[0].get("min_cell_n", 20)
    print(f"Chunks found: {len(payloads)} / 11   (min_cell_n = {min_n})\n")

    print("## The ladder — did any cell clear any rung?\n")
    print("| Stage | bar (Wilson LB) | cells clearing | strategies |")
    print("|---|---|---|---|")
    cleared_any = False
    for stage, bar in RUNGS:
        hits = [(d["strategy"], r) for d in payloads
                for r in eligible(d["rows"], min_n) if r["wilson_lb"] > bar]
        names = sorted({s for s, _ in hits})
        if hits:
            cleared_any = True
        print(f"| Stage {stage} | > {bar:.0f}% | **{len(hits)}** | "
              f"{', '.join(names) if names else '—'} |")
    if not cleared_any:
        print("\n**No cell clears any rung.** Per V52 Step 2's gate the ladder "
              "stops here: nothing above Stage 1 can be real if Stage 1 is empty.")

    print("\n## Best cell per strategy, by Wilson LB (the honest frontier)\n")
    print("| Strategy | cell | cuts | N | N ind | WR | **LB** | ExpR | dead | "
          "loss med | runner R med | runner R mean | runner hold |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for d in sorted(payloads, key=lambda d: d["strategy"]):
        cand = eligible(d["rows"], min_n)
        if not cand:
            print(f"| {d['strategy']} | — | — | — | — | — | **no eligible cell** "
                  f"| — | — | — | — | — | — |")
            continue
        r = max(cand, key=lambda r: r["wilson_lb"])
        print(f"| {d['strategy']} | `{r['cell']}` | {r['cuts']} | {r['n_eval']} | "
              f"{r['n_independent']} | {_f(r['win_rate'], '.1f')}% | "
              f"**{r['wilson_lb']:.1f}%** | {_f(r['expectancy_r'], '+.3f')} | "
              f"{r['excluded_share'] * 100:.0f}% | "
              f"{_f(r.get('loss_pct_median'), '.2f')}% | "
              f"{_f(r.get('runner_r_median'), '+.2f')} | "
              f"{_f(r.get('runner_r_mean'), '+.2f')} | "
              f"{_f(r.get('runner_hold_median'), '.0f')}d |")

    print("\n## Best cell per strategy, by expectancy (the rule's actual objective)\n")
    print("| Strategy | cell | cuts | N ind | WR | LB | **ExpR** |")
    print("|---|---|---|---|---|---|---|")
    for d in sorted(payloads, key=lambda d: d["strategy"]):
        cand = [r for r in eligible(d["rows"], min_n) if r["expectancy_r"] is not None]
        if not cand:
            print(f"| {d['strategy']} | — | — | — | — | — | **none** |")
            continue
        r = max(cand, key=lambda r: r["expectancy_r"])
        print(f"| {d['strategy']} | `{r['cell']}` | {r['cuts']} | "
              f"{r['n_independent']} | {_f(r['win_rate'], '.1f')}% | "
              f"{r['wilson_lb']:.1f}% | **{r['expectancy_r']:+.3f}** |")

    print("\n## Does the loss cap actually bind?\n")
    print("| Strategy | median loss | p95 loss | max loss | share over 1.75% |")
    print("|---|---|---|---|---|")
    for d in sorted(payloads, key=lambda d: d["strategy"]):
        alls = [r for r in d["rows"] if r["cell"] == "all" and r["cuts"] == "none"]
        if not alls:
            continue
        r = alls[0]
        print(f"| {d['strategy']} | {_f(r.get('loss_pct_median'), '.2f')}% | "
              f"{_f(r.get('loss_pct_p95'), '.2f')}% | "
              f"{_f(r.get('loss_pct_max'), '.2f')}% | "
              f"{_f((r.get('loss_over_cap_share') or 0) * 100, '.1f')}% |")

    print("\n## The runner leg — what a win actually pays\n")
    print("V51 Step 2: a win realises `0.5 x 1.4286 + 0.5 x r_runner`, so "
          "break-even WR is 41.2% if runners match TP1, **58.3% if they stop at "
          "breakeven**, and the measured no-skill rate is 43.4%.\n")
    print("| Strategy | runners | R p25 | R median | R mean | R p75 | "
          "blended R per win | break-even WR |")
    print("|---|---|---|---|---|---|---|---|")
    for d in sorted(payloads, key=lambda d: d["strategy"]):
        alls = [r for r in d["rows"] if r["cell"] == "all" and r["cuts"] == "none"]
        if not alls or not alls[0].get("n_runners"):
            continue
        r = alls[0]
        med = r.get("runner_r_median")
        blended = None if med is None else 0.5 * 1.4286 + 0.5 * med
        be = None if not blended or blended <= 0 else 100.0 / (1.0 + blended)
        print(f"| {d['strategy']} | {r['n_runners']} | "
              f"{_f(r.get('runner_r_p25'), '+.2f')} | {_f(med, '+.2f')} | "
              f"{_f(r.get('runner_r_mean'), '+.2f')} | "
              f"{_f(r.get('runner_r_p75'), '+.2f')} | {_f(blended, '.3f')}R | "
              f"{_f(be, '.1f')}% |")

    print("\n## Which axis actually moves win rate?\n")
    print("Best LB reachable on each axis family, pooled across strategies "
          "(eligible cells only).\n")
    fams = {"score": "score>=", "tier(exact)": "tier=", "tier(<=)": "tier<=",
            "confluence": "confluence>=", "regime": "regime=", "all": "all"}
    print("| Axis family | best LB | cell | strategy |")
    print("|---|---|---|---|")
    for fam, prefix in fams.items():
        best, who = None, None
        for d in payloads:
            for r in eligible(d["rows"], min_n):
                if not r["cell"].startswith(prefix):
                    continue
                if best is None or r["wilson_lb"] > best["wilson_lb"]:
                    best, who = r, d["strategy"]
        if best:
            print(f"| {fam} | {best['wilson_lb']:.1f}% | `{best['cell']}` | {who} |")


if __name__ == "__main__":
    main()
