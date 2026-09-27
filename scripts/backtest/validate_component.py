#!/usr/bin/env python3
"""The acceptance funnel, with v100 stamped-arm integrity guards."""
from __future__ import annotations
import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
from swingbot.core.backtesting.acceptance import ALPHA, BOOTSTRAP_RESAMPLES, GEOMETRY_MAX_DROP_PCT, NON_INFERIORITY_R, VOLUME_MAX_CUT_PCT, ArmTrade, AcceptanceResult, ClauseResult, evaluate, delta_expectancy_r, delta_standardised_win_rate, mde_paired, mde_win_rate, project_target_n, render_json, render_markdown  # noqa: E402
from swingbot.core.backtesting.acceptance_harvest import mde_expectancy_r  # noqa: E402
from swingbot.core.backtesting.arms import reachability  # noqa: E402
from swingbot.core.backtesting.arms.pairing import changed_outcomes, overlap  # noqa: E402
from swingbot.core.backtesting.arms.provenance import check_stamp  # noqa: E402
from swingbot.core.backtesting.backtest_wf import gate_win_rate  # noqa: E402
DECIDED = ("win", "loss")

def load_arms(path):
    blob = json.loads(Path(path).read_text())
    return [ArmTrade(**row) for row in blob["baseline"]], [ArmTrade(**row) for row in blob["component"]]

def load_folds(path):
    blob = json.loads(Path(path).read_text())
    return [{"test_year": fold["test_year"], "baseline": [ArmTrade(**row) for row in fold["baseline"]], "component": [ArmTrade(**row) for row in fold["component"]]} for fold in blob["folds"]]

def _folds_are_well_formed(folds):
    years = [fold["test_year"] for fold in folds]
    return len(years) == 3 and len(set(years)) == 3

def _full_universe():
    from measure_arms import cached_universe
    return cached_universe()

def _stamp_gate(args):
    if args.bespoke_instrument:
        print(f"BESPOKE INSTRUMENT: {args.bespoke_instrument}")
        return None
    token = check_stamp(json.loads(Path(args.arms).read_text()), funnel_stage=args.stage, full_universe=_full_universe())
    if token:
        print(f"{token} -- v100 stamp gate. Budget intact.", file=sys.stderr)
        return 1
    return None

def _stamp_observed_days(path):
    stamp = json.loads(Path(path).read_text()).get("provenance")
    if not stamp: return None
    start, end = (dt.date.fromisoformat(value) for value in stamp["signal_window"])
    return (end - start).days + 1

def stage_reachability(args):
    blob = json.loads(Path(args.arms).read_text()); delta = (blob.get("provenance") or {}).get("knob_delta") or {}
    for attr in delta:
        cls = reachability.classify(attr)
        if cls != reachability.REACHABLE:
            print(f"refused:unreachable:{cls} -- {reachability.reason(attr)} Budget intact.", file=sys.stderr); return 1
    baseline, component = load_arms(args.arms); changed = changed_outcomes(baseline, component)
    print(f"knobs: {delta} baseline N={len(baseline)} component N={len(component)} changed outcomes: {changed}")
    if not changed:
        print("refused:zero-diff -- the component reached no trade. Budget intact.", file=sys.stderr); return 1
    print("REACHABLE -- the component changes trades; Stage 0 may proceed."); return 0

def _mde_design(args, baseline, component):
    harvest = args.gate == "harvest"
    counted = ("win", "loss", "scratch", "timeout") if harvest else DECIDED
    observed = sum(trade.outcome in counted for trade in baseline)
    days = args.observed_days or _stamp_observed_days(args.arms) or 365
    target = project_target_n(observed_n=observed, observed_days=days, target_days=args.target_days)
    statistic = delta_expectancy_r if harvest else delta_standardised_win_rate
    unpaired = mde_expectancy_r(baseline, target_n=target) if harvest else mde_win_rate(baseline, target_n=target)
    paired = None
    if overlap(baseline, component):
        paired = mde_paired(baseline, component, statistic, observed_n=observed,
                            target_n=target, n_resamples=args.resamples, seed=args.seed)
    return harvest, observed, days, target, paired, unpaired

def stage_mde(args):
    baseline, component = load_arms(args.arms)
    harvest, observed, days, target, paired, unpaired = _mde_design(args, baseline, component)
    use_paired = args.mde_method == "paired" and paired is not None
    mde = paired if use_paired else unpaired
    claimed = args.train_effect_r if harvest else args.train_effect_pp
    unit, label = ("R", "dExpR") if harvest else ("pp", "dWR")
    print(f"observed N         : {observed} over {days}d\nprojected target N : {target} over {args.target_days}d")
    print(f"paired MDE   ({label}): {'n/a' if paired is None else f'{paired:.4f}{unit}'}\nunpaired MDE ({label}): {'n/a' if unpaired is None else f'{unpaired:.4f}{unit}'}\ngating on: {'paired' if use_paired else 'unpaired'}")
    if mde is None or claimed < mde:
        print("REFUSED -- the TRAIN effect is below the minimum this sample can detect. Budget intact."); return 1
    print("RESOLVABLE -- the shot may proceed."); return 0

