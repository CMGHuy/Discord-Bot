#!/usr/bin/env python3
"""v88 A1: build and score the pre-registered armed-confluence-entry grid.

Read docs/superpowers/specs/2026-09-15-v88-armed-confluence-entries-design.md
§4 first. The arithmetic lives in swingbot/core/backtesting/armed_measurement.py;
this script only replays frames and moves rows to and from disk. Stage
verdicts come from scripts/backtest/validate_component.py, fed by `arms`.

    replay   --run run1 | run2     sharded per ticker, resumable; run2 refused
                                   without a Stage 2 doc reading **Overall: PASS**
    summary  --run R --window LO..HI --out-md PATH
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
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from swingbot.core.backtesting import armed_measurement as am  # noqa: E402
from swingbot.core.backtesting.acceptance import ArmTrade, arm_trade_from_plan  # noqa: E402
from swingbot.core.market.strategy_types import HORIZONS  # noqa: E402

CACHE_DIR = ROOT / "data" / "backtest_cache"
OUT_ROOT = ROOT / "data" / "v88"
RUNS = {"run1": am.RUN1_WINDOW, "run2": am.VALIDATION_WINDOW}
STAGE2_PASS_MARKER = "**Overall: PASS**"


def load_frame(cache_dir, symbol):
    path = Path(cache_dir) / f"{symbol}.csv"
    if not path.exists():
        return None
    try:
        return pd.read_csv(path, index_col="Date", parse_dates=True)
    except Exception as exc:
        # belt-and-braces: a poisoned cache file must not stall an unattended
        # multi-hour replay -- same convention as data_refresh.refresh_all.
        print(f"WARNING: {symbol}.csv unreadable, skipping ({exc})", flush=True)
        return None


def _trade(frame, index, plan, date) -> ArmTrade:
    from swingbot.core.planning.plan_engine import simulate_exit
    result = simulate_exit(frame, index, plan, scale_out=True)
    trade = arm_trade_from_plan(plan, entry_date=date, outcome=result.outcome,
                                r_multiple=result.r_total)
    return dataclasses.replace(trade, strategy=f"confluence:{plan.strategy}")


def ticker_rows(ticker, frame, window, horizons):
    """Baseline rows (today's replay) and every cell's rows, in window."""
    from swingbot.core.backtesting.armed_replay import arm_candidates, replay_armed
    from swingbot.core.backtesting.backtest_scenarios import replay_scenarios
    lo, hi = window
    rows, counts = [], {}
    for horizon in horizons:
        for index, plan in replay_scenarios(ticker, frame, horizon):
            date = str(frame.index[index].date())
            if lo <= date <= hi:
                rows.append(am.Row(am.BASELINE, _trade(frame, index, plan, date)))
        cache: dict = {}
        candidates = arm_candidates(ticker, frame, horizon, level_cache=cache)
        results = replay_armed(ticker, frame, horizon, am.CELLS, candidates=candidates,
                               level_cache=cache)
        for cell_id, result in results.items():
            counts[f"{horizon}|{cell_id}"] = dict(result.counts)
            for j, plan, kind in result.issued:
                date = str(frame.index[j].date())
                if lo <= date <= hi:
                    rows.append(am.Row(cell_id, _trade(frame, j, plan, date), kind))
    return rows, counts


def _replay_worker(task):
    ticker, cache_dir, window, horizons = task
    frame = load_frame(cache_dir, ticker)
    if frame is None or frame.empty:
        return ticker, [], {}
    rows, counts = ticker_rows(ticker, frame, window, horizons)
    return ticker, [row.to_dict() for row in rows], counts


def write_shard(path, rows):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    temporary.replace(path)


def read_rows(run_dir) -> list:
    rows = []
    for shard in sorted(Path(run_dir).glob("*.jsonl")):
        rows += [am.Row.from_dict(json.loads(line))
                 for line in shard.read_text(encoding="utf-8").splitlines() if line]
    return rows


def run_meta(cache_dir, window, horizons) -> dict:
    return {"cache_files": sorted(p.name for p in Path(cache_dir).glob("*.csv")),
            "window": list(window), "horizons": list(horizons),
            "cells": [cell.cell_id for cell in am.CELLS]}


def _map(worker, tasks, workers):
    """Results in task order; the pool is shut down when iteration ends."""
    if workers == 1:
        yield from map(worker, tasks)
        return
    with ProcessPoolExecutor(max_workers=workers) as pool:
        yield from pool.map(worker, tasks)


def cmd_replay(args) -> int:
    if args.run == "run2":
        doc = Path(args.stage2_doc) if args.stage2_doc else None
        if doc is None or not doc.exists() or STAGE2_PASS_MARKER not in doc.read_text(encoding="utf-8"):
            print("REFUSED -- run2 replays VALIDATION; it needs --stage2-doc reading "
                  f"{STAGE2_PASS_MARKER}", flush=True)
            return 3
    cache = Path(args.cache_dir)
    horizons = args.horizons.split(",") if args.horizons else list(HORIZONS)
    run_dir = Path(args.out_root) / args.run
    run_dir.mkdir(parents=True, exist_ok=True)
    meta = run_meta(cache, RUNS[args.run], horizons)
    meta_path = run_dir / "run.json"
    if meta_path.exists() and json.loads(meta_path.read_text()) != meta:
        print(f"REFUSED -- {meta_path} was written for a different cache/window/horizons/grid",
              flush=True)
        return 4
    meta_path.write_text(json.dumps(meta, indent=1))
    symbols = args.tickers.split(",") if args.tickers else sorted(p.stem for p in cache.glob("*.csv"))
    todo = [s for s in symbols if not (run_dir / f"{s}.jsonl").exists()]
    tasks = [(s, str(cache), RUNS[args.run], horizons) for s in todo]
    progress = run_dir / "progress.txt"
    try:
        for done, (ticker, rows, counts) in enumerate(_map(_replay_worker, tasks, args.workers), 1):
            write_shard(run_dir / f"{ticker}.jsonl", rows)
            (run_dir / f"{ticker}.counts.json").write_text(json.dumps(counts))
            pct = 100 * done // len(todo) if todo else 100
            progress.write_text(f"{done}/{len(todo)} tickers ({pct}%)\n")
            print(f"[{done}/{len(todo)}] {ticker}: {len(rows)} rows ({pct}%)", flush=True)
    finally:
        progress.unlink(missing_ok=True)
    print(f"complete: {len(read_rows(run_dir))} rows", flush=True)
    return 0


def cmd_summary(args) -> int:
    run_dir = Path(args.out_root) / args.run
    lo, hi = args.window.split("..")
    rows = am.in_window(read_rows(run_dir), (lo, hi))
    totals: dict = {}
    for path in sorted(run_dir.glob("*.counts.json")):
        for key, counts in json.loads(path.read_text()).items():
            cell_id = key.split("|", 1)[1]
            bucket = totals.setdefault(cell_id, {})
            for name, value in counts.items():
                bucket[name] = bucket.get(name, 0) + value
    names = sorted({name for bucket in totals.values() for name in bucket})
    lines = [f"# v88 armed confluence entries — {args.run} replay", "",
             f"Rows in window {lo}..{hi}: {len(rows)} across "
             f"{len({r.trade.ticker for r in rows})} tickers.", "", am.LIMITATIONS, "",
             "| arm | rows in window |", "|---|---|",
             f"| baseline | {len(am.arm_trades(rows, am.BASELINE))} |"]
    lines += [f"| {c.cell_id} | {len(am.arm_trades(rows, c.cell_id))} |" for c in am.CELLS]
    lines += ["", "## Arm funnel, whole replayed frame (not windowed)", "",
              "| cell | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    lines += [f"| {c.cell_id} | " + " | ".join(str(totals.get(c.cell_id, {}).get(n, 0)) for n in names) + " |"
              for c in am.CELLS]
    Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_md).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


def cmd_select(args) -> int:
    rows = am.in_window(read_rows(Path(args.out_root) / "run1"), am.SELECTION_WINDOW)
    if not rows:
        print("no rows in the selection window", flush=True)
        return 2
    selection = am.select_cell(rows)
    payload = {"verdict": selection.verdict, "selected": selection.selected, "best": selection.best,
               "scores": [dataclasses.asdict(s) for s in selection.scores],
               "plateaus": list(selection.plateaus)}
    if args.out_json:
        Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out_json).write_text(json.dumps(payload, indent=1), encoding="utf-8")
    if args.out_md:
        Path(args.out_md).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out_md).write_text(am.render_selection_md(selection), encoding="utf-8")
    print(f"verdict: {selection.verdict}; selected: {selection.selected}", flush=True)
    return 0 if selection.verdict == am.SELECTED else 1


def cmd_arms(args) -> int:
    root = Path(args.out_root)
    if args.stage == "validation":
        blob = am.arms_blob(am.in_window(read_rows(root / "run2"), am.VALIDATION_WINDOW), args.cell)
    elif args.stage == "walkforward":
        blob = am.folds_blob(read_rows(root / "run1"), args.cell)
    else:
        blob = am.arms_blob(am.in_window(read_rows(root / "run1"), am.SELECTION_WINDOW), args.cell)
    parts = blob["folds"] if "folds" in blob else [blob]
    if not all(part["baseline"] for part in parts):
        print("an arm has no baseline rows", flush=True)
        return 2
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(blob), encoding="utf-8")
    return 0


def _permute_worker(task):
    from swingbot.core.backtesting.armed_replay import arm_candidates, delay_permutations, replay_armed
    ticker, cache_dir, cell_id, horizons, n, seed = task
    frame = load_frame(cache_dir, ticker)
    permutations = [[] for _ in range(n)]
    if frame is None or frame.empty:
        return ticker, permutations
    cell = am.cell_by_id(cell_id)
    for horizon in horizons:
        cache: dict = {}
        candidates = arm_candidates(ticker, frame, horizon, level_cache=cache)
        result = replay_armed(ticker, frame, horizon, [cell], candidates=candidates,
                              level_cache=cache)[cell_id]
        drawn = delay_permutations(ticker, frame, horizon, cell, result.confirmed, n=n,
                                   seed=seed, level_cache=cache)
        for index, rows in enumerate(drawn):
            permutations[index] += rows
    return ticker, permutations


def cmd_permute(args) -> int:
    run_dir = Path(args.out_root) / "run2"
    meta_path = run_dir / "run.json"
    if not meta_path.exists():
        print("REFUSED -- no run2 replay to permute", flush=True)
        return 4
    meta = json.loads(meta_path.read_text())
    rows = am.in_window(read_rows(run_dir), am.VALIDATION_WINDOW)
    baseline, real = am.arm_trades(rows, am.BASELINE), am.arm_trades(rows, args.cell)
    tickers = sorted({row.trade.ticker for row in rows})
    tasks = [(t, args.cache_dir, args.cell, meta["horizons"], am.PERMUTATION_N, am.PERMUTATION_SEED)
             for t in tickers]
    lo, hi = am.VALIDATION_WINDOW
    permuted = [[] for _ in range(am.PERMUTATION_N)]
    progress = run_dir / "progress.txt"
    try:
        for done, (ticker, drawn) in enumerate(_map(_permute_worker, tasks, args.workers), 1):
            for index, perm_rows in enumerate(drawn):
                permuted[index] += [ArmTrade(ticker, strategy, horizon, date, outcome, None, None)
                                    for date, strategy, horizon, outcome in perm_rows
                                    if lo <= date <= hi]
            pct = 100 * done // len(tasks) if tasks else 100
            progress.write_text(f"{done}/{len(tasks)} tickers ({pct}%)\n")
            print(f"[{done}/{len(tasks)}] {ticker} ({pct}%)", flush=True)
    finally:
        progress.unlink(missing_ok=True)
    result = {**am.permutation_p(baseline, real, permuted), "seed": am.PERMUTATION_SEED,
              "cell": args.cell, "window": list(am.VALIDATION_WINDOW)}
    Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_json).write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(f"permutation p = {result['p_value']}", flush=True)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p):
        p.add_argument("--cache-dir", default=str(CACHE_DIR))
        p.add_argument("--out-root", default=str(OUT_ROOT))

    cell_ids = [cell.cell_id for cell in am.CELLS]
    p = sub.add_parser("replay"); common(p)
    p.add_argument("--run", choices=RUNS, required=True)
    p.add_argument("--tickers"); p.add_argument("--horizons"); p.add_argument("--stage2-doc")
    p.add_argument("--workers", type=int, default=max(1, os.cpu_count() or 1))
    p = sub.add_parser("summary"); common(p)
    p.add_argument("--run", choices=RUNS, required=True)
    p.add_argument("--window", required=True); p.add_argument("--out-md", required=True)
    p = sub.add_parser("select"); common(p)
    p.add_argument("--out-md"); p.add_argument("--out-json")
    p = sub.add_parser("arms"); common(p)
    p.add_argument("--stage", choices=("mde", "walkforward", "validation"), required=True)
    p.add_argument("--cell", choices=cell_ids, required=True); p.add_argument("--out", required=True)
    p = sub.add_parser("permute"); common(p)
    p.add_argument("--cell", choices=cell_ids, required=True); p.add_argument("--out-json", required=True)
    p.add_argument("--workers", type=int, default=max(1, os.cpu_count() or 1))

    args = parser.parse_args(argv)
    handler = {"replay": cmd_replay, "summary": cmd_summary, "select": cmd_select,
               "arms": cmd_arms, "permute": cmd_permute}[args.command]
    return handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
