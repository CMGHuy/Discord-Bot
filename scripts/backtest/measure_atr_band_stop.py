#!/usr/bin/env python3
"""v191 ATR-band stops: Stage -1..3 driver per arm, plus the two-arm Holm family.

  --arm K|R --stage -1  census of plans on fold-train, no outcome -> REACHABLE | refused:zero-diff
  --arm K|R --stage 0   paired dExpR MDE on fold-train             -> POWERED | UNDERPOWERED
  --arm K|R --stage 1   fold-train plateau selection over k         -> SELECTED | NO_ELIGIBLE_CELL
  --arm K|R --stage 2   walk-forward folds 2021 / 2022 / 2023       -> PASS | FAIL
  --arm K|R --stage 3   ONE-SHOT VALIDATION, selected k only        -> PASS | FAIL
  --family              Holm across both arms' Stage 3 p            -> the family file

Each stage reads the same arm's previous verdict JSON and refuses without the
verdict it needs, so a closed arm cannot be advanced by hand. Fold-train rows
are replayed once (stage 0) and reused; the 2023 fold and VALIDATION replay
the selected k only. Stage 3 is refused when its output exists and without
--preregistration <the v191 spec>. Instrument v1 and data source alpaca only;
the universe is measure_arms.cached_universe(): in a worktree set
MEASURE_ARMS_UNIVERSE=cache, HISTORY_STORE_DIR and BACKTEST_CACHE_DIR.

PROGRESS: a flushed line per ticker, plus
logs/measure_atr_band_stop.<arm>.<census|rows>.progress (percent, rewritten
per ticker, deleted on completion).

Run: python scripts/backtest/measure_atr_band_stop.py --arm K --stage -1
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

from swingbot.core.backtesting import atr_band_funnel as funnel  # noqa: E402
from swingbot.core.backtesting import atr_band_replay as abr  # noqa: E402
from swingbot.core.backtesting.acceptance import BOOTSTRAP_RESAMPLES  # noqa: E402
from swingbot.core.backtesting.backtest_scenarios import _resolve_replay_workers  # noqa: E402
from swingbot.core.backtesting.instrument import cli as instrument_cli  # noqa: E402
from swingbot.core.market.strategy_types import LEGACY_HORIZONS  # noqa: E402
from swingbot.core.marketdata import training_data  # noqa: E402

RESULTS = ROOT / "docs" / "superpowers" / "results" / "v191"
LOG_DIR = ROOT / "logs"
PREFIX = "2026-10-24-v191-arm{arm}"
FAMILY_FILE = "2026-10-24-v191-family.json"
PREREGISTRATION = (ROOT / "docs" / "superpowers" / "specs"
                   / "2026-10-24-v191-confluence-atr-band-stops-design.md")
#: stage -> (the stage it consumes, the verdict that stage must carry).
REQUIRES = {0: (-1, "REACHABLE"), 1: (0, "POWERED"), 2: (1, "SELECTED"), 3: (2, "PASS")}
ADVANCING = ("REACHABLE", "POWERED", "SELECTED", "PASS")
KINDS = {"rows": abr.replay_entries, "census": abr.census}


def stage_path(out_dir, arm, stage) -> Path:
    label = "M1" if stage == -1 else str(stage)
    return Path(out_dir) / f"{PREFIX.format(arm=arm)}-stage{label}.json"


def rows_path(out_dir, arm, name) -> Path:
    return Path(out_dir) / f"{PREFIX.format(arm=arm)}-{name}-rows.json"


def family_path(out_dir) -> Path:
    return Path(out_dir) / FAMILY_FILE


def _load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write(path, blob, indent=1) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(blob, indent=indent), encoding="utf-8")


def _refuse(message):
    raise SystemExit(f"refused: {message}")


# --- replay ------------------------------------------------------------------

def _init_worker() -> None:
    """Every process reads the alpaca store: BACKTEST_CACHE_DIR in a worktree
    would otherwise default the training source to yfinance."""
    training_data.select(funnel.DATA_SOURCE)


def _worker(task):
    """One ticker, one arm, every legacy horizon -- the process-pool entry point."""
    kind, arm, ticker, window, cells = task
    frame = training_data.load_daily(ticker)
    if frame is None or len(frame) == 0:
        return ticker, []
    return ticker, KINDS[kind](ticker, frame, LEGACY_HORIZONS, arm=arm,
                               start=window[0], end=window[1], cells=cells)


def _write_progress(path, done, total) -> None:
    try:
        path.write_text(f"{done}/{total} tickers ({done / total * 100:.0f}%)\n",
                        encoding="utf-8")
    except OSError:
        pass


def universe() -> list[str]:
    from measure_arms import cached_universe
    return cached_universe()


def _run_tasks(tasks, record, workers) -> None:
    n_workers = _resolve_replay_workers(workers)
    if n_workers <= 1 or len(tasks) <= 1:
        for task in tasks:
            record(*_worker(task))
        return
    with ProcessPoolExecutor(max_workers=n_workers, initializer=_init_worker) as pool:
        for future in as_completed([pool.submit(_worker, task) for task in tasks]):
            record(*future.result())


def build(kind, arm, window, cells, *, tickers=None, workers=None) -> list:
    """Replay every universe ticker for one arm; rows come back in ticker
    order, so the output is identical whatever order the pool finishes in."""
    _init_worker()
    names = universe()
    names = names[:tickers] if tickers else names
    tasks = [(kind, arm, ticker, tuple(window), tuple(float(k) for k in cells))
             for ticker in names]
    LOG_DIR.mkdir(exist_ok=True)
    progress = LOG_DIR / f"measure_atr_band_stop.{arm}.{kind}.progress"
    by_ticker: dict = {}

    def record(ticker, rows):
        by_ticker[ticker] = rows or []
        print(f"  [arm {arm} {kind} {window[0]}..{window[1]}] {len(by_ticker)}/{len(tasks)} "
              f"{ticker}: {len(by_ticker[ticker])} entries", flush=True)
        _write_progress(progress, len(by_ticker), len(tasks))

    _run_tasks(tasks, record, workers)
    progress.unlink(missing_ok=True)
    return [row for ticker in sorted(by_ticker) for row in by_ticker[ticker]]


# --- stages ------------------------------------------------------------------

def _previous(out_dir, arm, stage) -> dict:
    """The same arm's verdict JSON this stage consumes, or a refusal."""
    needed_stage, needed_verdict = REQUIRES[stage]
    path = stage_path(out_dir, arm, needed_stage)
    if not path.exists():
        _refuse(f"arm {arm} stage {stage} needs {path.name} -- run stage {needed_stage} first")
    previous = _load(path)
    if previous["verdict"] != needed_verdict:
        _refuse(f"arm {arm} closed at stage {needed_stage} with {previous['verdict']} "
                f"-- stage {stage} does not run")
    return previous


