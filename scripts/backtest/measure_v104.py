#!/usr/bin/env python3
"""v104 measurement: Part A structural stops (15 cells) and Part B shorts (B1-B3).

Stages (spec §5): count (B Stage 0) -> collect -> evaluate (Stages 1-2 on
TRAIN) -> holdout (Stage 3: one shot per candidate, thin-holdout rule) ->
emit-registry. Reads the EXTENDED cache only:
  BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/backtest/measure_v104.py <command> ...
"""
from __future__ import annotations

import argparse
import collections
import contextlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(Path(__file__).resolve().parent)]

import funnel  # noqa: E402
from funnel import BOOTSTRAP_SEED, MIN_N_TRAIN, MIN_N_VALIDATION, cell_key  # noqa: E402
from measure_bearish_arms import apply_laggard_rule  # noqa: E402
from measure_fib_confluence import Progress, _load_frames, _write, require_ext_cache  # noqa: E402
from measure_fib_v103 import require_committed  # noqa: E402
from run_backtest_range import _build_asof_map, merge_registry, window_trades  # noqa: E402
from swingbot import config  # noqa: E402
from swingbot.core.backtesting.acceptance import BOOTSTRAP_RESAMPLES  # noqa: E402
from swingbot.core.backtesting.backtest import run_backtest  # noqa: E402
from swingbot.core.market import earnings_context  # noqa: E402
from swingbot.core.market.entry_filters import DEFAULT_PARAMS, entries_for, gate_override  # noqa: E402
from swingbot.core.market.strategy_types import HORIZONS, SHORT_STRATEGIES, STRATEGY_GATES  # noqa: E402

# --- pre-registered constants (spec §5.1) ---
TRAIN = ("2010-01-01", "2025-12-31")
HOLDOUT_START = "2026-01-01"
HOLDOUT_END: str | None = None     # frozen ONCE by V104-15 and committed before any Stage 3 run
THIN_REOPEN = "2026-12-31"         # spec §5.4
FOLD_YEARS = tuple(range(2013, 2026))
ALL_HZ = tuple(HORIZONS)
RESULTS = ROOT / "docs" / "superpowers" / "results"

PART_A = (
    ("Fibonacci", "bullish"), ("RSI", "bullish"), ("MA Ribbon", "bullish"), ("VWAP", "bullish"),
    ("Support/Resistance", "bullish"), ("MACD", "bullish"), ("Volume Profile", "bullish"),
    ("Break & Retest", "bullish"), ("Break & Retest", "bearish"),
    ("EMA Crossover", "bullish"), ("EMA Crossover", "bearish"),
    ("RSI Divergence", "bullish"), ("RSI Divergence", "bearish"),
    ("Elliott Wave", "bullish"), ("Elliott Wave", "bearish"),
)
BULL_TRAP, VOL_BREAKDOWN, GAP_DRIFT = SHORT_STRATEGIES
MECHANISMS = {
    "B1": SimpleNamespace(strategy=BULL_TRAP, knob="k", grid=(1, 2, 3), loosest=3,
                          earnings=("hold", "exit_before")),
    "B2": SimpleNamespace(strategy=VOL_BREAKDOWN, knob="m", grid=(1.0, 1.2, 1.4), loosest=1.0,
                          earnings=("hold", "exit_before")),
    "B3": SimpleNamespace(strategy=GAP_DRIFT, knob="g", grid=(0.05, 0.08, 0.12), loosest=0.05,
                          earnings=("hold",)),
}


# --- small helpers ------------------------------------------------------------

def slug(text: str) -> str:
    return text.lower().replace(" & ", "-and-").replace("/", "-").replace(" ", "-")


def admitted_directions(strategy: str) -> tuple:
    directions = (STRATEGY_GATES.get(strategy) or {}).get("directions")
    return tuple(directions) if directions is not None else ("bullish", "bearish")


def admitted_horizons(strategy: str, direction: str) -> tuple:
    gates = STRATEGY_GATES.get(strategy) or {}
    by_direction = gates.get("horizons_by_direction") or {}
    horizons = by_direction.get(direction, gates.get("horizons"))
    return tuple(horizons) if horizons else ALL_HZ


@contextlib.contextmanager
def scope(raw: str):
    saved = getattr(config, "STRUCTURAL_STOP_SCOPE", "")
    config.STRUCTURAL_STOP_SCOPE = raw
    try:
        yield
    finally:
        config.STRUCTURAL_STOP_SCOPE = saved


