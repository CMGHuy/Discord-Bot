#!/usr/bin/env python3
"""v212 confluence limit entry: Stage -1..3 driver (spec § Pass rule).

  census    Stage -1 rows (plans and fills, no outcome)
  rows      outcome rows for a window (--touch: the disclosed touch-fill sensitivity)
  stage     one funnel stage (V212-13c)
  ledger    one preregistration-ledger row per look (V212-13c)

Every command refuses without the committed v212 pre-registration. Rows are
built one ticker at a time and each finished ticker is written to
--checkpoint-dir at once, so a restart skips it; progress prints a flushed
percent. Universe and frames: measure_arms (MEASURE_ARMS_UNIVERSE=cache,
BACKTEST_CACHE_DIR=data/backtest_cache_ext).

Run: python scripts/backtest/measure_confluence_limit.py rows --window train \
         --preregistration docs/superpowers/results/<date>-v212-preregistration.md
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "scripts" / "data"), str(ROOT / "scripts" / "backtest")]

from swingbot import config  # noqa: E402
from swingbot.core.backtesting import confluence_limit_replay as clr  # noqa: E402
from swingbot.core.backtesting.acceptance import (CLOSED, ArmTrade, expectancy_r,  # noqa: E402
                                                  win_rate)
from swingbot.core.backtesting.acceptance_exit_funnel import TRAIN, VALIDATION  # noqa: E402
from swingbot.core.backtesting.backtest_scenarios import _resolve_replay_workers  # noqa: E402
from swingbot.core.backtesting.backtest_wf import portfolio_replay  # noqa: E402
from swingbot.core.market.strategy_types import LEGACY_HORIZONS  # noqa: E402

RESULTS = ROOT / "docs" / "superpowers" / "results" / "v212"
CHECKPOINTS = ROOT / "logs" / "v212-checkpoints"
FOLD_YEARS = (2021, 2022, 2023)
WINDOWS = {"train": TRAIN, "validation": VALIDATION}
#: stage -> (the stage it consumes, the verdict that stage must carry).
REQUIRES = {0: (-1, "REACHABLE"), 1: (0, "POWERED"), 2: (1, "SELECTED"), 3: (2, "PASS")}
ADVANCING = ("REACHABLE", "POWERED", "SELECTED", "PASS")
#: PRE-REGISTERED pass clauses (spec § Pass rule). Changing one is a new pre-registration.
FILLS_SHARE = 0.5
WR_SLACK_PP = 2.0
THIN_PER_DIRECTION = 30
DIRECTIONS = ("bullish", "bearish")
CLAUSE_NAMES = ("expr_beats_reference", "fills_half_of_reference", "wr_within_2pp")
KINDS = {"census": clr.census, "rows": clr.replay_entries}


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write(path, blob, indent=1) -> None:
    """Atomic: a crash mid-write never leaves a truncated checkpoint behind."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(blob, indent=indent), encoding="utf-8")
    os.replace(tmp, path)


def _refuse(message):
    raise SystemExit(f"refused: {message}")


# --- refusals ------------------------------------------------------------------

def _committed(path: Path) -> bool:
    tracked = subprocess.run(["git", "ls-files", "--error-unmatch", str(path)], cwd=ROOT,
                             capture_output=True)
    clean = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", str(path)], cwd=ROOT,
                           capture_output=True)
    return tracked.returncode == 0 and clean.returncode == 0


def require_preregistration(path) -> None:
    """Every command refuses before the pre-registration is committed."""
    if path is None or not Path(path).name.endswith("-v212-preregistration.md") \
            or not Path(path).exists():
        _refuse(f"no-preregistration -- pass the committed v212 pre-registration, got {path}")
    if not _committed(Path(path).resolve()):
        _refuse(f"uncommitted-preregistration -- commit {path} before any compute")


# --- stage files ---------------------------------------------------------------

def stage_path(out_dir, stage) -> Path:
    return Path(out_dir) / f"v212-stage{'M1' if stage == -1 else stage}.json"


