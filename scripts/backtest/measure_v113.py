#!/usr/bin/env python3
"""v113 measurement: Part A (Downtrend Overbought Fade on 1w, grid m), Part B
(the 22 legacy strategy x direction cells on 1w, Tier 1 + bootstrap lower
bound) and Part D (every live bullish mask on SH/PSQ/RWM/DOG, one pooled cell).

Stages (spec §6): collect -> evaluate (Stages 1-2 on TRAIN) -> holdout (Stage 3,
one shot per cell, thin-holdout rule) -> emit-registry. Reads the EXTENDED
cache only:
  BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/backtest/measure_v113.py <command> ...
"""
from __future__ import annotations

import argparse
import collections
import contextlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(Path(__file__).resolve().parent)]

import funnel  # noqa: E402
from funnel import BOOTSTRAP_SEED, MIN_N_TRAIN, MIN_N_VALIDATION, cell_key  # noqa: E402
from measure_fib_confluence import Progress, _write  # noqa: E402
from measure_fib_v103 import require_committed  # noqa: E402
from measure_v104 import (FOLD_YEARS, HOLDOUT_START, THIN_REOPEN, TRAIN, _frames,  # noqa: E402
                          params, slug, trade_rows)
from run_backtest_range import merge_registry  # noqa: E402
from swingbot.core.backtesting.acceptance import BOOTSTRAP_RESAMPLES  # noqa: E402
from swingbot.core.backtesting.backtest import ALL_STRATEGIES  # noqa: E402
from swingbot.core.market.entry_filters import gate_override  # noqa: E402
from swingbot.core.market.short_entries import FADE  # noqa: E402
from swingbot.core.market.strategy_types import LEGACY_HORIZONS, STRATEGY_GATES, admits  # noqa: E402
from swingbot.core.planning import reward_floor  # noqa: E402
from swingbot.core.planning.stop_scope import stop_ceiling  # noqa: E402

# --- pre-registered constants (spec §1, §3-§6) ---
HOLDOUT_END: str | None = "2026-09-25"     # spec §6; frozen by the pre-registration commit (V113-13)
HZ = "1w"
A_GRID = (1.0, 1.25, 1.5)
PART_B = tuple((strategy, direction) for strategy in ALL_STRATEGIES for direction in ("bullish", "bearish"))
D_TICKERS = ("SH", "PSQ", "RWM", "DOG")
CAP_TOLERANCE_PCT = 0.001
RESULTS = ROOT / "docs" / "superpowers" / "results"


# --- small helpers ------------------------------------------------------------

def d_cells() -> tuple:
    """Every (strategy, horizon) today's live masks admit BULLISH (spec §5),
    legacy horizons only -- run unchanged on the four inverse ETFs."""
    return tuple((strategy, horizon) for strategy in ALL_STRATEGIES for horizon in LEGACY_HORIZONS
                 if admits(strategy, "bullish", horizon))


@contextlib.contextmanager
def admit_1w(strategy: str, direction: str):
    """Admit exactly (direction, 1w) for `strategy` during the run; every other
    pair keeps its live mask (spec §2)."""
    gates = dict(STRATEGY_GATES.get(strategy) or {})
    gates["cells"] = frozenset(gates.get("cells", ())) | {(direction, HZ)}
    with gate_override(strategy, gates):
        yield


def cap_bind_rate(rows, strategy, direction):
    """Share of trades whose planned risk sits on the 1w stop ceiling (spec §4)."""
    if not rows:
        return None
    cap = stop_ceiling(strategy, direction, HZ)[0]
    return sum(1 for row in rows if row["risk_pct"] >= cap - CAP_TOLERANCE_PCT) / len(rows)


def floor_counts(strategy) -> dict:
    """The 1w reward floor's decisions for `strategy` since the last reset (spec §4)."""
    key = (strategy, HZ)
    drops, passes = reward_floor.DROPS[key], reward_floor.PASSES[key]
    total = drops + passes
    return {"floor_drops": drops, "floor_passes": passes,
            "floor_drop_rate": drops / total if total else None}


