#!/usr/bin/env python3
"""The v72 acceptance funnel -- the single CLI that decides whether a
component ships.

Read docs/claude/backtest-methodology.md first. The clause set lives in
swingbot/core/backtesting/acceptance.py and is PRE-REGISTERED: a component
that fails is dropped and documented, never re-measured against a bar moved
to fit it.

Stages:
  mde          Is the hypothesis answerable at the N we can get? A TRAIN
               effect below the MDE means the shot is REFUSED and the
               budget stays unspent -- an unanswerable question wastes a
               shot whatever the answer looks like.
  walkforward  Score on fold-test years 2021/2022/2023. Free and
               repeatable. Clauses 1-4 and 6; no permutation required.
  validation   2024-01-01..2025-12-31. ONE shot, ever. All six clauses; a
               missing permutation p is a FAIL, not a skip.

Arms come from a JSON file the component's own measurement script wrote:
  {"baseline": [ArmTrade...], "component": [ArmTrade...]}

Exit code 0 = PASS / RESOLVABLE, 1 = FAIL / REFUSED.

Run:
  python scripts/backtest/validate_component.py --stage mde \\
      --arms data/mycomponent_train.json --title "v73 my component" \\
      --window "fold-train" --train-effect-pp 1.2 \\
      --observed-days 365 --target-days 730
  python scripts/backtest/validate_component.py --stage validation \\
      --arms data/mycomponent_validation.json --title "v73 my component" \\
      --window "2024-01-01..2025-12-31" --permutation-p 0.013 \\
      --out-md docs/superpowers/results/2026-XX-XX-v73-validation.md
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from swingbot.core.backtesting.acceptance import (  # noqa: E402
    ALPHA, BOOTSTRAP_RESAMPLES, GEOMETRY_MAX_DROP_PCT, NON_INFERIORITY_R,
    VOLUME_MAX_CUT_PCT, ArmTrade, AcceptanceResult, ClauseResult, evaluate,
    delta_standardised_win_rate, mde_win_rate, project_target_n,
    render_json, render_markdown, win_rate,
)
from swingbot.core.backtesting.backtest_wf import gate_win_rate  # noqa: E402

DECIDED = ("win", "loss")


def load_arms(path: Path) -> tuple:
    blob = json.loads(Path(path).read_text())
    to_arm = lambda rows: [ArmTrade(**r) for r in rows]
    return to_arm(blob["baseline"]), to_arm(blob["component"])


def load_folds(path: Path) -> list:
    blob = json.loads(Path(path).read_text())
    to_arm = lambda rows: [ArmTrade(**r) for r in rows]
    return [{"test_year": f["test_year"], "baseline": to_arm(f["baseline"]),
             "component": to_arm(f["component"])} for f in blob["folds"]]


def stage_mde(args) -> int:
    baseline, _ = load_arms(args.arms)
    observed = sum(1 for t in baseline if t.outcome in DECIDED)
    target_n = project_target_n(observed_n=observed,
                                observed_days=args.observed_days,
                                target_days=args.target_days)
    mde = mde_win_rate(baseline, target_n=target_n)
    wr = win_rate(baseline)
    print(f"observed decided N : {observed} over {args.observed_days}d")
    print(f"projected target N : {target_n} over {args.target_days}d")
    print(f"baseline win rate  : {'n/a' if wr is None else f'{wr:.2f}%'}")
    if mde is None:
        print("\nREFUSED -- no decided trades to estimate an MDE from.")
        return 1
    print(f"MDE (dWR, 80% power, one-sided 0.05): {mde:.3f}pp")
    print(f"TRAIN effect claimed               : {args.train_effect_pp:.3f}pp")
    if args.train_effect_pp < mde:
        print("\nREFUSED -- the TRAIN effect is below the minimum this "
              "sample can detect. The VALIDATION budget is NOT spent; "
              "record this as 'unresolvable, budget intact'.")
        return 1
    print("\nRESOLVABLE -- the shot may proceed.")
    return 0


def stage_walkforward(args) -> int:
    """Stage 2. Free and repeatable: a plain point-estimate per fold, no
    bootstrap -- consistency across fold-test years is the whole question,
    and gate_win_rate (C2) is the pre-registered rule for it."""
    folds = load_folds(args.arms)
    rows = []
    for f in folds:
        b, c = f["baseline"], f["component"]
        delta = delta_standardised_win_rate(b, c)
        n = min(sum(1 for t in b if t.outcome in DECIDED),
                sum(1 for t in c if t.outcome in DECIDED))
        rows.append({"test_years": f["test_year"], "delta_win_rate_pp": delta, "n": n})
        print(f"fold {f['test_year']}: dWR="
              f"{'n/a' if delta is None else f'{delta:+.2f}pp'} n={n}", flush=True)
    verdict = gate_win_rate({"folds": rows})
    print(f"\n{verdict} -- stage 2 walkforward win-rate consistency gate")
    if args.out_json:
        Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out_json).write_text(json.dumps({"verdict": verdict, "folds": rows}, indent=1))
    if args.out_md:
        lines = [f"# {args.title} — WALKFORWARD", "", f"Window: {args.window}", "",
                 "| fold | dWR (pp) | n |", "|---|---|---|"]
        for r in rows:
            d = r["delta_win_rate_pp"]
            d_str = "n/a" if d is None else f"{d:+.2f}"
            lines.append(f"| {r['test_years']} | {d_str} | {r['n']} |")
        lines += ["", f"**Overall: {verdict}**"]
        Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out_md).write_text("\n".join(lines) + "\n")
    return 0 if verdict == "PASS" else 1


def _write_skeleton(args, stage: str) -> None:
    """Pre-registration: the clause set and its thresholds go on disk
    before evaluate() runs, so nothing about what counts as a pass can be
    changed after the number is seen."""
    if not args.out_md and not args.out_json:
        return
    pending = lambda name, threshold: ClauseResult(name, "PENDING", "not yet run", None, threshold)
    skeleton = AcceptanceResult(
        stage=stage, verdict="PENDING",
        clauses=(
            pending("win_rate", 0.0), pending("profit_floor", NON_INFERIORITY_R),
            pending("geometry", GEOMETRY_MAX_DROP_PCT),
            pending("volume", VOLUME_MAX_CUT_PCT), pending("permutation", ALPHA),
            pending("mechanism", None)),
        strata=[], split={"removed": 0, "changed": 0, "unchanged": 0,
                         "added": 0, "is_subset": False})
    md = render_markdown(skeleton, title=args.title, window=args.window,
                         notes="PRE-REGISTERED skeleton -- written before "
                               "evaluate() runs; verdict pending.")
    if args.out_md:
        Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out_md).write_text(md)
    if args.out_json:
        Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out_json).write_text(json.dumps(render_json(skeleton), indent=1))


def _run_gate(args, stage: str) -> int:
    baseline, component = load_arms(args.arms)
    _write_skeleton(args, stage)
    result = evaluate(baseline, component, stage=stage,
                      permutation_p=args.permutation_p,
                      n_resamples=args.resamples, seed=args.seed)
    md = render_markdown(result, title=args.title, window=args.window,
                         notes=args.notes)
    print(md)
    if args.out_md:
        Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out_md).write_text(md)
        print(f"[wrote {args.out_md}]")
    if args.out_json:
        Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out_json).write_text(json.dumps(render_json(result), indent=1))
        print(f"[wrote {args.out_json}]")
    return 0 if result.verdict == "PASS" else 1


def stage_validation(args) -> int:
    return _run_gate(args, "validation")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage", required=True,
                    choices=("mde", "walkforward", "validation"))
    ap.add_argument("--arms", required=True, type=Path,
                    help='JSON: {"baseline": [...], "component": [...]}')
    ap.add_argument("--title", required=True, help="component name for the doc")
    ap.add_argument("--window", required=True, help="the window, for the record")
    ap.add_argument("--permutation-p", type=float, default=None,
                    help="p from permutation_test.py -- REQUIRED at --stage "
                         "validation")
    ap.add_argument("--train-effect-pp", type=float, default=0.0,
                    help="--stage mde: the dWR the TRAIN grid claimed")
    ap.add_argument("--observed-days", type=int, default=365)
    ap.add_argument("--target-days", type=int, default=730)
    ap.add_argument("--resamples", type=int, default=BOOTSTRAP_RESAMPLES)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--notes", default=None)
    ap.add_argument("--out-md", default=None)
    ap.add_argument("--out-json", default=None)
    args = ap.parse_args()
    return {"mde": stage_mde, "walkforward": stage_walkforward,
            "validation": stage_validation}[args.stage](args)


if __name__ == "__main__":
    raise SystemExit(main())