@contextlib.contextmanager
def params(strategy: str, values: dict):
    current = DEFAULT_PARAMS[strategy]
    saved = dict(current)
    current.update(values)
    try:
        yield
    finally:
        current.clear()
        current.update(saved)


def cell_values(spec, value, earnings) -> dict:
    values = {spec.knob: value}
    if spec.strategy != GAP_DRIFT:
        values["earnings"] = earnings
    return values


def b_key(value, earnings) -> str:
    return f"{cell_key(value)}|{earnings}"


def _row(ticker, horizon_key, trade) -> dict:
    return {"ticker": ticker, "horizon_key": horizon_key, "direction": trade.direction,
            "entry_date": trade.entry_date, "outcome": trade.outcome, "r_multiple": trade.r_multiple,
            "risk_pct": round(abs(trade.entry - trade.stop_loss) / trade.entry * 100, 4)}


def trade_rows(strategy, frames, asof_map, direction, window, horizons, *,
               progress=None, label="", run_fn=None) -> list:
    """Every decided trade of `strategy` x `direction` inside `window`, v2 exits,
    scale-out, TP2 levels, frictions on -- the live arithmetic. Bearish
    populations pass the live laggard rule (backtest == live)."""
    run_fn = run_fn or run_backtest
    raw = []
    for ticker, frame in sorted(frames.items()):
        if progress is not None:
            progress.tick(f"{label} {ticker}")
        for horizon in horizons:
            summary = run_fn(ticker, frame, strategy, horizon, one_at_a_time=True, exit_model="v2",
                             scale_out=True, tp2_mode="levels", frictions=True, asof=asof_map.get(ticker))
            raw.extend({"ticker": ticker, "horizon_key": horizon, "trade": trade}
                       for trade in window_trades(summary, *window) if trade.direction == direction)
    if direction == "bearish":
        raw = apply_laggard_rule(raw)
    return [_row(item["ticker"], item["horizon_key"], item["trade"]) for item in raw]


def _frames(args):
    require_ext_cache()
    frames = _load_frames(args.universe, args.tickers)
    frames = {ticker: earnings_context.attach(frame, ticker) for ticker, frame in frames.items()}
    return frames, _build_asof_map(list(frames), frames, args.universe)


# --- Part A -------------------------------------------------------------------

def part_a_arms(strategy, direction, frames, asof_map, window, progress=None):
    horizons = admitted_horizons(strategy, direction)
    arms = {}
    for arm, raw in (("out", ""), ("in", f"{strategy}:{direction}")):
        with scope(raw):
            arms[arm] = trade_rows(strategy, frames, asof_map, direction, window, horizons,
                                   progress=progress, label=f"A {strategy} {direction} {arm}")
    return arms, horizons


def evaluate_a(strategy, direction, arms, *, n_resamples=BOOTSTRAP_RESAMPLES, seed=BOOTSTRAP_SEED):
    baseline = funnel.pooled(arms["out"])
    scored = funnel.score_cell(arms["in"], MIN_N_TRAIN, n_resamples=n_resamples, seed=seed)
    in_exp, out_exp = scored["stats"]["expectancy_r"], baseline["expectancy_r"]
    beats = in_exp is not None and out_exp is not None and in_exp > out_exp
    folds = funnel.fixed_folds(arms["in"], FOLD_YEARS)
    stage2 = funnel.fold_verdict(folds)
    proceed = scored["tier"] is not None and beats and stage2["clears"]
    return {"part": "A", "strategy": strategy, "direction": direction, "baseline": baseline,
            "in_scope": scored, "beats_baseline": beats, "folds": folds, "stage2": stage2,
            "proceed_to_holdout": proceed, "tier": scored["tier"] if proceed else None}


# --- Part B -------------------------------------------------------------------

def _count(strategy, frames) -> dict:
    by_year, by_horizon = collections.Counter(), collections.Counter()
    for frame in frames.values():
        for horizon in ALL_HZ:
            _, bearish = entries_for(strategy, frame, horizon)
            dates = frame.index[bearish.to_numpy(dtype=bool)].strftime("%Y-%m-%d")
            years = [date[:4] for date in dates if TRAIN[0] <= date <= TRAIN[1]]
            by_year.update(years)
            by_horizon[horizon] += len(years)
    return {"total": sum(by_year.values()), "by_year": dict(sorted(by_year.items())),
            "by_horizon": {horizon: by_horizon[horizon] for horizon in ALL_HZ}}


