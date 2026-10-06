#!/usr/bin/env python3
"""v127: replay and score the pre-registered structure-break armed-entry grid.

Read docs/superpowers/specs/2026-10-02-v127-structure-break-armed-entries-design.md
§4 first. The walk lives in swingbot/core/backtesting/structure_arm.py, the
arithmetic in structure_measurement.py; this script only replays frames and
moves rows to and from disk. Stage verdicts come from
scripts/backtest/validate_component.py (with --bespoke-instrument), fed by `arms`.

    replay   --run run1 | run2     sharded per ticker, resumable; run2 refused
                                   without a Stage 2 doc reading **Overall: PASS**
    summary  --out-md PATH         run1 row counts + arm funnel, selection window only
    select   (Stage 1, selection window only)
    arms     --stage mde | walkforward | validation --cell CELL_ID --out PATH
    permute  --cell CELL_ID        the random-delay null over run2

Long runs: dispatch to the backtest-runner subagent. Progress is flushed to
stdout and to <out-root>/<run>/progress.txt as "done/total tickers (pct%)";
the file is deleted when the command finishes.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from measure_armed_entries import (  # noqa: E402  (sibling script, same dir)
    STAGE2_PASS_MARKER, _map, _trade, load_frame, read_rows, write_shard,
)
from swingbot.core.backtesting import structure_measurement as sm  # noqa: E402
from swingbot.core.backtesting.acceptance import ArmTrade  # noqa: E402
from swingbot.core.market.strategy_types import LEGACY_HORIZONS  # noqa: E402

CACHE_DIR = ROOT / "data" / "backtest_cache"
OUT_ROOT = ROOT / "data" / "v127"
RUNS = {"run1": sm.RUN1_WINDOW, "run2": sm.VALIDATION_WINDOW}
BESPOKE_REASON = ("structure_arm: v127 armed structure-break replay "
                  "(measure_arms.py has no armed-entry engine)")


def _in(window, date) -> bool:
    return window[0] <= date <= window[1]


def _horizon_rows(ticker, frame, horizon, window):
    """(rows, counts, arm records) for one horizon, rows/arms in window."""
    from swingbot.core.backtesting.armed_replay import arm_candidates
    from swingbot.core.backtesting.backtest_scenarios import replay_scenarios
    from swingbot.core.backtesting.structure_arm import replay_structure
    rows, counts, arms = [], {}, []
    for index, plan in replay_scenarios(ticker, frame, horizon):
        date = str(frame.index[index].date())
        if _in(window, date):
            rows.append(sm.Row(sm.BASELINE, _trade(frame, index, plan, date)))
    cache: dict = {}
    candidates = arm_candidates(ticker, frame, horizon, level_cache=cache)
    results = replay_structure(ticker, frame, horizon, sm.CELLS, candidates=candidates,
                               level_cache=cache)
    for cell_id, result in results.items():
        counts[f"{horizon}|{cell_id}"] = dict(result.counts)
        for j, plan, trigger in result.issued:
            date = str(frame.index[j].date())
            if _in(window, date):
                rows.append(sm.Row(cell_id, _trade(frame, j, plan, date), trigger))
        for arm_index, _end, status in result.arms:
            date = str(frame.index[arm_index].date())
            if _in(window, date):
                arms.append({"cell": cell_id, "horizon": horizon, "arm_date": date,
                             "status": status})
    return rows, counts, arms


def ticker_rows(ticker, frame, window, horizons):
    rows, counts, arms = [], {}, []
    for horizon in horizons:
        r, c, a = _horizon_rows(ticker, frame, horizon, window)
        rows += r
        counts.update(c)
        arms += a
    return rows, counts, arms


def _replay_worker(task):
    ticker, cache_dir, window, horizons = task
    frame = load_frame(cache_dir, ticker)
    if frame is None or frame.empty:
        return ticker, [], {}, []
    rows, counts, arms = ticker_rows(ticker, frame, window, horizons)
    return ticker, [row.to_dict() for row in rows], counts, arms


def read_arms(run_dir) -> list:
    """Arm records live in <ticker>.arms.json -- NOT .jsonl, which
    measure_armed_entries.read_rows globs as trade rows."""
    out = []
    for shard in sorted(Path(run_dir).glob("*.arms.json")):
        out += json.loads(shard.read_text(encoding="utf-8"))
    return out


def run_meta(cache_dir, window, horizons) -> dict:
    return {"cache_files": sorted(p.name for p in Path(cache_dir).glob("*.csv")),
            "window": list(window), "horizons": list(horizons),
            "cells": [cell.cell_id for cell in sm.CELLS]}


def _run2_locked(args) -> bool:
    if args.run != "run2":
        return False
    doc = Path(args.stage2_doc) if args.stage2_doc else None
    return doc is None or not doc.exists() or STAGE2_PASS_MARKER not in doc.read_text(encoding="utf-8")


def _claim_run_dir(args, horizons):
    """The run dir, or None when an existing run.json disagrees (no resume)."""
    run_dir = Path(args.out_root) / args.run
    run_dir.mkdir(parents=True, exist_ok=True)
    meta = run_meta(Path(args.cache_dir), RUNS[args.run], horizons)
    meta_path = run_dir / "run.json"
    if meta_path.exists() and json.loads(meta_path.read_text()) != meta:
        return None
    meta_path.write_text(json.dumps(meta, indent=1))
    return run_dir


def _write_ticker(run_dir, ticker, rows, counts, arms):
    (run_dir / f"{ticker}.arms.json").write_text(json.dumps(arms), encoding="utf-8")
    (run_dir / f"{ticker}.counts.json").write_text(json.dumps(counts))
    write_shard(run_dir / f"{ticker}.jsonl", rows)       # last: its presence marks the ticker done


def cmd_replay(args) -> int:
    if _run2_locked(args):
        print("REFUSED -- run2 replays VALIDATION; it needs --stage2-doc reading "
              f"{STAGE2_PASS_MARKER}", flush=True)
        return 3
    horizons = args.horizons.split(",") if args.horizons else list(LEGACY_HORIZONS)
    run_dir = _claim_run_dir(args, horizons)
    if run_dir is None:
        print(f"REFUSED -- {args.out_root}/{args.run}/run.json was written for a different "
              "cache/window/horizons/grid", flush=True)
        return 4
    cache = Path(args.cache_dir)
    symbols = args.tickers.split(",") if args.tickers else sorted(p.stem for p in cache.glob("*.csv"))
    todo = [s for s in symbols if not (run_dir / f"{s}.jsonl").exists()]
    tasks = [(s, str(cache), RUNS[args.run], horizons) for s in todo]
    progress = run_dir / "progress.txt"
    try:
        for done, (ticker, rows, counts, arms) in enumerate(_map(_replay_worker, tasks, args.workers), 1):
            _write_ticker(run_dir, ticker, rows, counts, arms)
            pct = 100 * done // len(todo) if todo else 100
            progress.write_text(f"{done}/{len(todo)} tickers ({pct}%)\n")
            print(f"[{done}/{len(todo)}] {ticker}: {len(rows)} rows ({pct}%)", flush=True)
    finally:
        progress.unlink(missing_ok=True)
    print(f"complete: {len(read_rows(run_dir))} rows", flush=True)
    return 0


def cmd_summary(args) -> int:
    """Run 1 sanity, SELECTION window only (spec §4.3: nothing outside it
    is inspected before its stage)."""
    run_dir = Path(args.out_root) / "run1"
    rows = sm.in_window(read_rows(run_dir), sm.SELECTION_WINDOW)
    funnel = sm.funnel(read_arms(run_dir), sm.SELECTION_WINDOW)
    lo, hi = sm.SELECTION_WINDOW
    lines = ["# v127 structure-break armed entries — run1 replay", "",
             f"Rows in the selection window {lo}..{hi}: {len(rows)} across "
             f"{len({r.trade.ticker for r in rows})} tickers.", "", sm.LIMITATIONS, "",
             "| arm | rows | " + " | ".join(sm.FUNNEL_COLUMNS) + " |",
             "|---|---|" + "---|" * len(sm.FUNNEL_COLUMNS),
             f"| baseline | {len(sm.arm_trades(rows, sm.BASELINE))} |" + " |" * len(sm.FUNNEL_COLUMNS)]
    for cell in sm.CELLS:
        counts = funnel[cell.cell_id]
        lines.append(f"| {cell.cell_id} | {len(sm.arm_trades(rows, cell.cell_id))} | "
                     + " | ".join(str(counts[c]) for c in sm.FUNNEL_COLUMNS) + " |")
    Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_md).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


def _write_text(path, text):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8")


def cmd_select(args) -> int:
    run_dir = Path(args.out_root) / "run1"
    rows = sm.in_window(read_rows(run_dir), sm.SELECTION_WINDOW)
    if not rows:
        print("no rows in the selection window", flush=True)
        return 2
    selection = sm.select_cell(rows)
    funnel = sm.funnel(read_arms(run_dir), sm.SELECTION_WINDOW)
    payload = {"verdict": selection.verdict, "selected": selection.selected, "best": selection.best,
               "scores": [dataclasses.asdict(s) for s in selection.scores],
               "plateaus": list(selection.plateaus), "funnel": funnel}
    if args.out_json:
        _write_text(args.out_json, json.dumps(payload, indent=1))
    if args.out_md:
        _write_text(args.out_md, sm.render_selection_md(selection, funnel))
    print(f"verdict: {selection.verdict}; selected: {selection.selected}", flush=True)
    return 0 if selection.verdict == sm.SELECTED else 1


def cmd_arms(args) -> int:
    root = Path(args.out_root)
    if args.stage == "validation":
        blob = sm.arms_blob(sm.in_window(read_rows(root / "run2"), sm.VALIDATION_WINDOW), args.cell)
    elif args.stage == "walkforward":
        blob = sm.folds_blob(read_rows(root / "run1"), args.cell)
    else:
        blob = sm.arms_blob(sm.in_window(read_rows(root / "run1"), sm.SELECTION_WINDOW), args.cell)
    parts = blob["folds"] if "folds" in blob else [blob]
    if not all(part["baseline"] for part in parts):
        print("an arm has no baseline rows", flush=True)
        return 2
    _write_text(args.out, json.dumps(blob))
    return 0


def _permute_worker(task):
    from swingbot.core.backtesting.armed_replay import arm_candidates
    from swingbot.core.backtesting.structure_arm import replay_structure, structure_permutations
    ticker, cache_dir, cell_id, horizons, n, seed = task
    frame = load_frame(cache_dir, ticker)
    permutations = [[] for _ in range(n)]
    if frame is None or frame.empty:
        return ticker, permutations
    cell = sm.cell_by_id(cell_id)
    for horizon in horizons:
        cache: dict = {}
        candidates = arm_candidates(ticker, frame, horizon, level_cache=cache)
        result = replay_structure(ticker, frame, horizon, [cell], candidates=candidates,
                                  level_cache=cache)[cell_id]
        drawn = structure_permutations(ticker, frame, horizon, cell, result.confirmed, n=n,
                                       seed=seed, level_cache=cache)
        for index, rows in enumerate(drawn):
            permutations[index] += rows
    return ticker, permutations


def _collect_permutations(tasks, workers, progress) -> list:
    lo, hi = sm.VALIDATION_WINDOW
    permuted = [[] for _ in range(sm.PERMUTATION_N)]
    try:
        for done, (ticker, drawn) in enumerate(_map(_permute_worker, tasks, workers), 1):
            for index, perm_rows in enumerate(drawn):
                permuted[index] += [ArmTrade(ticker, strategy, horizon, date, outcome, None, None)
                                    for date, strategy, horizon, outcome in perm_rows
                                    if lo <= date <= hi]
            pct = 100 * done // len(tasks) if tasks else 100
            progress.write_text(f"{done}/{len(tasks)} tickers ({pct}%)\n")
            print(f"[{done}/{len(tasks)}] {ticker} ({pct}%)", flush=True)
    finally:
        progress.unlink(missing_ok=True)
    return permuted


def cmd_permute(args) -> int:
    run_dir = Path(args.out_root) / "run2"
    meta_path = run_dir / "run.json"
    if not meta_path.exists():
        print("REFUSED -- no run2 replay to permute", flush=True)
        return 4
    meta = json.loads(meta_path.read_text())
    rows = sm.in_window(read_rows(run_dir), sm.VALIDATION_WINDOW)
    baseline, real = sm.arm_trades(rows, sm.BASELINE), sm.arm_trades(rows, args.cell)
    tickers = sorted({row.trade.ticker for row in rows})
    tasks = [(t, args.cache_dir, args.cell, meta["horizons"], sm.PERMUTATION_N, sm.PERMUTATION_SEED)
             for t in tickers]
    permuted = _collect_permutations(tasks, args.workers, run_dir / "progress.txt")
    result = {**sm.permutation_p(baseline, real, permuted), "seed": sm.PERMUTATION_SEED,
              "cell": args.cell, "window": list(sm.VALIDATION_WINDOW)}
    _write_text(args.out_json, json.dumps(result, indent=1))
    print(f"permutation p = {result['p_value']}", flush=True)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    cell_ids = [cell.cell_id for cell in sm.CELLS]
    workers = max(1, os.cpu_count() or 1)

    def command(name):
        p = sub.add_parser(name)
        p.add_argument("--cache-dir", default=str(CACHE_DIR))
        p.add_argument("--out-root", default=str(OUT_ROOT))
        return p

    p = command("replay")
    p.add_argument("--run", choices=RUNS, required=True)
    p.add_argument("--tickers"); p.add_argument("--horizons"); p.add_argument("--stage2-doc")
    p.add_argument("--workers", type=int, default=workers)
    command("summary").add_argument("--out-md", required=True)
    p = command("select")
    p.add_argument("--out-md"); p.add_argument("--out-json")
    p = command("arms")
    p.add_argument("--stage", choices=("mde", "walkforward", "validation"), required=True)
    p.add_argument("--cell", choices=cell_ids, required=True); p.add_argument("--out", required=True)
    p = command("permute")
    p.add_argument("--cell", choices=cell_ids, required=True); p.add_argument("--out-json", required=True)
    p.add_argument("--workers", type=int, default=workers)
    return parser


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    handler = {"replay": cmd_replay, "summary": cmd_summary, "select": cmd_select,
               "arms": cmd_arms, "permute": cmd_permute}[args.command]
    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
