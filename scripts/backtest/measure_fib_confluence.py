#!/usr/bin/env python3
"""v102: Fibonacci x Rolling S/R confluence on extended history.

Spec: docs/superpowers/specs/2026-09-24-v102-fib-sr-confluence-extended-history-design.md
Reads the EXTENDED cache only -- run with BACKTEST_CACHE_DIR=data/backtest_cache_ext.
The shared cache starts 2018-06 and would silently shrink TRAIN_EXT, so the
script refuses to run against it.

Stages (one verdict per direction):
  count       Stage 0: raw signal survivors per tolerance/direction/year (no backtest)
  collect     backtest trades for 0.0 + every GRID tolerance, TRAIN_EXT entries only
  evaluate    Stage 1 selection + Stage 2 walk-forward, pure over a collect JSON
  validation  Stage 3: ONE tolerance, one direction, VALIDATION entries only;
              requires the committed pre-registration

Run (from the repo root):
  BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/backtest/measure_fib_confluence.py count --out <json>
  BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/backtest/measure_fib_confluence.py collect --out <json>
  python scripts/backtest/measure_fib_confluence.py evaluate --rows <collect json> --out <json>
  BACKTEST_CACHE_DIR=data/backtest_cache_ext python scripts/backtest/measure_fib_confluence.py validation \\
      --tol 0.5 --direction bullish --preregistration <md> --out <json>
"""
from __future__ import annotations

import argparse
import collections
import contextlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(Path(__file__).resolve().parent)]

from measure_bearish_arms import _unmasked_gates, apply_laggard_rule  # noqa: E402
from run_backtest_range import (  # noqa: E402
    _build_asof_map, _tickers_for_run, _with_context, load_cached, merge_registry, window_trades,
)
from swingbot.core.backtesting.backtest import run_backtest  # noqa: E402
from swingbot.core.market.entry_filters import entries_for, gate_override  # noqa: E402
from swingbot.core.market.strategy_types import LEGACY_HORIZONS, STRATEGY_GATES  # noqa: E402
from swingbot.core.marketdata.universe import data_quality_issues, liquidity_reason  # noqa: E402
from funnel import FOLD_YEARS, MIN_N_TRAIN, MIN_N_VALIDATION  # noqa: E402
from funnel import badge_verdict, fold_verdict, plateau_ok, pooled  # noqa: E402
from funnel import cell_key as tol_key  # noqa: E402
from funnel import dir_rows as _dir, year_rows as _years  # noqa: E402
from funnel import fold_pick as _fold_pick_on  # noqa: E402

STRATEGY = "Fibonacci"
DIRECTIONS = ("bullish", "bearish")
ALL_HZ = tuple(LEGACY_HORIZONS)
EXT_CACHE_NAME = "backtest_cache_ext"

# --- pre-registered constants (spec "Windows and funnel") ---
TRAIN_EXT = ("2010-01-01", "2023-12-31")
VALIDATION = ("2024-01-01", "2025-12-31")
GRID = (0.25, 0.5, 0.75, 1.0)
BASELINE_TOL = 0.0


def require_ext_cache():
    from swingbot.core.marketdata import backtest_cache
    if backtest_cache.CACHE_DIR.name != EXT_CACHE_NAME:
        raise SystemExit(f"v102 reads the extended cache only: run with "
                         f"BACKTEST_CACHE_DIR=data/{EXT_CACHE_NAME} (got {backtest_cache.CACHE_DIR})")


@contextlib.contextmanager
def confluence_tol(tol):
    from swingbot import config
    previous = getattr(config, "FIB_SR_CONFLUENCE_ATR", 0.0)
    config.FIB_SR_CONFLUENCE_ATR = float(tol)
    try:
        yield
    finally:
        config.FIB_SR_CONFLUENCE_ATR = previous


class Progress:
    """Flushed `[k/N] P% label` lines -- the percent answers "how far along"."""

    def __init__(self, total):
        self.total, self.done = max(total, 1), 0

    def tick(self, label):
        self.done += 1
        print(f"[{self.done}/{self.total}] {self.done / self.total * 100:.0f}% {label}", flush=True)


def _direction_gate(direction):
    if direction == "bearish":
        return gate_override(STRATEGY, _unmasked_gates(STRATEGY))
    return contextlib.nullcontext()