def count_b(mech, frames) -> dict:
    spec, counts = MECHANISMS[mech], {}
    with gate_override(spec.strategy, {"directions": ("bearish",)}):
        for earnings in spec.earnings:
            for value in spec.grid:
                with params(spec.strategy, cell_values(spec, value, earnings)):
                    counts[b_key(value, earnings)] = _count(spec.strategy, frames)
    return counts


def stage0_closures(mech, counts) -> list:
    spec = MECHANISMS[mech]
    return [e for e in spec.earnings if counts[b_key(spec.loosest, e)]["total"] < MIN_N_TRAIN]


def collect_b(mech, frames, asof_map, window, earnings_settings, *, values=None, progress=None) -> dict:
    spec, rows = MECHANISMS[mech], {}
    with gate_override(spec.strategy, {"directions": ("bearish",)}):
        for earnings in earnings_settings:
            for value in (values or spec.grid):
                with params(spec.strategy, cell_values(spec, value, earnings)):
                    rows[b_key(value, earnings)] = trade_rows(
                        spec.strategy, frames, asof_map, "bearish", window, ALL_HZ,
                        progress=progress, label=f"{mech} {b_key(value, earnings)}")
    return rows


def _earnings_result(spec, rows_by_cell, earnings, n_resamples, seed):
    by_value = {cell_key(v): rows_by_cell[b_key(v, earnings)] for v in spec.grid}
    stage1 = funnel.stage1(by_value, "bearish", spec.grid, n_resamples=n_resamples, seed=seed)
    stage2 = funnel.stage2(by_value, "bearish", spec.grid, fold_years=FOLD_YEARS)
    proceed = stage1["winner"] is not None and stage2["verdict"]["clears"]
    return {"stage1": stage1, "stage2": stage2, "proceed": proceed}


def evaluate_b(mech, rows_by_cell, closed=(), *, n_resamples=BOOTSTRAP_RESAMPLES, seed=BOOTSTRAP_SEED):
    """Per earnings setting: Stage 1 plateau + Stage 2 folds. Across settings the
    proceeding winner with the better tier, then the higher ExpR, is the cell."""
    spec, per_setting, best = MECHANISMS[mech], {}, None
    for earnings in spec.earnings:
        if earnings in closed:
            per_setting[earnings] = {"closed_at": "stage0"}
            continue
        result = _earnings_result(spec, rows_by_cell, earnings, n_resamples, seed)
        per_setting[earnings] = result
        if not result["proceed"]:
            continue
        winner = result["stage1"]["winner"]
        exp = result["stage1"]["cells"][cell_key(winner)]["stats"]["expectancy_r"]
        rank = (result["stage1"]["winner_tier"], -exp)
        if best is None or rank < best[0]:
            best = (rank, {"value": winner, "earnings": earnings, "tier": result["stage1"]["winner_tier"]})
    cell = best[1] if best else None
    return {"part": "B", "mechanism": mech, "strategy": spec.strategy, "direction": "bearish",
            "by_earnings": per_setting, "proceed_to_holdout": cell is not None,
            "validation_cell": cell, "tier": cell["tier"] if cell else None}


# --- Stage 3: holdout -----------------------------------------------------------

def holdout_window() -> tuple:
    if HOLDOUT_END is None:
        raise SystemExit("HOLDOUT_END is not frozen -- V104-15 sets and commits it before any Stage 3 run")
    return HOLDOUT_START, HOLDOUT_END


def candidate_slug(evaluated: dict) -> str:
    if evaluated["part"] == "A":
        return f"a-{slug(evaluated['strategy'])}-{evaluated['direction']}"
    return f"b-{evaluated['mechanism'].lower()}"


def check_shot_allowed(candidate: str, out_path) -> None:
    """One shot per candidate under ANY date; a single sealed-thin shot may be
    retried once, and only when the holdout reaches 12 months (spec §5.4)."""
    if Path(out_path).exists():
        raise SystemExit(f"holdout output already exists: {out_path}")
    prior = sorted(Path(RESULTS).glob(f"*-v104-holdout-{candidate}.json"))
    if not prior:
        return
    statuses = [json.loads(path.read_text(encoding="utf-8")).get("status") for path in prior]
    if statuses != ["sealed-thin"]:
        raise SystemExit(f"holdout shot for {candidate} is spent ({prior[-1].name})")
    if (HOLDOUT_END or "") < THIN_REOPEN:
        raise SystemExit(f"{candidate} is sealed-thin; its one retry waits for HOLDOUT_END >= {THIN_REOPEN}")


