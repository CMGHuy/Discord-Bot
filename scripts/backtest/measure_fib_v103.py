#!/usr/bin/env python3
"""v103 Fibonacci level-stop (A) and continuation (C) measurement funnel."""
from __future__ import annotations

import argparse
import collections
import contextlib
import json
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(Path(__file__).resolve().parent)]

import fib_funnel
from fib_funnel import BOOTSTRAP_SEED, MIN_N_TRAIN, MIN_N_VALIDATION, cell_key, dir_rows
from measure_bearish_arms import _unmasked_gates, apply_laggard_rule
from measure_fib_confluence import TRAIN_EXT, VALIDATION, Progress, _load_frames, _write, require_ext_cache
from run_backtest_range import _build_asof_map, merge_registry, window_trades
from swingbot import config
from swingbot.core.backtesting.acceptance import BOOTSTRAP_RESAMPLES
from swingbot.core.backtesting.backtest import run_backtest
from swingbot.core.market.entry_filters import DEFAULT_PARAMS, entries_for, gate_override
from swingbot.core.market.strategy_types import HORIZONS, STRATEGY_GATES

DIRECTIONS = ("bullish", "bearish")
ALL_HZ = tuple(HORIZONS)
_MISSING = object()
MECHANISMS = {
    "A": SimpleNamespace(strategy="Fibonacci", grid=(0.1, 0.25, 0.5), loosest=0.1, baseline=0.0),
    "C": SimpleNamespace(strategy="Fibonacci Continuation", grid=(0.5, 0.618, 0.786), loosest=0.786, baseline=None),
}


@contextlib.contextmanager
def _config_values(**values):
    saved = {key: getattr(config, key, _MISSING) for key in values}
    try:
        for key, value in values.items():
            setattr(config, key, value)
        yield
    finally:
        for key, value in saved.items():
            if value is _MISSING:
                delattr(config, key)
            else:
                setattr(config, key, value)


@contextlib.contextmanager
def _param_value(strategy, key, value):
    params = DEFAULT_PARAMS[strategy]
    previous = params[key]
    params[key] = value
    try:
        yield
    finally:
        params[key] = previous


def mechanism_cell(mech, value):
    if mech == "A":
        enabled = float(value) > 0
        return _config_values(FIB_LEVEL_STOP_ATR=float(value), FIB_LEVEL_STOP_DIRECTIONS="bullish,bearish" if enabled else "")
    return _param_value(MECHANISMS["C"].strategy, "d_max", float(value))


def direction_gate(strategy, direction):
    gates = STRATEGY_GATES.get(strategy) or {}
    directions = gates.get("directions")
    if directions is not None and direction not in directions:
        return gate_override(strategy, _unmasked_gates(strategy))
    return contextlib.nullcontext()


def _row(ticker, horizon_key, trade):
    return {"ticker": ticker, "horizon_key": horizon_key, "direction": trade.direction,
            "entry_date": trade.entry_date, "outcome": trade.outcome, "r_multiple": trade.r_multiple}


def _direction_pass(strategy, frames, asof_map, direction, window, horizons, run_fn, progress, label):
    raw = []
    with direction_gate(strategy, direction):
        for ticker, frame in sorted(frames.items()):
            progress.tick(f"{label} {direction} {ticker}")
            for horizon in horizons:
                summary = run_fn(ticker, frame, strategy, horizon, one_at_a_time=True, exit_model="v2", scale_out=True, tp2_mode="levels", frictions=True, asof=asof_map.get(ticker))
                raw.extend({"ticker": ticker, "horizon_key": horizon, "trade": trade} for trade in window_trades(summary, *window) if trade.direction == direction)
    if direction == "bearish":
        raw = apply_laggard_rule(raw)
    return [_row(row["ticker"], row["horizon_key"], row["trade"]) for row in raw]


def collect_trades(mech, frames, asof_map, value, window, *, directions=DIRECTIONS, horizons=ALL_HZ, run_fn=None, progress=None):
    spec = MECHANISMS[mech]
    run_fn = run_fn or run_backtest
    progress = progress or Progress(len(frames) * len(directions))
    rows = []
    with mechanism_cell(mech, value):
        for direction in directions:
            rows.extend(_direction_pass(spec.strategy, frames, asof_map, direction, window, horizons, run_fn, progress, f"{mech} {cell_key(value)}"))
    return rows


def _signal_years(strategy, frame, horizon, direction):
    bullish, bearish = entries_for(strategy, frame, horizon)
    series = bullish if direction == "bullish" else bearish
    dates = frame.index[series.to_numpy(dtype=bool)].strftime("%Y-%m-%d")
    return [date[:4] for date in dates if TRAIN_EXT[0] <= date <= TRAIN_EXT[1]]