def _row(ticker, horizon_key, trade):
    return {"ticker": ticker, "horizon_key": horizon_key, "direction": trade.direction,
            "entry_date": trade.entry_date, "outcome": trade.outcome, "r_multiple": trade.r_multiple}


def _direction_pass(frames, asof_map, direction, window, horizons, run_fn, progress, label):
    raw = []
    with _direction_gate(direction):
        for ticker, frame in sorted(frames.items()):
            progress.tick(f"{label} {direction} {ticker}")
            for h in horizons:
                summary = run_fn(ticker, frame, STRATEGY, h, one_at_a_time=True, exit_model="v2",
                                 scale_out=True, tp2_mode="levels", frictions=True,
                                 asof=asof_map.get(ticker))
                raw.extend({"ticker": ticker, "horizon_key": h, "trade": t}
                           for t in window_trades(summary, *window) if t.direction == direction)
    if direction == "bearish":
        raw = apply_laggard_rule(raw)
    return [_row(r["ticker"], r["horizon_key"], r["trade"]) for r in raw]


def collect_trades(frames, asof_map, tol, window, *, horizons=ALL_HZ, run_fn=None, progress=None):
    """Bullish from the LIVE gate; bearish unmasked + v93 laggard rule."""
    run_fn = run_fn or run_backtest
    progress = progress or Progress(len(frames) * len(DIRECTIONS))
    rows = []
    with confluence_tol(tol):
        for direction in DIRECTIONS:
            rows.extend(_direction_pass(frames, asof_map, direction, window, horizons, run_fn,
                                        progress, f"tol={tol_key(tol)}"))
    return rows


def _signal_years(frame, horizon, direction):
    bullish, bearish = entries_for(STRATEGY, frame, horizon)
    series = bullish if direction == "bullish" else bearish
    dates = frame.index[series.to_numpy(dtype=bool)].strftime("%Y-%m-%d")
    return [d[:4] for d in dates if TRAIN_EXT[0] <= d <= TRAIN_EXT[1]]


def count_signals(frames, tols, *, horizons=ALL_HZ):
    """Stage 0: raw signal counts -- an UPPER bound on decided trades
    (one-at-a-time, no-target drops and the bearish laggard rule only remove)."""
    out = {}
    for tol in tols:
        with confluence_tol(tol):
            for direction in DIRECTIONS:
                by_year = collections.Counter()
                with _direction_gate(direction):
                    for frame in frames.values():
                        for h in horizons:
                            by_year.update(_signal_years(frame, h, direction))
                out[f"{tol_key(tol)}|{direction}"] = dict(sorted(by_year.items()))
    return out


def _plateau_ok(cells, tol):
    return plateau_ok({value: cells[value]["verdict"]["clears"] for value in cells}, GRID, tol)


def stage1(rows_by_tol, direction):
    cells = {}
    for tol in GRID:
        stats = pooled(_dir(rows_by_tol[tol_key(tol)], direction))
        cells[tol] = {"stats": stats, "verdict": badge_verdict(stats, MIN_N_TRAIN)}
    passing = [t for t in GRID if cells[t]["verdict"]["clears"] and _plateau_ok(cells, t)]
    winner = max(passing, key=lambda t: cells[t]["stats"]["expectancy_r"]) if passing else None
    baseline = pooled(_dir(rows_by_tol[tol_key(BASELINE_TOL)], direction))
    return {"baseline": baseline, "cells": {tol_key(t): c for t, c in cells.items()},
            "plateau_passing": passing, "winner": winner}


def fold_pick(rows_by_tol, direction, year):
    """v102's grid bound onto the shared Fibonacci funnel's fold picker."""
    return _fold_pick_on(rows_by_tol, direction, year, GRID)


def stage2(rows_by_tol, direction):
    folds = []
    for year in FOLD_YEARS:
        tol = fold_pick(rows_by_tol, direction, year)
        stats = (pooled(_dir(_years(rows_by_tol[tol_key(tol)], year, year), direction))
                 if tol is not None else None)
        folds.append({"test_year": year, "tol": tol, "stats": stats})
    return {"folds": folds, "verdict": fold_verdict(folds)}


def registry_record(rows, run_date):
    stats = pooled(rows)
    status = "VALIDATED" if badge_verdict(stats, MIN_N_VALIDATION)["clears"] else "WEAK"
    return {"source": "strategy", "strategy": STRATEGY, "horizon": None, "status": status,
            "n": stats["n"],
            "win_rate": None if stats["win_rate"] is None else round(stats["win_rate"], 1),
            "expectancy_r": None if stats["expectancy_r"] is None else round(stats["expectancy_r"], 3),
            "window": f"{VALIDATION[0]}..{VALIDATION[1]}", "run_date": run_date}