def _saved(out_dir, arm, name, kind, window, cells, build_fn) -> list:
    """Rows from the rows file, building (and saving) them when absent."""
    path = rows_path(out_dir, arm, name)
    if not path.exists():
        _write(path, build_fn(kind, arm, window, cells), indent=None)
    return _load(path)


def _train_rows(out_dir, arm, build_fn) -> list:
    return _saved(out_dir, arm, "train", "rows", funnel.FOLD_TRAIN, abr.K_STEPS, build_fn)


def _stage_m1(out_dir, arm, build_fn, n_resamples) -> dict:
    rows = _saved(out_dir, arm, "census-train", "census", funnel.FOLD_TRAIN, abr.K_STEPS,
                  build_fn)
    return funnel.stage_minus1(rows, arm)


def _stage0(out_dir, arm, build_fn, n_resamples) -> dict:
    cells = _previous(out_dir, arm, 0)["reachable_cells"]
    return funnel.stage0(_train_rows(out_dir, arm, build_fn), arm, cells=cells)


def _stage1(out_dir, arm, build_fn, n_resamples) -> dict:
    cells = _previous(out_dir, arm, 1)["powered_cells"]
    rows = _train_rows(out_dir, arm, build_fn)
    out = funnel.stage1(rows, arm, cells=cells, n_resamples=n_resamples)
    out["reports"] = [funnel.report(rows, arm, abr.cell_key(k), n_resamples=n_resamples)
                      for k in abr.K_STEPS]
    return out


def _fold_rows(out_dir, arm, k, build_fn) -> dict:
    """Folds inside fold-train come from the train rows; the 2023 fold is
    replayed for the selected k only."""
    train = _train_rows(out_dir, arm, build_fn)
    last_train_year = int(funnel.FOLD_TRAIN[1][:4])
    by_year = {year: [r for r in train if r["entry_date"][:4] == str(year)]
               for year in funnel.FOLD_YEARS if year <= last_train_year}
    by_year[int(funnel.FOLD_2023[0][:4])] = _saved(out_dir, arm, "fold2023", "rows",
                                                   funnel.FOLD_2023, [k], build_fn)
    return by_year


def _stage2(out_dir, arm, build_fn, n_resamples) -> dict:
    selected = _previous(out_dir, arm, 2)["selected"]
    return funnel.stage2(_fold_rows(out_dir, arm, selected["k"], build_fn), arm,
                         selected["cell"])


def _stage3(out_dir, arm, build_fn, n_resamples) -> dict:
    _previous(out_dir, arm, 3)
    selected = _load(stage_path(out_dir, arm, 1))["selected"]
    rows = _saved(out_dir, arm, "validation", "rows", funnel.VALIDATION, [selected["k"]],
                  build_fn)
    out = funnel.stage3(rows, arm, selected["cell"], n_resamples=n_resamples)
    out["report"] = funnel.report(rows, arm, selected["cell"], n_resamples=n_resamples)
    return out


