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
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _path in (str(ROOT), str(HERE)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from deferred_entry import analysis, arms, bars, pairlog, report, verdict  # noqa: E402
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
    verdict.assert_same_frictions(list(logged.values()), arms.frictions_stamp())
    added = 0
    for row, frame, reason in scanned:
        if reason != "eligible" or row.get("direction") != "bullish" or row.get("trade_id") in known:
            continue
        pair = build_pair_for(row, frame)
        pairlog.append_pair(log_path, pair, known=known)
        logged[pair["trade_id"]] = pair
        added += 1
    return added, logged


OUTPUT_NAMES = {"exploratory": "exploratory", "verdict": "forward-verdict"}


def _context(scanned, t0, phase: str) -> dict:
    """Funnel, close-bucket context and bearish disclosure pairs for one read."""
    longs = [(row, reason) for row, _, reason in scanned if row.get("direction") == "bullish"]
    funnel = Counter(reason for row, reason in longs if row_phase(row, t0) in (phase, None))
    close_r = [float(row["r_realized"]) for row, reason in longs
               if reason == "close_bucket" and row_phase(row, t0) == phase and row.get("r_realized")]
    bearish = [build_pair_for(row, frame) for row, frame, reason in scanned
               if reason == "eligible" and row.get("direction") == "bearish" and row_phase(row, t0) == phase]
    return {"funnel": dict(funnel), "bearish": bearish,
            "close_bucket": {"n": len(close_r), "exp_r": sum(close_r) / len(close_r) if close_r else None}}


def _outputs(out_dir, mode: str) -> tuple[Path, Path]:
    stem = Path(out_dir) / OUTPUT_NAMES[mode]
    md, js = stem.with_suffix(".md"), stem.with_suffix(".json")
    if js.exists():
        raise verdict.VerdictRefused(f"{js} already exists: this read runs once")
    return md, js


def _write(paths: tuple[Path, Path], payload: dict) -> None:
    md, js = paths
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text(report.render_markdown(payload), encoding="utf-8")
    js.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def _payload(phase: str, sel: list[dict], ctx: dict, run: dict) -> dict:
    return report.build_payload(phase=phase, t0=run["t0"].isoformat(), pairs=sel, bearish=ctx["bearish"],
                                funnel=ctx["funnel"], close_bucket=ctx["close_bucket"],
                                archive_last_bar=run["archive_last_bar"], git_sha=run["git_sha"])


def run_exploratory(args, scanned, logged: dict, run: dict) -> int:
    paths = _outputs(args.out_dir, "exploratory")
    sel = select(logged.values(), run["t0"], "exploratory")
    if not sel:
        raise verdict.VerdictRefused("no exploratory pairs: check --rows, --bars-dir and --t0")
    verdict.assert_one_rule(sel)
    payload = _payload("exploratory", sel, _context(scanned, run["t0"], "exploratory"), run)
    payload["verdict"] = verdict.exploratory_close(payload["calibration"], len(sel))
    _write(paths, payload)
    cal = payload["calibration"]
    word = "CALIBRATED" if cal["calibrated"] else "UNCALIBRATED"
    print(f"v229 exploratory: n={len(sel)}, agreement {cal['agreement']}, {word}")
    return 0


def run_verdict(args, scanned, logged: dict, run: dict) -> int:
    paths = _outputs(args.out_dir, "verdict")
    verdict.guard(today=run["today"], t0=run["t0"], ledger_rows=stats.load_ledger(args.ledger),
                  pairs=list(logged.values()))
    sel = select(logged.values(), run["t0"], "forward")
    payload = _payload("forward", sel, _context(scanned, run["t0"], "forward"), run)
    payload["verdict"] = verdict.study_verdict(deltas=payload["deltas"], calibration=payload["calibration"],
                                               n_pairs=len(sel), weeks=analysis.week_count(sel))
    _write(paths, payload)
    ledger = payload["verdict"]["ledger"]
    print(f"v229 verdict: {payload['verdict']['study']} (ledger {ledger['verdict']}, n={ledger['n']}, "
          f"p={ledger['p']})")
    return 0


MODES.update(exploratory=run_exploratory, verdict=run_verdict)


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