def verdict(rows_in, rows_out, tier, *, n_resamples=BOOTSTRAP_RESAMPLES, seed=BOOTSTRAP_SEED) -> dict:
    """Stage 3: N < 15 writes N only (sealed-thin, shot unspent); otherwise the
    assigned tier's clauses, plus beats_baseline for Part A."""
    n = funnel.pooled(rows_in)["n"]
    if n < MIN_N_VALIDATION:
        return {"status": "sealed-thin", "n": n}
    scored = funnel.score_cell(rows_in, MIN_N_VALIDATION, n_resamples=n_resamples, seed=seed)
    clauses = dict(scored["tier1" if tier == 1 else "tier2"]["clauses"])
    baseline = None
    if rows_out is not None:
        baseline = funnel.pooled(rows_out)
        in_exp, out_exp = scored["stats"]["expectancy_r"], baseline["expectancy_r"]
        clauses["beats_baseline"] = out_exp is None or (in_exp is not None and in_exp >= out_exp)
    return {"status": "scored", "tier": tier, "stats": scored["stats"], "lower_bound": scored["lower_bound"],
            "baseline": baseline, "clauses": clauses, "passes": all(clauses.values())}


def _holdout_rows(evaluated, frames, asof_map, window):
    if evaluated["part"] == "A":
        arms, _ = part_a_arms(evaluated["strategy"], evaluated["direction"], frames, asof_map, window)
        return arms["in"], arms["out"]
    cell = evaluated["validation_cell"]
    rows = collect_b(evaluated["mechanism"], frames, asof_map, window, (cell["earnings"],), values=(cell["value"],))
    return rows[b_key(cell["value"], cell["earnings"])], None


# --- commands -------------------------------------------------------------------

def _cmd_count(args):
    frames, _ = _frames(args)
    counts = count_b(args.mechanism, frames)
    _write(args.out, {"mechanism": args.mechanism, "universe_n": len(frames), "counts": counts,
                      "closed_at_stage0": stage0_closures(args.mechanism, counts)})


def _cmd_collect_a(args):
    if (args.strategy, args.direction) not in PART_A:
        raise SystemExit(f"{args.strategy}:{args.direction} is not a pre-registered Part A cell")
    frames, asof_map = _frames(args)
    progress = Progress(2 * len(frames))
    arms, horizons = part_a_arms(args.strategy, args.direction, frames, asof_map, TRAIN, progress)
    for rows in arms.values():
        funnel.assert_rows_before(rows, TRAIN[1])
    _write(args.out, {"part": "A", "strategy": args.strategy, "direction": args.direction,
                      "horizons": list(horizons), "window": list(TRAIN), "universe_n": len(frames), "arms": arms})


def _cmd_collect_b(args):
    closed = json.loads(Path(args.stage0).read_text(encoding="utf-8"))["closed_at_stage0"]
    spec = MECHANISMS[args.mechanism]
    open_settings = tuple(e for e in spec.earnings if e not in closed)
    if not open_settings:
        raise SystemExit(f"{args.mechanism}: every earnings setting closed at Stage 0")
    frames, asof_map = _frames(args)
    progress = Progress(len(open_settings) * len(spec.grid) * len(frames))
    rows = collect_b(args.mechanism, frames, asof_map, TRAIN, open_settings, progress=progress)
    for cell_rows in rows.values():
        funnel.assert_rows_before(cell_rows, TRAIN[1])
    _write(args.out, {"part": "B", "mechanism": args.mechanism, "window": list(TRAIN),
                      "universe_n": len(frames), "closed_at_stage0": closed, "rows_by_cell": rows})


def _cmd_evaluate(args):
    collected = json.loads(Path(args.rows).read_text(encoding="utf-8"))
    if collected["part"] == "A":
        result = evaluate_a(collected["strategy"], collected["direction"], collected["arms"])
    else:
        result = evaluate_b(collected["mechanism"], collected["rows_by_cell"],
                            closed=tuple(collected["closed_at_stage0"]))
    _write(args.out, result)