def _notes(args):
    if not getattr(args, "bespoke_instrument", None): return args.notes
    prefix = f"BESPOKE INSTRUMENT (not measure_arms.py): {args.bespoke_instrument}."
    return f"{prefix} {args.notes}" if args.notes else prefix

def stage_walkforward(args):
    folds = load_folds(args.arms)
    if not _folds_are_well_formed(folds): print("REFUSED -- gate_win_rate requires exactly 3 folds with distinct test_year values."); return 1
    rows = [{"test_years": fold["test_year"], "delta_win_rate_pp": delta_standardised_win_rate(fold["baseline"], fold["component"]), "n": min(sum(t.outcome in DECIDED for t in fold["baseline"]), sum(t.outcome in DECIDED for t in fold["component"]))} for fold in folds]
    verdict = gate_win_rate({"folds": rows}); print(f"{verdict} -- stage 2 walkforward win-rate consistency gate")
    if args.out_json: Path(args.out_json).parent.mkdir(parents=True, exist_ok=True); Path(args.out_json).write_text(json.dumps({"verdict": verdict, "folds": rows}, indent=1), encoding="utf-8")
    return 0 if verdict == "PASS" else 1

def _write_skeleton(args, stage):
    if not args.out_md and not args.out_json: return
    pending = lambda name, threshold: ClauseResult(name, "PENDING", "not yet run", None, threshold)
    result = AcceptanceResult(stage=stage, verdict="PENDING", seed=args.seed, clauses=(pending("win_rate", 0.0), pending("profit_floor", NON_INFERIORITY_R), pending("geometry", GEOMETRY_MAX_DROP_PCT), pending("volume", VOLUME_MAX_CUT_PCT), pending("permutation", ALPHA), pending("mechanism", None)), strata=[], split={"removed": 0,"changed": 0,"unchanged": 0,"added": 0,"is_subset": False})
    markdown = render_markdown(result, title=args.title, window=args.window, notes="PRE-REGISTERED skeleton -- verdict pending.")
    if args.out_md: Path(args.out_md).parent.mkdir(parents=True, exist_ok=True); Path(args.out_md).write_text(markdown, encoding="utf-8")
    if args.out_json: Path(args.out_json).parent.mkdir(parents=True, exist_ok=True); Path(args.out_json).write_text(json.dumps(render_json(result), indent=1), encoding="utf-8")

def _run_gate(args, stage):
    baseline, component = load_arms(args.arms); _write_skeleton(args, stage)
    result = evaluate(baseline, component, stage=stage, permutation_p=args.permutation_p, n_resamples=args.resamples, seed=args.seed)
    markdown = render_markdown(result, title=args.title, window=args.window, notes=_notes(args)); print(markdown)
    if args.out_md: Path(args.out_md).parent.mkdir(parents=True, exist_ok=True); Path(args.out_md).write_text(markdown, encoding="utf-8")
    if args.out_json: Path(args.out_json).parent.mkdir(parents=True, exist_ok=True); Path(args.out_json).write_text(json.dumps(render_json(result), indent=1), encoding="utf-8")
    return 0 if result.verdict == "PASS" else 1

def stage_validation(args): return _run_gate(args, "validation")

def main(argv=None):
    parser = argparse.ArgumentParser(); parser.add_argument("--stage", required=True, choices=("reachability", "mde", "walkforward", "validation")); parser.add_argument("--arms", required=True, type=Path); parser.add_argument("--title", required=True); parser.add_argument("--window", required=True)
    parser.add_argument("--permutation-p", type=float, default=None); parser.add_argument("--train-effect-pp", type=float, default=0.0); parser.add_argument("--train-effect-r", type=float, default=0.0); parser.add_argument("--observed-days", type=int, default=None); parser.add_argument("--target-days", type=int, default=730); parser.add_argument("--resamples", type=int, default=BOOTSTRAP_RESAMPLES); parser.add_argument("--seed", type=int, default=42); parser.add_argument("--notes", default=None); parser.add_argument("--out-md", default=None); parser.add_argument("--out-json", default=None); parser.add_argument("--bespoke-instrument", default=None); parser.add_argument("--mde-method", choices=("paired", "unpaired"), default="paired"); parser.add_argument("--gate", choices=("win_rate", "harvest"), default="win_rate")
    args = parser.parse_args(argv); refused = _stamp_gate(args)
    if refused is not None: return refused
    return {"reachability": stage_reachability,"mde": stage_mde,"walkforward": stage_walkforward,"validation": stage_validation}[args.stage](args)

if __name__ == "__main__": raise SystemExit(main())