def _load_frames(universe=None, tickers=None):
    names = tickers.split(",") if tickers else _tickers_for_run(universe)
    frames = {t: _with_context(load_cached(t)) for t in names}
    return {t: f for t, f in frames.items()
            if f is not None and liquidity_reason(f) is None and not data_quality_issues(f, t)}


def _write(path, payload):
    Path(path).write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")


def _cmd_count(args):
    require_ext_cache()
    frames = _load_frames(args.universe, args.tickers)
    _write(args.out, {"universe_n": len(frames),
                      "counts": count_signals(frames, (BASELINE_TOL, *GRID))})


def _cmd_collect(args):
    require_ext_cache()
    started = time.monotonic()
    frames = _load_frames(args.universe, args.tickers)
    asof_map = _build_asof_map(list(frames), frames, args.universe)
    tols = (BASELINE_TOL, *GRID)
    progress = Progress(len(tols) * len(frames) * len(DIRECTIONS))
    rows_by_tol = {tol_key(t): collect_trades(frames, asof_map, t, TRAIN_EXT, progress=progress)
                   for t in tols}
    _write(args.out, {"window": TRAIN_EXT, "universe_n": len(frames), "rows_by_tol": rows_by_tol,
                      "elapsed_s": round(time.monotonic() - started, 1)})


def _cmd_evaluate(args):
    rows_by_tol = json.loads(Path(args.rows).read_text(encoding="utf-8"))["rows_by_tol"]
    out = {}
    for direction in DIRECTIONS:
        s1 = stage1(rows_by_tol, direction)
        s2 = stage2(rows_by_tol, direction)
        proceed = s1["winner"] is not None and s2["verdict"]["clears"]
        out[direction] = {"stage1": s1, "stage2": s2, "proceed_to_validation": proceed,
                          "validation_tol": s1["winner"] if proceed else None}
    _write(args.out, out)


def _cmd_validation(args):
    prereg = Path(args.preregistration)
    if not prereg.is_file():
        raise SystemExit(f"VALIDATION needs the committed pre-registration; not found: {prereg}")
    if float(args.tol) not in GRID:
        raise SystemExit(f"--tol must be a GRID value {GRID}, got {args.tol}")
    require_ext_cache()
    frames = _load_frames(args.universe, args.tickers)
    asof_map = _build_asof_map(list(frames), frames, args.universe)
    rows = _dir(collect_trades(frames, asof_map, float(args.tol), VALIDATION), args.direction)
    stats = pooled(rows)
    _write(args.out, {"direction": args.direction, "tol": float(args.tol),
                      "preregistration": str(prereg), "stats": stats,
                      "verdict": badge_verdict(stats, MIN_N_VALIDATION), "rows": rows})


def _cmd_emit(args):
    rows = []
    for path in args.validation_json:
        rows.extend(json.loads(Path(path).read_text(encoding="utf-8"))["rows"])
    merge_registry(args.registry, [registry_record(rows, args.run_date)])


def _parser():
    ap = argparse.ArgumentParser(description="v102 Fibonacci x Rolling S/R confluence funnel")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("count", "collect", "validation"):
        p = sub.add_parser(name)
        p.add_argument("--out", required=True)
        p.add_argument("--universe")
        p.add_argument("--tickers", help="comma-separated subset, smoke runs only")
    sub.choices["validation"].add_argument("--tol", required=True)
    sub.choices["validation"].add_argument("--direction", required=True, choices=DIRECTIONS)
    sub.choices["validation"].add_argument("--preregistration", required=True)
    ev = sub.add_parser("evaluate")
    ev.add_argument("--rows", required=True)
    ev.add_argument("--out", required=True)
    em = sub.add_parser("emit-registry")
    em.add_argument("--validation-json", nargs="+", required=True)
    em.add_argument("--registry", required=True)
    em.add_argument("--run-date", required=True)
    return ap


COMMANDS = {"count": _cmd_count, "collect": _cmd_collect, "evaluate": _cmd_evaluate,
            "validation": _cmd_validation, "emit-registry": _cmd_emit}


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    COMMANDS[args.cmd](args)
    print(f"v102 {args.cmd} done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
