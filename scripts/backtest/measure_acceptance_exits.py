#!/usr/bin/env python3
"""v129 acceptance-failure exits: Stage 0-3 driver, one arm and one stage per call.

Each stage reads the previous stage's verdict JSON and refuses to run without
the verdict it needs, so a closed arm cannot be advanced by hand:

  stage 0  paired MDE precheck on TRAIN   -> POWERED | UNDERPOWERED
  stage 1  TRAIN plateau selection        -> SELECTED | NO_ELIGIBLE_CELL
  stage 2  TRAIN calendar-year folds      -> PASS | FAIL
  stage 3  ONE-SHOT VALIDATION            -> PASS | FAIL

TRAIN rows are replayed once (stage 0) and reused. Stage 3 replays VALIDATION
for the selected cell only and is refused when its output exists.

PROGRESS: a flushed line per ticker, plus logs/measure_acceptance_exits.
arm<ARM>.progress (percent, rewritten per ticker, deleted on completion).

Run: python scripts/backtest/measure_acceptance_exits.py --arm Z --stage 0
"""
from __future__ import annotations

import argparse
import functools
import json
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "scripts" / "data"), str(ROOT / "scripts" / "backtest")]

from swingbot.core.backtesting import acceptance_exit_funnel as funnel  # noqa: E402
from swingbot.core.backtesting.acceptance import BOOTSTRAP_RESAMPLES  # noqa: E402
from swingbot.core.backtesting.acceptance_replay import CELLS, cell_key, replay_entries  # noqa: E402
from swingbot.core.backtesting.backtest_scenarios import _resolve_replay_workers  # noqa: E402
from swingbot.core.market.strategy_types import LEGACY_HORIZONS  # noqa: E402

RESULTS = ROOT / "docs" / "superpowers" / "results" / "v129"
LOG_DIR = ROOT / "logs"
PREFIX = "2026-10-03-v129"
#: stage -> (the stage it consumes, the verdict that stage must carry).
REQUIRES = {1: (0, "POWERED"), 2: (1, "SELECTED"), 3: (2, "PASS")}
ADVANCING = ("POWERED", "SELECTED", "PASS")


def stage_path(out_dir, arm, stage) -> Path:
    return Path(out_dir) / f"{PREFIX}-arm{arm}-stage{stage}.json"


def rows_path(out_dir, arm, window) -> Path:
    return Path(out_dir) / f"{PREFIX}-arm{arm}-{window}-rows.json"


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write(path, blob, indent=1) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(blob, indent=indent), encoding="utf-8")


def _refuse(message):
    raise SystemExit(f"refused: {message}")


# --- replay ------------------------------------------------------------------

def _worker(task):
    """One ticker, every horizon -- the process-pool entry point."""
    arm, ticker, window, cells = task
    from measure_arms import load_frame
    frame = load_frame(ticker)
    if frame is None:
        return ticker, []
    return ticker, replay_entries(arm, ticker, frame, LEGACY_HORIZONS,
                                  start=window[0], end=window[1], cells=cells)


def _write_progress(path, done, total) -> None:
    try:
        path.write_text(f"{done}/{total} tickers ({done / total * 100:.0f}%)\n",
                        encoding="utf-8")
    except OSError:
        pass


def build_rows(arm, window, cells, *, tickers=None, workers=None) -> list:
    """Replay every cached ticker and return its rows in ticker order, so the
    output is identical whatever order the pool finishes in."""
    from measure_arms import cached_universe
    universe = cached_universe()[:tickers] if tickers else cached_universe()
    tasks = [(arm, ticker, tuple(window), tuple(tuple(c) for c in cells))
             for ticker in universe]
    LOG_DIR.mkdir(exist_ok=True)
    progress = LOG_DIR / f"measure_acceptance_exits.arm{arm}.progress"
    by_ticker: dict = {}

    def record(ticker, rows):
        by_ticker[ticker] = rows
        print(f"  [arm {arm} {window[0]}..{window[1]}] {len(by_ticker)}/{len(tasks)} "
              f"{ticker}: {len(rows)} entries", flush=True)
        _write_progress(progress, len(by_ticker), len(tasks))

    n_workers = _resolve_replay_workers(workers)
    if n_workers <= 1 or len(tasks) <= 1:
        for task in tasks:
            record(*_worker(task))
    else:
        with ProcessPoolExecutor(max_workers=n_workers) as pool:
            for future in as_completed([pool.submit(_worker, task) for task in tasks]):
                record(*future.result())
    progress.unlink(missing_ok=True)
    return [row for ticker in sorted(by_ticker) for row in by_ticker[ticker]]


# --- stages ------------------------------------------------------------------