def strict_clauses(scored) -> dict:
    """Part B's bar (spec §4): every Tier 1 clause AND the bootstrap lower bound > 0."""
    return {**scored["tier1"]["clauses"], "lower_bound": scored["tier2"]["clauses"]["lower_bound"]}


def _ab_frames(args):
    """Parts A and B run on the watchlist universe, never on Part D's ETFs."""
    frames, asof_map = _frames(args)
    return {ticker: frame for ticker, frame in frames.items() if ticker not in D_TICKERS}, asof_map


def _d_frames(args):
    if sorted((args.tickers or "").split(",")) != sorted(D_TICKERS):
        raise SystemExit(f"Part D runs on exactly --tickers {','.join(D_TICKERS)}")
    return _frames(args)


# --- collectors -----------------------------------------------------------------

def collect_a(frames, asof_map, window, *, values=A_GRID, progress=None, run_fn=None) -> dict:
    out = {"rows_by_cell": {}, "floor": {}}
    with admit_1w(FADE, "bearish"):
        for value in values:
            reward_floor.reset()
            with params(FADE, {"m": value}):
                out["rows_by_cell"][cell_key(value)] = trade_rows(
                    FADE, frames, asof_map, "bearish", window, (HZ,),
                    progress=progress, label=f"A m={cell_key(value)}", run_fn=run_fn)
            out["floor"][cell_key(value)] = floor_counts(FADE)
    return out


def collect_b(strategy, direction, frames, asof_map, window, *, progress=None, run_fn=None) -> dict:
    reward_floor.reset()
    with admit_1w(strategy, direction):
        rows = trade_rows(strategy, frames, asof_map, direction, window, (HZ,),
                          progress=progress, label=f"B {strategy} {direction}", run_fn=run_fn)
    return {"rows": rows, "floor": floor_counts(strategy)}


def collect_d(frames, asof_map, window, *, progress=None, run_fn=None) -> list:
    rows = []
    for strategy, horizon in d_cells():
        rows.extend({**row, "strategy": strategy} for row in trade_rows(
            strategy, frames, asof_map, "bullish", window, (horizon,),
            progress=progress, label=f"D {strategy} {horizon}", run_fn=run_fn))
    return rows


# --- evaluators (Stages 1-2 on TRAIN) --------------------------------------------

def evaluate_a(collected, *, n_resamples=BOOTSTRAP_RESAMPLES, seed=BOOTSTRAP_SEED) -> dict:
    """Stage 1: standard tiers per m, plateau winner (funnel.stage1). Stage 2:
    per-fold reselection over the grid (funnel.stage2)."""
    rows_by_cell = collected["rows_by_cell"]
    stage1 = funnel.stage1(rows_by_cell, "bearish", A_GRID, n_resamples=n_resamples, seed=seed)
    stage2 = funnel.stage2(rows_by_cell, "bearish", A_GRID, fold_years=FOLD_YEARS)
    proceed = stage1["winner"] is not None and stage2["verdict"]["clears"]
    return {"part": "A", "strategy": FADE, "direction": "bearish", "horizon": HZ,
            "stage1": stage1, "stage2": stage2, "floor": collected["floor"],
            "cap_bind": {key: cap_bind_rate(rows, FADE, "bearish") for key, rows in rows_by_cell.items()},
            "proceed_to_holdout": proceed,
            "validation_cell": {"value": stage1["winner"]} if proceed else None,
            "tier": stage1["winner_tier"] if proceed else None}