def rows_file(out_dir, kind, window_name, touch=False, subset="") -> Path:
    """`subset` ('-n5', '-f0.5') marks a smoke or one-cell run, so it can never
    land on the measured file name a stage loads."""
    return Path(out_dir) / f"v212-{kind}-{window_name}{'-touch' if touch else ''}{subset}-rows.json"


def _previous(out_dir, stage) -> dict:
    """The verdict JSON `stage` consumes, or a refusal: a closed run never
    advances by hand."""
    needed_stage, needed_verdict = REQUIRES[stage]
    path = stage_path(out_dir, needed_stage)
    if not path.exists():
        _refuse(f"stage {stage} needs {path.name} -- run stage {needed_stage} first")
    previous = _load(path)
    if previous["verdict"] != needed_verdict:
        _refuse(f"v212 closed at stage {needed_stage} with {previous['verdict']} "
                f"-- stage {stage} does not run")
    return previous


# --- checkpointed build ----------------------------------------------------------

def universe() -> list[str]:
    from measure_arms import cached_universe
    return cached_universe()


def _worker(task):
    """One ticker, every legacy horizon -- the process-pool entry point."""
    kind, ticker, window, touch, cells = task
    from measure_arms import load_frame
    frame = load_frame(ticker)
    if frame is None:
        return ticker, []
    extra = {"touch": touch} if kind == "rows" else {}
    return ticker, KINDS[kind](ticker, frame, LEGACY_HORIZONS, window, cells=cells, **extra)


def _tag(kind, window, touch, cells) -> str:
    rule = "touch" if touch else "through"
    return f"{kind}-{window[0]}_{window[1]}-{rule}-{'_'.join(clr.cell_key(c) for c in cells)}"


def _run_tasks(tasks, record, workers, worker) -> None:
    n_workers = _resolve_replay_workers(workers)
    if n_workers <= 1 or len(tasks) <= 1:
        for task in tasks:
            record(*worker(task))
        return
    with ProcessPoolExecutor(max_workers=n_workers) as pool:
        for future in as_completed([pool.submit(worker, task) for task in tasks]):
            record(*future.result())


def build(kind, window, *, touch=False, cells=clr.F_GRID, tickers=None, workers=None,
          checkpoint_dir=CHECKPOINTS, worker=None) -> list:
    """Rows for every universe ticker, in ticker order. Each finished ticker
    is persisted at once; a restart loads it instead of replaying it."""
    names = universe()
    names = names[:tickers] if tickers else names
    folder = Path(checkpoint_dir) / _tag(kind, window, touch, cells)
    done = {name: _load(folder / f"{name}.json") for name in names
            if (folder / f"{name}.json").exists()}
    tasks = [(kind, name, tuple(window), touch, tuple(float(c) for c in cells))
             for name in names if name not in done]

    def record(ticker, rows):
        _write(folder / f"{ticker}.json", rows, indent=None)
        done[ticker] = rows
        print(f"  [{kind} {window[0]}..{window[1]}] {len(done)}/{len(names)} "
              f"({len(done) / len(names) * 100:.0f}%) {ticker}: {len(rows)} rows", flush=True)

    _run_tasks(tasks, record, workers, worker or _worker)
    return [row for name in sorted(done) for row in done[name]]


# --- census (Stage -1, outcome-blind) ---------------------------------------------

def _drop_reasons(rows, cell) -> dict:
    return dict(Counter(r["drops"][cell] for r in rows if r["drops"].get(cell)))


def _by_direction(rows) -> dict:
    return {d: sum(r["direction"] == d for r in rows) for d in DIRECTIONS}


def _d_range(rows) -> list | None:
    ds = [r["d_pct"] for r in rows]
    return [min(ds), max(ds)] if ds else None


def _census_cell(rows, cell) -> dict:
    kept = [r for r in rows if cell in r["drops"] and r["drops"][cell] is None]
    filled = [r for r in kept if r["filled"][cell]]
    return {"cell": cell, "in_scope": sum(cell in r["drops"] for r in rows),
            "drops": _drop_reasons(rows, cell), "kept": len(kept), "observed_n": len(filled),
            "fill_states": dict(Counter(r["fill_state"][cell] for r in kept)),
            "filled_by_direction": _by_direction(filled), "d_range": _d_range(kept)}


