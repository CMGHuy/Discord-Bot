#!/usr/bin/env python3
"""v229 deferred-entry counterfactual: do late-session entries beat early ones?

Spec: docs/superpowers/specs/2026-11-14-v229-deferred-entry-counterfactual-design.md

Modes:
  append       log every eligible LONG plan not yet in the pair log; one count line (weekly cron)
  exploratory  append, then the one exploratory read (plans opened before T0): calibration, no verdict
  verdict      append, then the forward verdict, once, on or after verdict_open_date(T0)

On the VM (bot container, cwd /app; the host writes the export first):
  docker compose exec -T bot python scripts/reports/deferred_entry_counterfactual.py \
      --mode append --rows /app/data/v229/rows.csv --t0 <T0>
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _path in (str(ROOT), str(HERE)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from deferred_entry import arms, bars, pairlog, verdict  # noqa: E402
from deferred_entry import pairs as pairs_mod  # noqa: E402
from swingbot.core.backtesting.instrument import stats  # noqa: E402

EARNINGS_LOOKUP = None          # None = the production earnings lookup inside build_pair
MODES: dict = {}                # V229-10b: "exploratory" and "verdict" handlers


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mode", required=True, choices=("append", *MODES))
    parser.add_argument("--rows", required=True, help="export_book_rows.sh rows CSV")
    parser.add_argument("--bars-dir", default="market_data/5min")
    parser.add_argument("--pairs-log", default=pairlog.DEFAULT_LOG)
    parser.add_argument("--t0", required=True, help="freeze commit timestamp, ISO with offset")
    parser.add_argument("--out-dir", default="data/v229")
    parser.add_argument("--ledger", default=str(stats.LEDGER_PATH))
    parser.add_argument("--today", type=dt.date.fromisoformat, default=None)
    parser.add_argument("--git-sha", default=None)
    return parser


def resolve_git_sha(given: str | None) -> str:
    if given:
        return given
    if os.environ.get("V229_GIT_SHA"):
        return os.environ["V229_GIT_SHA"]
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=HERE, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return out.stdout.strip() or "unknown"


def row_phase(row: dict, t0) -> str | None:
    """The read an export row belongs to; None without a parseable opened_at (plan rows)."""
    try:
        return verdict.phase(bars.et_date(bars.to_utc(row.get("opened_at"))), t0)
    except ValueError:
        return None


def select(pairs, t0, phase: str) -> list[dict]:
    return [p for p in pairs if verdict.phase(dt.date.fromisoformat(p["entry_date"]), t0) == phase]


def classify_rows(rows, bars_dir, archive_end) -> list[tuple[dict, object, str]]:
    cache: dict[str, object] = {}
    out = []
    for row in rows:
        frame = None
        if row.get("row_kind") == "trade":
            ticker = row.get("ticker") or ""
            if ticker not in cache:
                cache[ticker] = bars.load_bars(bars_dir, ticker)
            frame = cache[ticker]
        out.append((row, frame, pairs_mod.classify(row, frame, archive_end=archive_end)))
    return out


def build_pair_for(row: dict, frame) -> dict:
    return pairs_mod.build_pair(row, frame, rule_hash=verdict.rule_hash(), earnings_lookup=EARNINGS_LOOKUP)


def append_new(scanned, log_path) -> tuple[int, dict]:
    logged = pairlog.read_pairs(log_path)
    known = set(logged)
    added = 0
    for row, frame, reason in scanned:
        if reason != "eligible" or row.get("direction") != "bullish" or row.get("trade_id") in known:
            continue
        pair = build_pair_for(row, frame)
        pairlog.append_pair(log_path, pair, known=known)
        logged[pair["trade_id"]] = pair
        added += 1
    return added, logged


def _run(args) -> int:
    arms.assert_frictions()
    t0 = bars.to_utc(args.t0)
    last = bars.archive_last_bar(args.bars_dir)
    scanned = classify_rows(pairs_mod.read_export(args.rows), args.bars_dir, bars.to_utc(last) if last else None)
    added, logged = append_new(scanned, args.pairs_log)
    if args.mode == "append":
        forward = len(select(logged.values(), t0, "forward"))
        print(f"v229 pairs: appended {added}, total {len(logged)}, forward {forward}")
        return 0
    run = {"t0": t0, "archive_last_bar": last, "git_sha": resolve_git_sha(args.git_sha),
           "today": args.today or dt.datetime.now(dt.timezone.utc).date()}
    return MODES[args.mode](args, scanned, logged, run)


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return _run(args)
    except (arms.FrictionsError, verdict.VerdictRefused, ValueError) as exc:  # ArchiveError, PairLogError: ValueError
        print(f"v229 refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
