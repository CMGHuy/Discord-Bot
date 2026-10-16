#!/usr/bin/env python3
"""v161: the live-book autopsy -- two read-only VM exports in, a JSON and a Markdown report out.

    python scripts/reports/book_autopsy.py <rows.csv> <rejections.csv> [--bars-dir DIR]
        [--out-dir docs/superpowers/results] [--date YYYY-MM-DD] [--resamples N]
        [--seed N] [--balance USD]

The CSVs come from scripts/ops/export_book_rows.sh (rows / rejections mode) and
stay in the scratchpad. Writes <out-dir>/<date>-book-autopsy.json and .md.
Deterministic for one seed; no model, no network: bars come only from --bars-dir."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "scripts" / "reports")]

from autopsy.report import DEFAULT_BALANCE, build_report, render_markdown  # noqa: E402
from autopsy.rows import friction_settings, load_rejections, load_rows  # noqa: E402
from swingbot.core.backtesting.instrument.stats import (  # noqa: E402
    WEEK_BOOTSTRAP_RESAMPLES, WEEK_BOOTSTRAP_SEED)

RESULTS_DIR = ROOT / "docs" / "superpowers" / "results"


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="v161 live-book autopsy")
    p.add_argument("rows", type=Path, help="rows-mode export CSV")
    p.add_argument("rejections", type=Path, help="rejections-mode export CSV")
    p.add_argument("--bars-dir", type=Path, default=None,
                   help="daily-bar CSVs named like backtest_cache.cache_path (scratch dir)")
    p.add_argument("--out-dir", type=Path, default=RESULTS_DIR)
    p.add_argument("--date", default=date.today().isoformat())
    p.add_argument("--resamples", type=int, default=WEEK_BOOTSTRAP_RESAMPLES)
    p.add_argument("--seed", type=int, default=WEEK_BOOTSTRAP_SEED)
    p.add_argument("--balance", type=float, default=DEFAULT_BALANCE,
                   help="account balance the stop cells' 2%% dollar view is priced at")
    return p


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    args = _parser().parse_args(argv)
    frictions = friction_settings()
    inputs = {}
    loaded = load_rows(args.rows, frictions=frictions, input_fingerprints=inputs)
    rejections = load_rejections(args.rejections, input_fingerprints=inputs)
    invocation = {"command": [sys.executable, str(Path(__file__).resolve()), *argv],
                  "options": {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()}}
    report = build_report(loaded, rejections,
                          bars_dir=args.bars_dir, n_resamples=args.resamples,
                          seed=args.seed, balance=args.balance, frictions=frictions,
                          input_fingerprints=inputs, invocation=invocation)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.out_dir / f"{args.date}-book-autopsy.json"
    md_path = args.out_dir / f"{args.date}-book-autopsy.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    h = report["header"]
    print(f"wrote {json_path}\nwrote {md_path}")
    print(f"N {h['n']}, bar-covered {h['bar_covered_n']}, cells tested {h['cells_tested']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