def _previous(out_dir, arm, stage) -> dict:
    """The verdict JSON this stage consumes, or a refusal."""
    needed_stage, needed_verdict = REQUIRES[stage]
    path = stage_path(out_dir, arm, needed_stage)
    if not path.exists():
        _refuse(f"stage {stage} needs {path.name} -- run stage {needed_stage} first")
    previous = _load(path)
    if previous["verdict"] != needed_verdict:
        _refuse(f"arm {arm} closed at stage {needed_stage} with "
                f"{previous['verdict']} -- stage {stage} does not run")
    return previous


def _saved_rows(out_dir, arm, window_name, window, cells, build) -> list:
    """Rows from the rows file, building (and saving) them when absent."""
    path = rows_path(out_dir, arm, window_name)
    if not path.exists():
        _write(path, build(arm, window, cells), indent=None)
    return _load(path)


def _train_rows(out_dir, arm, build) -> list:
    return _saved_rows(out_dir, arm, "train", funnel.TRAIN, CELLS[arm], build)


def _stage0(out_dir, arm, build, n_resamples) -> dict:
    return funnel.stage0(_train_rows(out_dir, arm, build), arm)


def _stage1(out_dir, arm, build, n_resamples) -> dict:
    _previous(out_dir, arm, 1)
    rows = _train_rows(out_dir, arm, build)
    out = funnel.stage1(rows, arm, n_resamples=n_resamples)
    out["reports"] = [funnel.report(rows, arm, cell_key(m, b), n_resamples=n_resamples)
                      for m, b in CELLS[arm]]
    return out


def _stage2(out_dir, arm, build, n_resamples) -> dict:
    selected = _previous(out_dir, arm, 2)["selected"]
    return funnel.stage2(_train_rows(out_dir, arm, build), arm, selected["cell"])


def _stage3(out_dir, arm, build, n_resamples) -> dict:
    _previous(out_dir, arm, 3)
    selected = _load(stage_path(out_dir, arm, 1))["selected"]
    rows = _saved_rows(out_dir, arm, "validation", funnel.VALIDATION,
                       [(selected["m"], selected["b"])], build)
    out = funnel.stage3(rows, arm, selected["cell"], n_resamples=n_resamples)
    out["report"] = funnel.report(rows, arm, selected["cell"], n_resamples=n_resamples)
    return out


_STAGES = {0: _stage0, 1: _stage1, 2: _stage2, 3: _stage3}


def run_stage(arm, stage, out_dir, *, build, n_resamples: int = BOOTSTRAP_RESAMPLES) -> dict:
    """Run one stage and write its verdict JSON. Stages 0-2 are TRAIN-only
    and deterministic, so they may be re-run; stage 3 may not."""
    out_dir = Path(out_dir)
    target = stage_path(out_dir, arm, stage)
    if stage == 3 and target.exists():
        _refuse(f"{target.name} exists -- arm {arm}'s one VALIDATION shot is spent")
    out = _STAGES[stage](out_dir, arm, build, n_resamples)
    _write(target, out)
    return out


# --- CLI ---------------------------------------------------------------------

def _cli_refusal(args) -> str | None:
    if args.tickers and args.stage == 3:
        return ("refused:partial-validation -- stage 3 is the one shot and runs "
                "the full universe; drop --tickers")
    if args.tickers and args.out_dir.resolve() == RESULTS.resolve():
        return ("refused:smoke-run -- --tickers needs a scratch --out-dir, never "
                "the committed results directory")
    if args.stage == 3 and not (args.preregistration and args.preregistration.exists()):
        return ("refused:no-preregistration -- stage 3 needs --preregistration "
                "<committed doc>. This is the one shot.")
    return None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--arm", required=True, choices=sorted(CELLS))
    parser.add_argument("--stage", required=True, type=int, choices=sorted(_STAGES))
    parser.add_argument("--out-dir", type=Path, default=RESULTS)
    parser.add_argument("--preregistration", type=Path, default=None)
    parser.add_argument("--tickers", type=int, default=None)
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--resamples", type=int, default=BOOTSTRAP_RESAMPLES)
    args = parser.parse_args(argv)
    refusal = _cli_refusal(args)
    if refusal:
        print(refusal, file=sys.stderr)
        return 1
    build = functools.partial(build_rows, tickers=args.tickers, workers=args.workers)
    out = run_stage(args.arm, args.stage, args.out_dir, build=build,
                    n_resamples=args.resamples)
    print(f"arm {args.arm} stage {args.stage}: {out['verdict']} "
          f"-> {stage_path(args.out_dir, args.arm, args.stage)}", flush=True)
    return 0 if out["verdict"] in ADVANCING else 1


if __name__ == "__main__":
    sys.exit(main())
