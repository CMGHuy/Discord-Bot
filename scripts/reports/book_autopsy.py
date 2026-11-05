#!/usr/bin/env python3
"""v161: the live-book autopsy -- two read-only VM exports in, a JSON and a Markdown report out.

    python scripts/reports/book_autopsy.py <rows.csv> <rejections.csv> [--bars-dir DIR]
        [--out-dir docs/superpowers/results] [--date YYYY-MM-DD] [--resamples N]
        [--seed N] [--balance USD]
        [--entry-type market|stop_entry|limit]

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

from autopsy.exclusions import EXCLUSIONS_PATH  # noqa: E402
from autopsy.report import DEFAULT_BALANCE, build_report, render_markdown  # noqa: E402
from autopsy.rows import friction_settings, load_rejections, load_rows  # noqa: E402
from swingbot.core.backtesting.instrument.stats import (  # noqa: E402
    WEEK_BOOTSTRAP_RESAMPLES, WEEK_BOOTSTRAP_SEED)

RESULTS_DIR = ROOT / "docs" / "superpowers" / "results"

#: Entry families carried by trade and plan rows.
ENTRY_TYPES = ("market", "stop_entry", "limit")


def filter_entry_type(rows, entry_type: str | None) -> list:
    """Keep one entry family's trade and plan rows; None keeps every row."""
    rows = list(rows)
    return rows if entry_type is None else [row for row in rows if row.entry_type == entry_type]


def _output_stem(day: str, entry_type: str | None) -> str:
    return f"{day}-book-autopsy" if entry_type is None else f"{day}-book-autopsy-{entry_type}"


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
    p.add_argument("--entry-type", choices=ENTRY_TYPES, default=None,
                   help="keep one entry family's rows; outputs are named <date>-book-autopsy-<type>")
    p.add_argument("--exclusions", type=Path, default=EXCLUSIONS_PATH,
                   help="committed trade-id exclusion file (the August 2026 stall)")
    p.add_argument("--no-exclusions", action="store_true", help="apply no exclusion")
    return p


def _record_filter(report: dict, entry_type: str | None) -> None:
    if entry_type is None:
        return
    report["header"]["entry_type_filter"] = entry_type
    report["header"]["notes"].append(f"entry-type filter: {entry_type} rows only (v192 disclosure); "
                                     "rejection tallies carry no entry type and are unfiltered")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    args = _parser().parse_args(argv)
    frictions = friction_settings()
    inputs = {}
    loaded = filter_entry_type(load_rows(args.rows, frictions=frictions, input_fingerprints=inputs),
                               args.entry_type)
    rejections = load_rejections(args.rejections, input_fingerprints=inputs)
    invocation = {"command": [sys.executable, str(Path(__file__).resolve()), *argv],
                  "options": {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()}}
    report = build_report(loaded, rejections,
                          bars_dir=args.bars_dir, n_resamples=args.resamples,
                          seed=args.seed, balance=args.balance, frictions=frictions,
                          input_fingerprints=inputs, invocation=invocation,
                          exclusions_path=None if args.no_exclusions else args.exclusions)
    _record_filter(report, args.entry_type)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    stem = _output_stem(args.date, args.entry_type)
    json_path = args.out_dir / f"{stem}.json"
    md_path = args.out_dir / f"{stem}.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    h = report["header"]
    print(f"wrote {json_path}\nwrote {md_path}")
    print(f"N {h['n']}, bar-covered {h['bar_covered_n']}, cells tested {h['cells_tested']}")
    for stall in h["stall_exclusions"]:
        print(f"stall exclusion {stall['key']}: N {stall['n']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