def stage_minus1(rows) -> dict:
    """Scope, drops, fills and the D range each cell reaches; no outcome read."""
    cells = [_census_cell(rows, cell) for cell in clr.CELLS]
    verdict = "REACHABLE" if any(cell["observed_n"] for cell in cells) else "refused:zero-diff"
    return {"stage": -1, "verdict": verdict, "alerts": len(rows), "cells": cells}


# --- populations and clauses ----------------------------------------------------

def closed(rows, arm) -> list:
    return [r for r in rows if r["arm"] == arm and r["filled"] and r["outcome"] in CLOSED]


def cell_keys(rows, cell) -> set:
    """The cell's in-scope alerts it did not drop -- its slice of D."""
    return {r["key"] for r in rows if r["arm"] == cell and r["dropped"] is None}


def reference_rows(rows, cell) -> list:
    keys = cell_keys(rows, cell)
    return [r for r in closed(rows, "ref") if r["key"] in keys]


def to_trade(r) -> ArmTrade:
    """A row as the harvest helpers read it: R after frictions, paired on the
    signal date."""
    return ArmTrade(ticker=r["ticker"], strategy=r["strategy"], horizon_key=r["horizon_key"],
                    entry_date=r["entry_date"], outcome=r["outcome"], r_multiple=r["r_net"],
                    planned_rr=r["planned_rr"], source="confluence", direction=r["direction"])


def clauses(arm_rows, ref_rows) -> dict:
    """Spec § Pass rule, point estimates, pooled directions."""
    arm, ref = [to_trade(r) for r in arm_rows], [to_trade(r) for r in ref_rows]
    exp, ref_exp, wr, ref_wr = expectancy_r(arm), expectancy_r(ref), win_rate(arm), win_rate(ref)
    out = {"n": len(arm), "ref_n": len(ref), "expr": exp, "ref_expr": ref_exp,
           "wr": wr, "ref_wr": ref_wr,
           "expr_beats_reference": exp is not None and ref_exp is not None and exp > ref_exp,
           "fills_half_of_reference": bool(ref) and len(arm) >= FILLS_SHARE * len(ref),
           "wr_within_2pp": wr is not None and ref_wr is not None
           and wr >= ref_wr - WR_SLACK_PP - 1e-9}
    out["passes"] = all(out[name] for name in CLAUSE_NAMES)
    return out


def neighbours(key: str) -> list[str]:
    index = clr.CELLS.index(key)
    return [clr.CELLS[j] for j in (index - 1, index + 1) if 0 <= j < len(clr.CELLS)]


def plateau(results: dict) -> str | None:
    """Spec § Stage 1 plateau: the winner is the highest-ExpR cell clearing
    all clauses (a tie keeps the smaller f: max keeps the first maximum in
    CELLS order); it stands only if every grid neighbour clears them too."""
    passing = [key for key in clr.CELLS if results[key]["passes"]]
    if not passing:
        return None
    winner = max(passing, key=lambda key: results[key]["expr"])
    return winner if all(results[other]["passes"] for other in neighbours(winner)) else None


def thin(rows) -> bool:
    """Stage 3 seal: fewer than 30 kept arm trades in either direction."""
    return any(sum(r["direction"] == d for r in rows) < THIN_PER_DIRECTION for d in DIRECTIONS)


# --- portfolio pass (spec rules 7 and 8) --------------------------------------------

def _signal(r) -> dict:
    return {"ticker": r["ticker"], "date": r["fill_date"], "exit_date": r["exit_date"],
            "r_multiple": r["r_net"], "direction": r["direction"], "outcome": r["outcome"],
            "strategy": r["strategy"], "stop_pct": r["stop_pct"], "key": r["key"],
            "entry": r["entry"], "stop_loss": r["stop_loss"]}