def _count_direction(strategy, frames, direction, horizons):
    by_year, by_horizon = collections.Counter(), collections.Counter()
    with direction_gate(strategy, direction):
        for frame in frames.values():
            for horizon in horizons:
                years = _signal_years(strategy, frame, horizon, direction)
                by_year.update(years)
                by_horizon[horizon] += len(years)
    return {"total": sum(by_year.values()), "by_year": dict(sorted(by_year.items())), "by_horizon": {horizon: by_horizon[horizon] for horizon in horizons}}


def count_signals(mech, frames, values, *, horizons=ALL_HZ):
    strategy, results = MECHANISMS[mech].strategy, {}
    for value in values:
        with mechanism_cell(mech, value):
            for direction in DIRECTIONS:
                results[f"{cell_key(value)}|{direction}"] = _count_direction(strategy, frames, direction, horizons)
    return results


def stage0_closures(counts, mech):
    key = cell_key(MECHANISMS[mech].loosest)
    return [direction for direction in DIRECTIONS if counts[f"{key}|{direction}"]["total"] < MIN_N_TRAIN]


def _evaluate_direction(spec, rows_by_cell, direction, n_resamples, seed):
    stage1 = fib_funnel.stage1(rows_by_cell, direction, spec.grid, n_resamples=n_resamples, seed=seed)
    stage2 = fib_funnel.stage2(rows_by_cell, direction, spec.grid)
    proceed = stage1["winner"] is not None and stage2["verdict"]["clears"]
    baseline = fib_funnel.pooled(dir_rows(rows_by_cell[cell_key(spec.baseline)], direction)) if spec.baseline is not None else None
    return {"baseline": baseline, "stage1": stage1, "stage2": stage2, "proceed_to_validation": proceed, "validation_cell": stage1["winner"] if proceed else None, "tier": stage1["winner_tier"] if proceed else None}


def evaluate(mech, rows_by_cell, *, closed=(), n_resamples=BOOTSTRAP_RESAMPLES, seed=BOOTSTRAP_SEED):
    spec = MECHANISMS[mech]
    result = {"mechanism": mech, "strategy": spec.strategy}
    for direction in DIRECTIONS:
        result[direction] = ({"closed_at": "stage0", "proceed_to_validation": False, "validation_cell": None, "tier": None} if direction in closed else _evaluate_direction(spec, rows_by_cell, direction, n_resamples, seed))
    return result


def validation_verdict(rows, tier, *, n_resamples=BOOTSTRAP_RESAMPLES, seed=BOOTSTRAP_SEED):
    scored = fib_funnel.score_cell(rows, MIN_N_VALIDATION, n_resamples=n_resamples, seed=seed)
    key = "tier1" if tier == 1 else "tier2"
    return {"tier": tier, "stats": scored["stats"], "lower_bound": scored["lower_bound"], "clauses": scored[key]["clauses"], "passes": scored[key]["clears"]}


def require_committed(path):
    path = Path(path).resolve()
    tracked = subprocess.run(["git", "ls-files", "--error-unmatch", str(path)], cwd=ROOT, capture_output=True)
    clean = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", str(path)], cwd=ROOT, capture_output=True)
    if tracked.returncode != 0 or clean.returncode != 0:
        raise SystemExit(f"must be committed before VALIDATION: {path}")


def registry_status(payloads, rows):
    tiers = {payload["verdict"]["tier"] for payload in payloads}
    badge = fib_funnel.badge_verdict(fib_funnel.pooled(rows), MIN_N_VALIDATION)["clears"]
    return "VALIDATED" if tiers == {1} and badge else "WEAK"


def registry_record(strategy, rows, status, run_date):
    stats = fib_funnel.pooled(rows)
    return {"source": "strategy", "strategy": strategy, "horizon": None, "status": status, "n": stats["n"], "win_rate": None if stats["win_rate"] is None else round(stats["win_rate"], 1), "expectancy_r": None if stats["expectancy_r"] is None else round(stats["expectancy_r"], 3), "window": f"{VALIDATION[0]}..{VALIDATION[1]}", "run_date": run_date}


def _frames_and_asof(args):
    require_ext_cache()
    frames = _load_frames(args.universe, args.tickers)
    return frames, _build_asof_map(list(frames), frames, args.universe)


def _cmd_count(args):
    require_ext_cache()
    spec = MECHANISMS[args.mechanism]
    frames = _load_frames(args.universe, args.tickers)
    values = ((spec.baseline,) if spec.baseline is not None else ()) + spec.grid
    counts = count_signals(args.mechanism, frames, values)
    _write(args.out, {"mechanism": args.mechanism, "universe_n": len(frames), "counts": counts, "closed_at_stage0": stage0_closures(counts, args.mechanism)})