def evaluate_b(strategy, direction, collected, *, n_resamples=BOOTSTRAP_RESAMPLES,
               seed=BOOTSTRAP_SEED) -> dict:
    """Stage 1: the single cell must clear strict_clauses. Stage 2: fixed folds."""
    rows = collected["rows"]
    scored = funnel.score_cell(rows, MIN_N_TRAIN, n_resamples=n_resamples, seed=seed)
    clauses = strict_clauses(scored)
    folds = funnel.fixed_folds(rows, FOLD_YEARS)
    stage2 = funnel.fold_verdict(folds)
    proceed = all(clauses.values()) and stage2["clears"]
    return {"part": "B", "strategy": strategy, "direction": direction, "horizon": HZ,
            "scored": scored, "clauses": clauses, "folds": folds, "stage2": stage2,
            "floor": collected["floor"], "cap_bind_rate": cap_bind_rate(rows, strategy, direction),
            "proceed_to_holdout": proceed, "tier": 1 if proceed else None}


def _breakdown(rows, key) -> dict:
    groups = collections.defaultdict(list)
    for row in rows:
        groups[row[key]].append(row)
    return {name: funnel.pooled(group) for name, group in sorted(groups.items())}


def evaluate_d(rows, *, n_resamples=BOOTSTRAP_RESAMPLES, seed=BOOTSTRAP_SEED) -> dict:
    """One pooled cell, standard tiers; breakdowns are reported, never used to select."""
    scored = funnel.score_cell(rows, MIN_N_TRAIN, n_resamples=n_resamples, seed=seed)
    folds = funnel.fixed_folds(rows, FOLD_YEARS)
    stage2 = funnel.fold_verdict(folds)
    proceed = scored["tier"] is not None and stage2["clears"]
    return {"part": "D", "strategy": "inverse-etf-longs", "direction": "bullish", "horizon": None,
            "cells": [list(cell) for cell in d_cells()], "scored": scored, "folds": folds,
            "stage2": stage2, "by_strategy": _breakdown(rows, "strategy"),
            "by_ticker": _breakdown(rows, "ticker"),
            "proceed_to_holdout": proceed, "tier": scored["tier"] if proceed else None}


EVALUATORS = {
    "A": lambda collected: evaluate_a(collected),
    "B": lambda collected: evaluate_b(collected["strategy"], collected["direction"], collected),
    "D": lambda collected: evaluate_d(collected["rows"]),
}


# --- Stage 3: holdout -------------------------------------------------------------

def holdout_window() -> tuple:
    if HOLDOUT_END is None:
        raise SystemExit("HOLDOUT_END is not frozen -- the pre-registration commit freezes it")
    return HOLDOUT_START, HOLDOUT_END


_SLUGS = {
    "A": lambda evaluated: "a-fade",
    "B": lambda evaluated: f"b-{slug(evaluated['strategy'])}-{evaluated['direction']}",
    "D": lambda evaluated: "d-inverse-etfs",
}


def candidate_slug(evaluated: dict) -> str:
    return _SLUGS[evaluated["part"]](evaluated)


def check_shot_allowed(candidate: str, out_path) -> None:
    """One shot per cell under ANY date; a single sealed-thin shot may be
    retried once, and only when the holdout reaches 12 months."""
    if Path(out_path).exists():
        raise SystemExit(f"holdout output already exists: {out_path}")
    prior = sorted(Path(RESULTS).glob(f"*-v113-holdout-{candidate}.json"))
    if not prior:
        return
    statuses = [json.loads(path.read_text(encoding="utf-8")).get("status") for path in prior]
    if statuses != ["sealed-thin"]:
        raise SystemExit(f"holdout shot for {candidate} is spent ({prior[-1].name})")
    if (HOLDOUT_END or "") < THIN_REOPEN:
        raise SystemExit(f"{candidate} is sealed-thin; its one retry waits for HOLDOUT_END >= {THIN_REOPEN}")


def _check_out_path(candidate: str, out_path) -> None:
    """The one-shot ledger is the results directory: --out must land there under the candidate's name."""
    out = Path(out_path)
    if out.parent != Path(RESULTS) or not out.match(f"*-v113-holdout-{candidate}.json"):
        raise SystemExit(f"--out must be {RESULTS}/<date>-v113-holdout-{candidate}.json so the one-shot rule sees it")