def run_portfolio(rows, *, sectors, cluster_fn) -> tuple:
    """One portfolio pass over closed rows dated at the fill: heat, sector,
    cluster, max-open and the notional caps re-run against the then-open
    book. Returns (kept rows, portfolio_replay result)."""
    result = portfolio_replay(
        [_signal(r) for r in rows], risk_pct=float(getattr(config, "RISK_PER_TRADE_PCT", 1.0)),
        heat_cap_pct=float(getattr(config, "PORTFOLIO_HEAT_CAP_PCT", 6.0)),
        sector_cap_pct=float(getattr(config, "SECTOR_HEAT_CAP_PCT", 3.0)),
        max_open=getattr(config, "MAX_OPEN_POSITIONS", None), sectors=sectors, throttles=False,
        max_position_pct=float(config.MAX_POSITION_SIZE_PCT),
        max_position_value=float(config.MAX_POSITION_VALUE_ABSOLUTE),
        cluster_fn=cluster_fn, track_keys=True)
    taken = set(result["taken_keys"])
    return [r for r in rows if r["key"] in taken], result


def portfolio_pass(rows, arm, *, sectors, cluster_fn) -> list:
    """Kept rows of one arm. For a cell's reference, pass rows already
    restricted to that cell's keys (reference_rows)."""
    return run_portfolio(closed(rows, arm), sectors=sectors, cluster_fn=cluster_fn)[0]


def make_cluster_fn(frames, sectors):
    """cluster_fn for portfolio_replay: correlation on frames cut BEFORE the
    fill bar, sector fallback on thin data (correlation.cluster_exposure)."""
    from swingbot.core.edge.correlation import cluster_check, cluster_exposure

    def cluster_fn(open_pos, sig, eff_risk) -> bool:
        names = {sig["ticker"], *(p["ticker"] for p in open_pos)}
        dfs = {t: frames[t].loc[:sig["date"]].iloc[:-1] for t in names if t in frames}
        exposure = cluster_exposure(open_pos, sig["ticker"], dfs, 10_000.0, sectors=sectors)
        return not cluster_check(exposure, eff_risk)["allowed"]
    return cluster_fn


def load_sectors() -> dict:
    from swingbot.core.marketdata.universe import sector_map
    return {**sector_map("etfs"), **sector_map("sp500")}


# --- CLI -------------------------------------------------------------------------

def _cells(names) -> tuple:
    """Grid order, no duplicates: the whole grid in any order is the full run."""
    return tuple(f for f, key in zip(clr.F_GRID, clr.CELLS) if key in names) if names         else clr.F_GRID


def _subset(tickers, cells) -> str:
    """'' for the full measured population, else a suffix naming the subset."""
    capped = f"-n{tickers}" if tickers else ""
    picked = "" if cells == clr.F_GRID else "-" + "_".join(clr.cell_key(c) for c in cells)
    return capped + picked


def _cmd_build(args):
    touch = getattr(args, "touch", False)
    cells = _cells(args.cells)
    rows = build(args.command, WINDOWS[args.window], touch=touch, cells=cells,
                 tickers=args.tickers, workers=args.workers, checkpoint_dir=args.checkpoint_dir)
    target = rows_file(args.out, args.command, args.window, touch,
                       subset=_subset(args.tickers, cells))
    _write(target, rows, indent=None)
    print(f"{args.command} {args.window}: {len(rows)} rows -> {target}", flush=True)
    return 0


COMMANDS = {"census": _cmd_build, "rows": _cmd_build}


def _common(sub) -> None:
    sub.add_argument("--preregistration", type=Path, required=True)
    sub.add_argument("--out", type=Path, default=RESULTS)
    sub.add_argument("--checkpoint-dir", type=Path, default=CHECKPOINTS)
    sub.add_argument("--tickers", type=int, default=None)
    sub.add_argument("--workers", type=int, default=None)


def _parser():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    subs = parser.add_subparsers(dest="command", required=True)
    for name in ("census", "rows"):
        sub = subs.add_parser(name)
        _common(sub)
        # VALIDATION rows are built only by `stage --stage 3`, for the selected cell.
        sub.add_argument("--window", choices=["train"], default="train")
        sub.add_argument("--cells", nargs="+", choices=clr.CELLS, default=None)
        if name == "rows":
            sub.add_argument("--touch", action="store_true")
    return parser, subs


def main(argv=None) -> int:
    parser, _ = _parser()
    args = parser.parse_args(argv)
    require_preregistration(args.preregistration)
    return COMMANDS[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