def _cmd_collect(args):
    started, spec = time.monotonic(), MECHANISMS[args.mechanism]
    closed = json.loads(Path(args.stage0).read_text(encoding="utf-8"))["closed_at_stage0"]
    directions = tuple(direction for direction in DIRECTIONS if direction not in closed)
    if not directions:
        raise SystemExit(f"{args.mechanism}: every direction closed at Stage 0")
    frames, asof_map = _frames_and_asof(args)
    values = ((spec.baseline,) if spec.baseline is not None else ()) + spec.grid
    progress = Progress(len(values) * len(frames) * len(directions))
    rows_by_cell = {cell_key(value): collect_trades(args.mechanism, frames, asof_map, value, TRAIN_EXT, directions=directions, progress=progress) for value in values}
    _write(args.out, {"mechanism": args.mechanism, "window": TRAIN_EXT, "universe_n": len(frames), "closed_at_stage0": closed, "rows_by_cell": rows_by_cell, "elapsed_s": round(time.monotonic() - started, 1)})


def _cmd_evaluate(args):
    collected = json.loads(Path(args.rows).read_text(encoding="utf-8"))
    _write(args.out, evaluate(collected["mechanism"], collected["rows_by_cell"], closed=tuple(collected["closed_at_stage0"])))


def _validation_target(args):
    require_committed(args.preregistration)
    require_committed(args.evaluate)
    evaluated = json.loads(Path(args.evaluate).read_text(encoding="utf-8"))
    if evaluated.get("mechanism") != args.mechanism:
        raise SystemExit(f"--evaluate is for mechanism {evaluated.get('mechanism')}, not {args.mechanism}")
    cell = evaluated[args.direction]
    if not cell.get("proceed_to_validation"):
        raise SystemExit(f"{args.mechanism} {args.direction} did not proceed to VALIDATION")
    return cell["validation_cell"], cell["tier"]


def _cmd_validation(args):
    if Path(args.out).exists():
        raise SystemExit(f"VALIDATION is one shot, ever: {args.out} already exists")
    value, tier = _validation_target(args)
    frames, asof_map = _frames_and_asof(args)
    rows = collect_trades(args.mechanism, frames, asof_map, value, VALIDATION, directions=(args.direction,))
    _write(args.out, {"mechanism": args.mechanism, "strategy": MECHANISMS[args.mechanism].strategy, "direction": args.direction, "cell": value, "preregistration": str(args.preregistration), "verdict": validation_verdict(rows, tier), "rows": rows})


def _cmd_emit(args):
    payloads = [json.loads(Path(path).read_text(encoding="utf-8")) for path in args.validation_json]
    if len({payload["mechanism"] for payload in payloads}) != 1:
        raise SystemExit("one mechanism per registry row")
    if not all(payload["verdict"]["passes"] for payload in payloads):
        raise SystemExit("refusing to emit a failing VALIDATION")
    rows = [row for payload in payloads for row in payload["rows"]]
    merge_registry(args.registry, [registry_record(payloads[0]["strategy"], rows, registry_status(payloads, rows), args.run_date)])


def _parser():
    parser = argparse.ArgumentParser(description="v103 Fibonacci level-stop / continuation funnel")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("count", "collect", "validation"):
        command = sub.add_parser(name)
        command.add_argument("--mechanism", required=True, choices=tuple(MECHANISMS))
        command.add_argument("--out", required=True)
        command.add_argument("--universe")
        command.add_argument("--tickers", help="comma-separated subset, smoke runs only")
    sub.choices["collect"].add_argument("--stage0", required=True)
    validation = sub.choices["validation"]
    validation.add_argument("--direction", required=True, choices=DIRECTIONS)
    validation.add_argument("--evaluate", required=True)
    validation.add_argument("--preregistration", required=True)
    evaluate_parser = sub.add_parser("evaluate")
    evaluate_parser.add_argument("--rows", required=True)
    evaluate_parser.add_argument("--out", required=True)
    emit = sub.add_parser("emit-registry")
    emit.add_argument("--validation-json", nargs="+", required=True)
    emit.add_argument("--registry", required=True)
    emit.add_argument("--run-date", required=True)
    return parser


COMMANDS = {"count": _cmd_count, "collect": _cmd_collect, "evaluate": _cmd_evaluate, "validation": _cmd_validation, "emit-registry": _cmd_emit}


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    COMMANDS[args.cmd](args)
    print(f"v103 {args.cmd} done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