def holdout_clauses(scored, part, tier) -> dict:
    """Part B keeps its strict bar on the holdout; A and D use their assigned tier."""
    if part == "B":
        return strict_clauses(scored)
    return dict(scored["tier1" if tier == 1 else "tier2"]["clauses"])


def verdict(rows, part, tier, *, n_resamples=BOOTSTRAP_RESAMPLES, seed=BOOTSTRAP_SEED) -> dict:
    """N < 15 writes N only (sealed-thin, shot unspent); otherwise the cell's clauses."""
    n = funnel.pooled(rows)["n"]
    if n < MIN_N_VALIDATION:
        return {"status": "sealed-thin", "n": n}
    scored = funnel.score_cell(rows, MIN_N_VALIDATION, n_resamples=n_resamples, seed=seed)
    clauses = holdout_clauses(scored, part, tier)
    return {"status": "scored", "tier": tier, "stats": scored["stats"], "lower_bound": scored["lower_bound"],
            "clauses": clauses, "passes": all(clauses.values())}


def holdout_rows(evaluated, frames, asof_map, window) -> list:
    part = evaluated["part"]
    if part == "A":
        value = evaluated["validation_cell"]["value"]
        return collect_a(frames, asof_map, window, values=(value,))["rows_by_cell"][cell_key(value)]
    if part == "B":
        return collect_b(evaluated["strategy"], evaluated["direction"], frames, asof_map, window)["rows"]
    return collect_d(frames, asof_map, window)


# --- registry ---------------------------------------------------------------------

def _validate_emit(payloads) -> str:
    """Raise unless every payload scored and passed, none is Part D (amendment 5),
    they share one strategy, and their directions are exactly that strategy's
    shipped 1w cells (a row ships only when every admitted direction passed)."""
    if not all(p.get("status") == "scored" and p.get("passes") for p in payloads):
        raise SystemExit("refusing to emit a failing or sealed holdout")
    if any(p["part"] == "D" for p in payloads):
        raise SystemExit("Part D pools strategies on four tickers -- it writes no registry row")
    strategies = {p["strategy"] for p in payloads}
    if len(strategies) != 1:
        raise SystemExit("one strategy per registry row")
    strategy = strategies.pop()
    shipped = {d for d, hk in (STRATEGY_GATES.get(strategy) or {}).get("cells", ()) if hk == HZ}
    if {p["direction"] for p in payloads} != shipped:
        raise SystemExit(f"{strategy}: a 1w row needs exactly its shipped 1w cells {sorted(shipped)}")
    return strategy


def _registry_row(strategy, payloads, run_date) -> dict:
    rows = [row for p in payloads for row in p["rows"]]
    stats = funnel.pooled(rows)
    badge = funnel.badge_verdict(stats, MIN_N_VALIDATION)["clears"]
    status = "VALIDATED" if {p["tier"] for p in payloads} == {1} and badge else "WEAK"
    return {"source": "strategy", "strategy": strategy, "horizon": HZ, "status": status, "n": stats["n"],
            "win_rate": None if stats["win_rate"] is None else round(stats["win_rate"], 1),
            "expectancy_r": None if stats["expectancy_r"] is None else round(stats["expectancy_r"], 3),
            "window": f"{HOLDOUT_START}..{payloads[0]['window'][1]}", "run_date": run_date}


# --- commands -------------------------------------------------------------------

def _cmd_collect_a(args):
    frames, asof_map = _ab_frames(args)
    collected = collect_a(frames, asof_map, TRAIN, progress=Progress(len(A_GRID) * len(frames)))
    for rows in collected["rows_by_cell"].values():
        funnel.assert_rows_before(rows, TRAIN[1])
    _write(args.out, {"part": "A", "window": list(TRAIN), "universe_n": len(frames), **collected})