def _cmd_holdout(args):
    window = holdout_window()
    require_committed(args.preregistration)
    require_committed(args.evaluate)
    evaluated = json.loads(Path(args.evaluate).read_text(encoding="utf-8"))
    if not evaluated.get("proceed_to_holdout"):
        raise SystemExit(f"{candidate_slug(evaluated)} did not proceed to the holdout")
    candidate = candidate_slug(evaluated)
    check_shot_allowed(candidate, args.out)
    frames, asof_map = _frames(args)
    rows_in, rows_out = _holdout_rows(evaluated, frames, asof_map, window)
    result = verdict(rows_in, rows_out, evaluated["tier"])
    payload = {"candidate": candidate, "part": evaluated["part"], "strategy": evaluated["strategy"],
               "direction": evaluated["direction"], "window": list(window), "evaluate": str(args.evaluate),
               "preregistration": str(args.preregistration), **result}
    if result["status"] == "scored":
        payload["rows"] = rows_in
    _write(args.out, payload)


def _validate_emit(payloads) -> str:
    """Raise unless every payload scored and passed, shares one strategy, and
    together cover exactly the strategy's admitted directions."""
    if not all(p.get("status") == "scored" and p.get("passes") for p in payloads):
        raise SystemExit("refusing to emit a failing or sealed holdout")
    strategies = {p["strategy"] for p in payloads}
    if len(strategies) != 1:
        raise SystemExit("one strategy per registry row")
    strategy = strategies.pop()
    directions = {p["direction"] for p in payloads}
    required = set(admitted_directions(strategy))
    if directions != required:
        raise SystemExit(f"{strategy}: a registry row needs every admitted direction {sorted(required)}, "
                         f"have {sorted(directions)} (plan index amendment 2)")
    return strategy


def _registry_row(strategy, payloads, run_date) -> dict:
    rows = [row for p in payloads for row in p["rows"]]
    stats = funnel.pooled(rows)
    badge = funnel.badge_verdict(stats, MIN_N_VALIDATION)["clears"]
    status = "VALIDATED" if {p["tier"] for p in payloads} == {1} and badge else "WEAK"
    return {"source": "strategy", "strategy": strategy, "horizon": None, "status": status, "n": stats["n"],
            "win_rate": None if stats["win_rate"] is None else round(stats["win_rate"], 1),
            "expectancy_r": None if stats["expectancy_r"] is None else round(stats["expectancy_r"], 3),
            "window": f"{HOLDOUT_START}..{payloads[0]['window'][1]}", "run_date": run_date}


def _cmd_emit(args):
    payloads = [json.loads(Path(path).read_text(encoding="utf-8")) for path in args.holdout_json]
    strategy = _validate_emit(payloads)
    merge_registry(args.registry, [_registry_row(strategy, payloads, args.run_date)])


def _parser():
    parser = argparse.ArgumentParser(description="v104 structural stops and shorts funnel")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("count", "collect-a", "collect-b", "holdout"):
        command = sub.add_parser(name)
        command.add_argument("--out", required=True)
        command.add_argument("--universe")
        command.add_argument("--tickers", help="comma-separated; the pre-registered universe list")
    for name in ("count", "collect-b"):
        sub.choices[name].add_argument("--mechanism", required=True, choices=tuple(MECHANISMS))
    sub.choices["collect-b"].add_argument("--stage0", required=True)
    sub.choices["collect-a"].add_argument("--strategy", required=True)
    sub.choices["collect-a"].add_argument("--direction", required=True, choices=("bullish", "bearish"))
    sub.choices["holdout"].add_argument("--evaluate", required=True)
    sub.choices["holdout"].add_argument("--preregistration", required=True)
    evaluate_parser = sub.add_parser("evaluate")
    evaluate_parser.add_argument("--rows", required=True)
    evaluate_parser.add_argument("--out", required=True)
    emit = sub.add_parser("emit-registry")
    emit.add_argument("--holdout-json", nargs="+", required=True)
    emit.add_argument("--registry", required=True)
    emit.add_argument("--run-date", required=True)
    return parser


COMMANDS = {"count": _cmd_count, "collect-a": _cmd_collect_a, "collect-b": _cmd_collect_b,
            "evaluate": _cmd_evaluate, "holdout": _cmd_holdout, "emit-registry": _cmd_emit}


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    COMMANDS[args.cmd](args)
    print(f"v104 {args.cmd} done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