_STAGES = {-1: _stage_m1, 0: _stage0, 1: _stage1, 2: _stage2, 3: _stage3}


def run_stage(arm, stage, out_dir, *, build, n_resamples: int = BOOTSTRAP_RESAMPLES) -> dict:
    """Run one stage for one arm and write its verdict JSON. Stages -1..2 are
    fold-train and deterministic, so they may be re-run; stage 3 may not."""
    out_dir = Path(out_dir)
    target = stage_path(out_dir, arm, stage)
    if stage == 3 and target.exists():
        _refuse(f"{target.name} exists -- arm {arm}'s one VALIDATION shot is spent")
    out = _STAGES[stage](out_dir, arm, build, n_resamples)
    out.update({"instrument": funnel.INSTRUMENT, "data_source": funnel.DATA_SOURCE})
    _write(target, out)
    return out


# --- the family ----------------------------------------------------------------

def _closed(out_dir, arm) -> bool:
    """Closed once Stage 3 ran, or once any stage carries a non-advancing verdict."""
    if stage_path(out_dir, arm, 3).exists():
        return True
    paths = [stage_path(out_dir, arm, stage) for stage in (-1, 0, 1, 2)]
    return any(path.exists() and _load(path)["verdict"] not in ADVANCING for path in paths)


def _stage3_or_none(out_dir, arm):
    path = stage_path(out_dir, arm, 3)
    return _load(path) if path.exists() else None


def run_family(out_dir) -> dict:
    """Holm across both arms, once both are closed; an arm closed before
    Stage 3 enters as p = 1.0 (atr_band_funnel.holm_family)."""
    out_dir = Path(out_dir)
    open_arms = [arm for arm in funnel.FAMILY if not _closed(out_dir, arm)]
    if open_arms:
        _refuse(f"arm(s) {', '.join(open_arms)} still open -- the family runs once both "
                "arms are closed")
    out = funnel.holm_family({arm: _stage3_or_none(out_dir, arm) for arm in funnel.FAMILY})
    _write(family_path(out_dir), out)
    return out


# --- CLI ---------------------------------------------------------------------

def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    which = parser.add_mutually_exclusive_group(required=True)
    which.add_argument("--stage", type=int, choices=sorted(_STAGES))
    which.add_argument("--family", action="store_true")
    parser.add_argument("--arm", choices=sorted(abr.ARMS), default=None)
    parser.add_argument("--out-dir", type=Path, default=RESULTS)
    parser.add_argument("--preregistration", type=Path, default=None)
    parser.add_argument("--tickers", type=int, default=None)
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--resamples", type=int, default=BOOTSTRAP_RESAMPLES)
    parser.add_argument("--data-source", choices=(funnel.DATA_SOURCE,), default=funnel.DATA_SOURCE)
    instrument_cli.add_instrument_arg(parser)
    return parser


def _preregistered(path) -> bool:
    return path is not None and path.is_file() and path.name == PREREGISTRATION.name


def _cli_refusal(args) -> str | None:
    if args.family:
        return None if args.arm is None else \
            "refused:family-takes-no-arm -- --family reads both arms' Stage 3 files"
    if args.arm is None:
        return "refused:no-arm -- a stage runs for one arm: --arm K or --arm R"
    if args.tickers is not None and args.stage == 3:
        return ("refused:partial-validation -- stage 3 is the one shot and runs "
                "the full universe; drop --tickers")
    if args.tickers is not None and args.out_dir.resolve() == RESULTS.resolve():
        return ("refused:smoke-run -- --tickers needs a scratch --out-dir, never "
                "the committed results directory")
    if args.stage == 3 and not _preregistered(args.preregistration):
        return (f"refused:no-preregistration -- stage 3 needs --preregistration "
                f"<committed {PREREGISTRATION.name}>. This is the one shot.")
    return None


def main(argv=None) -> int:
    args = _parser().parse_args(argv)
    instrument_cli.require_v1(instrument_cli.spec_from_args(args), "measure_atr_band_stop.py",
                              "a later plan")
    refusal = _cli_refusal(args)
    if refusal:
        print(refusal, file=sys.stderr)
        return 1
    if args.family:
        out = run_family(args.out_dir)
        print(f"v191 family: passed {out['passed'] or 'none'} -> {family_path(args.out_dir)}",
              flush=True)
        return 0
    build_fn = functools.partial(build, tickers=args.tickers, workers=args.workers)
    out = run_stage(args.arm, args.stage, args.out_dir, build=build_fn,
                    n_resamples=args.resamples)
    print(f"arm {args.arm} stage {args.stage}: {out['verdict']} -> "
          f"{stage_path(args.out_dir, args.arm, args.stage)}", flush=True)
    return 0 if out["verdict"] in ADVANCING else 1


if __name__ == "__main__":
    sys.exit(main())
