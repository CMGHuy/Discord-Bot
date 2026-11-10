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
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "scripts" / "data"), str(ROOT / "scripts" / "backtest")]

from swingbot.core.backtesting import confluence_limit_replay as clr  # noqa: E402
from swingbot.core.backtesting.acceptance_exit_funnel import TRAIN, VALIDATION  # noqa: E402
from swingbot.core.backtesting.backtest_scenarios import _resolve_replay_workers  # noqa: E402
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
