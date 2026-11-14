#!/usr/bin/env python3
"""Expectancy attribution (v146): does confidence predict R?

Thin wrapper: parse the arguments, call the study module, print a summary.
Reads the closed trades from the database ``DATABASE_URL`` names and the
TRAIN confluence-replay rows from --train-jsonl; writes the latest report to
data/reports/expectancy-attribution.json unless --no-write is given.

Run: python scripts/reports/expectancy_attribution.py \
         --train-jsonl data/reports/v146-train-scenarios.jsonl

v226: --study stop-width runs the stop-width study instead (its own report,
data/reports/stop-width-attribution.json, and its Markdown on stdout); the
default report and the v146 verdict of record are never touched by it.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


def _population_line(name: str, population: dict | None) -> str:
    if not population:
        return f"  {name:<5} no rows"
    mono = population["monotonicity"]
    return (f"  {name:<5} n={population['n']} scored={mono['n']} "
            f"terciles={mono['tercile_n']} spread={mono['tercile_spread']} "
            f"ci=[{mono['ci_low']}, {mono['ci_high']}] rho={mono['spearman_rho']} "
            f"inverted={mono['inverted']}")


def summary(report: dict) -> str:
    record = report["verdict_of_record"]
    lines = [
        "Expectancy attribution",
        f"  verdict of record: {record['verdict']} ({record['date']}, n={record['n']})",
        f"  this run: {report['verdict']} | looks={report['looks']} | seed={report['seed']}",
    ]
    lines += [_population_line(name, report["populations"].get(name))
              for name in ("live", "train")]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--train-jsonl", required=True,
                        help="rows written by run_backtest_range.py --scenarios --train --trades-jsonl")
    parser.add_argument("--seed", type=int, default=None,
                        help="bootstrap seed (default: the instrument's WEEK_BOOTSTRAP_SEED)")
    parser.add_argument("--no-write", action="store_true",
                        help="do not replace data/reports/expectancy-attribution.json "
                             "(with --study stop-width: stop-width-attribution.json)")
    parser.add_argument("--study", choices=("stop-width",), default=None,
                        help="v226: run the stop-width study and print its Markdown "
                             "instead of the v146 report")
    args = parser.parse_args(argv)

    from swingbot.core.analytics import expectancy_attribution as study
    seed = study.WEEK_BOOTSTRAP_SEED if args.seed is None else args.seed
    if args.study == "stop-width":
        report = study.run_stop_width(args.train_jsonl, seed=seed, write=not args.no_write)
        # The Markdown carries non-ASCII (">="); a Windows cp1252 console would crash
        # here after the report was already written, so emit UTF-8 explicitly.
        sys.stdout.reconfigure(encoding="utf-8")
        print(study.stop_width_markdown(report), end="")
        return 0
    report = study.run(args.train_jsonl, seed=seed, write=not args.no_write)
    print(summary(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
