#!/usr/bin/env python3
"""v232: live versus replay reconciliation, per direction.

    python scripts/reports/live_replay_reconcile.py --export data/v232/reconcile.jsonl \
        --since 2026-07-01 [--until D] [--fetch-bars] [--short-modes broad,isolated|none]

Checkpoints under --work-dir; the same command resumes. Exit 2: self-check or leak guard.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "scripts" / "reports")]

from autopsy.rows import friction_settings  # noqa: E402
from reconcile import (WORK_DIR, layer1_run, layer2, layer2_run, raw_bars,  # noqa: E402
                       records, render, table)
from reconcile.checkpoint import JsonlCheckpoint  # noqa: E402
from swingbot.core.backtesting.instrument.stats import (  # noqa: E402
    WEEK_BOOTSTRAP_RESAMPLES, WEEK_BOOTSTRAP_SEED)
from swingbot.scan_params import ScanParams  # noqa: E402

STEM = "v232-live-replay-reconciliation"
SHORT_MODES = ("broad", "isolated")


class RunRefused(RuntimeError):
    """The run would not be reproducible or would leak; nothing is written."""


def _modes(text: str) -> frozenset:
    if text == "none":
        return frozenset()
    modes = frozenset(m.strip() for m in text.split(",") if m.strip())
    if not modes or not modes <= set(SHORT_MODES):
        raise argparse.ArgumentTypeError(f"--short-modes {text!r}: use broad, isolated or none")
    return modes


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="v232 live versus replay reconciliation")
    p.add_argument("--export", type=Path, required=True, help="reconcile-mode JSONL (scratch)")
    p.add_argument("--since", type=dt.date.fromisoformat, required=True)
    p.add_argument("--until", type=dt.date.fromisoformat, default=None)
    p.add_argument("--bars-root", type=Path, default=ROOT / WORK_DIR / "bars")
    p.add_argument("--work-dir", type=Path, default=ROOT / WORK_DIR)
    p.add_argument("--fetch-bars", action="store_true", help="fetch raw bars first (resumes)")
    p.add_argument("--date", default=dt.date.today().isoformat())
    p.add_argument("--results-dir", type=Path, default=ROOT / "docs" / "superpowers" / "results")
    p.add_argument("--resamples", type=int, default=WEEK_BOOTSTRAP_RESAMPLES)
    p.add_argument("--seed", type=int, default=WEEK_BOOTSTRAP_SEED)
    p.add_argument("--short-modes", type=_modes, default=None, help="default: live configuration")
    return p


def make_provider():
    """Alpaca from .env through swingbot.config; the keys are never printed."""
    from swingbot import config
    from swingbot.core.marketdata.providers.alpaca_provider import AlpacaProvider
    return AlpacaProvider(config.ALPACA_API_KEY_ID, config.ALPACA_API_SECRET_KEY,
                          config.ALPACA_DATA_FEED_LIVE)


def _sha256(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def _commit() -> str | None:
    try:
        done = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                              text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return done.stdout.strip()


def _layer1(export, args) -> list:
    checkpoint = JsonlCheckpoint(args.work_dir / "trade-rows.jsonl")

    def bars(ticker: str):
        return (raw_bars.load_bars(ticker, args.bars_root, "raw"),
                raw_bars.load_bars(ticker, args.bars_root, "split"))

    layer1_run.run_layer1(export, bars, checkpoint, frictions=friction_settings(),
                          start=args.since)
    by_plan = {d["plan_id"]: layer1_run.TradeRow.from_dict(d) for d in checkpoint.rows()}
    return [by_plan[rec.plan_id] for rec in export.records if rec.plan_id in by_plan]


def _layer2(export, rows, window, params, modes, lane_dir: Path) -> tuple[dict, dict]:
    base = layer2_run.replay_tickers(export)
    frames, missing = layer2_run.load_frames(
        tuple(dict.fromkeys(base + layer2_run.reference_symbols(modes))))
    signals = layer2_run.run_layer2(frames, window, params, base_tickers=base, modes=modes,
                                    checkpoint_dir=lane_dir)
    cov = layer2_run.coverage(frames, window, base_tickers=base, modes=modes,
                              snapshot_fn=layer2_run.SNAPSHOT_FN)
    cov["store_missing"] = sorted(missing)
    plans = layer2.live_plans(export, {r.plan_id: r for r in rows})
    return layer2.selection_counts(layer2.match(signals, plans), export), cov


def _meta(args, argv, window, digest, modes, inputs, cov) -> dict:
    lanes = sorted((args.work_dir / "layer2").glob("lane-*.jsonl"))
    return {"commit": _commit(), "window": list(window), "params_digest": digest,
            "short_modes": sorted(modes),
            "inputs": {Path(k).name: v for k, v in inputs.items()},
            "rows_sha256": _sha256(args.work_dir / "trade-rows.jsonl"),
            "lanes_sha256": {p.name: _sha256(p) for p in lanes},
            "bars": raw_bars.bars_manifest(args.bars_root), "coverage": cov,
            "n_resamples": args.resamples, "seed": args.seed,
            "invocation": {"argv": list(argv),
                           "options": {k: str(v) for k, v in vars(args).items()}}}


def _write(args, report: dict, markdown: str) -> None:
    args.results_dir.mkdir(parents=True, exist_ok=True)
    stem = args.results_dir / f"{args.date}-{STEM}"
    outputs = ((Path(f"{stem}.json"), json.dumps(report, indent=2, allow_nan=False) + "\n"),
               (Path(f"{stem}.md"), markdown))
    for path, text in outputs:
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        print(f"wrote {path}")


def _run(args, argv) -> int:
    params = ScanParams.from_config()
    digest = layer2_run.params_digest(params)
    end = args.until or dt.date.today()
    window = (args.since.isoformat(), end.isoformat())
    inputs: dict = {}
    export = records.load_export(args.export, input_fingerprints=inputs, until=args.until)
    if args.fetch_bars:
        raw_bars.fetch_bars(sorted({r.ticker for r in export.records}), args.since, end,
                            args.bars_root, provider=make_provider())
    rows = _layer1(export, args)
    modes = layer2_run.live_short_modes() if args.short_modes is None else args.short_modes
    selection, cov = _layer2(export, rows, window, params, modes, args.work_dir / "layer2")
    report = render.build_report(rows, selection, export,
                                 meta=_meta(args, argv, window, digest, modes, inputs, cov),
                                 n_resamples=args.resamples, seed=args.seed)
    markdown = render.render_markdown(report)
    problems = render.leaks(report, markdown)
    if problems:
        raise RunRefused("leak guard: " + "; ".join(problems))
    _write(args, report, markdown)
    return 0


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    args = _parser().parse_args(argv)
    try:
        return _run(args, argv)
    except (RunRefused, table.ReconcileError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