def _cmd_collect_b(args):
    if (args.strategy, args.direction) not in PART_B:
        raise SystemExit(f"{args.strategy}:{args.direction} is not a pre-registered Part B cell")
    frames, asof_map = _ab_frames(args)
    collected = collect_b(args.strategy, args.direction, frames, asof_map, TRAIN,
                          progress=Progress(len(frames)))
    funnel.assert_rows_before(collected["rows"], TRAIN[1])
    _write(args.out, {"part": "B", "strategy": args.strategy, "direction": args.direction,
                      "window": list(TRAIN), "universe_n": len(frames), **collected})


def _cmd_collect_d(args):
    frames, asof_map = _d_frames(args)
    rows = collect_d(frames, asof_map, TRAIN, progress=Progress(len(d_cells()) * len(frames)))
    funnel.assert_rows_before(rows, TRAIN[1])
    _write(args.out, {"part": "D", "window": list(TRAIN), "universe_n": len(frames),
                      "tickers": sorted(frames), "cells": [list(cell) for cell in d_cells()], "rows": rows})


def _cmd_evaluate(args):
    collected = json.loads(Path(args.rows).read_text(encoding="utf-8"))
    _write(args.out, {"universe_n": collected["universe_n"], **EVALUATORS[collected["part"]](collected)})


def _cmd_holdout(args):
    window = holdout_window()
    require_committed(args.preregistration)
    require_committed(args.evaluate)
    evaluated = json.loads(Path(args.evaluate).read_text(encoding="utf-8"))
    candidate = candidate_slug(evaluated)
    if not evaluated.get("proceed_to_holdout"):
        raise SystemExit(f"{candidate} did not proceed to the holdout")
    _check_out_path(candidate, args.out)
    check_shot_allowed(candidate, args.out)
    frames, asof_map = _d_frames(args) if evaluated["part"] == "D" else _ab_frames(args)
    rows = holdout_rows(evaluated, frames, asof_map, window)
    result = verdict(rows, evaluated["part"], evaluated["tier"])
    payload = {"candidate": candidate, "part": evaluated["part"], "strategy": evaluated["strategy"],
               "direction": evaluated["direction"], "horizon": evaluated.get("horizon"),
               "window": list(window), "universe_n": len(frames), "evaluate": str(args.evaluate),
               "preregistration": str(args.preregistration), **result}
    if result["status"] == "scored":
        payload["rows"] = rows
    _write(args.out, payload)


def _cmd_emit(args):
    for path in args.holdout_json:
        require_committed(path)
    payloads = [json.loads(Path(path).read_text(encoding="utf-8")) for path in args.holdout_json]
    strategy = _validate_emit(payloads)
    for payload in payloads:
        if not payload.get("preregistration"):
            raise SystemExit("holdout JSON names no preregistration; refusing to emit")
        require_committed(payload["preregistration"])
        if tuple(payload["window"]) != holdout_window():
            raise SystemExit(f"holdout window {payload['window']} is not the frozen {list(holdout_window())}")
    merge_registry(args.registry, [_registry_row(strategy, payloads, args.run_date)])


def _parser():
    parser = argparse.ArgumentParser(description="v113 1w horizon, fade and inverse-ETF funnel")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("collect-a", "collect-b", "collect-d", "holdout"):
        command = sub.add_parser(name)
        command.add_argument("--out", required=True)
        command.add_argument("--universe")
        command.add_argument("--tickers", help="comma-separated; Part D requires exactly SH,PSQ,RWM,DOG")
    sub.choices["collect-b"].add_argument("--strategy", required=True)
    sub.choices["collect-b"].add_argument("--direction", required=True, choices=("bullish", "bearish"))
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


COMMANDS = {"collect-a": _cmd_collect_a, "collect-b": _cmd_collect_b, "collect-d": _cmd_collect_d,
            "evaluate": _cmd_evaluate, "holdout": _cmd_holdout, "emit-registry": _cmd_emit}


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    COMMANDS[args.cmd](args)
    print(f"v113 {args.cmd} done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
