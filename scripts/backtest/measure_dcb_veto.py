#!/usr/bin/env python3
"""v68 Task D8: TRAIN grid for the dead-cat-bounce veto -- twelve parameter
cells scored in ONE replay pass.

WHY ONE PASS, NOT TWELVE BACKTESTS: `chart_patterns.dead_cat_bounce` is a
pure function of the frame at the entry bar -- it does not change which
levels are found or which scenarios are geometrically valid, only which of
them survive. `tune_confluence_gates.py`'s docstring records a single grid
point alone running for HOURS even parallelized across 12 cores; twelve
cells run naively is days of compute, which is how a measurement never gets
made. Instead: run `replay_scenarios` ONCE per ticker/horizon with
`dcb_params=None` (the baseline, unvetoed population), and at each accepted
entry bar evaluate all twelve cells against the SAME no-lookahead window
already in hand, recording the twelve booleans alongside the trade's
outcome. Aggregating per cell afterwards is arithmetic over a table, not
twelve backtests -- and it is MORE rigorous than twelve separate runs: every
cell scores the identical trade population, so a delta is attributable to
the veto alone, never to run-to-run variation.

The veto only ever removes BULLISH scenarios (`build_scenarios`'s
`block_bullish`) -- bearish trades are unaffected by every cell, always. A
cell's "veto-on" population therefore keeps every bearish row and drops a
bullish row iff that cell's `detected` verdict at the entry bar was True.

NO-LOOKAHEAD: the window handed to `dead_cat_bounce` at each entry bar is
`df.iloc[:i+1]` -- the exact same slice `replay_scenarios` itself used to
accept the trade (chart_patterns.py's own module docstring proves this
holds for the detector itself; this script adds no further lookahead by
construction, since it re-slices from the same `i`).

Prints one flushed line per ticker (CLAUDE.md).

Run:
  python scripts/backtest/measure_dcb_veto.py --tickers AAPL,MSFT --horizons 4w --dry-run
  python scripts/backtest/measure_dcb_veto.py --train \
      --cache-dir <main checkout>/data/backtest_cache
  python scripts/backtest/measure_dcb_veto.py --validation --cell d20_gN_voff \
      --cache-dir <main checkout>/data/backtest_cache
"""
import argparse
import json
import math
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from swingbot.core.backtesting.backtest_scenarios import replay_scenarios  # noqa: E402
from swingbot.core.market.chart_patterns import dead_cat_bounce  # noqa: E402
from swingbot.core.market.strategy_types import HORIZONS  # noqa: E402
from swingbot.core.planning.plan_engine import simulate_exit  # noqa: E402

CACHE_DIR = ROOT / "data" / "backtest_cache"
OUT_TRAIN = ROOT / "data" / "v68_train_dcb.json"
OUT_VALIDATION = ROOT / "data" / "v68_validation_dcb.json"
TRAIN = ("2020-01-01", "2023-12-31")
VALIDATION = ("2024-01-01", "2025-12-31")   # verbatim run_backtest_range.py
HORIZONS_TO_TEST = ["4w", "2m", "3m", "4m", "6m"]
SAMPLE_EVERY = 3   # deterministic alphabetical stride -- tune_confluence_gates.py precedent
BASE_GATES = {"min_reward_pct": 3.0, "min_stop_distance_pct": 2.0,
              "max_stop_distance_pct": 7.0, "cooldown_bars": 5,
              "min_confluence": 1, "min_risk_reward": 0.0}
VOLUME_BUDGET_PCT = 30.0
MIN_TRAIN_N = 30

#: The four fixed values are set from reasoning in the v68 spec and are NOT
#: grid dimensions -- widening the grid to include them is a different
#: pre-registration. The three grid dimensions carry their permissive default.
GRID = [
    {"decline_pct": d, "gap_required": g, "volume_ratio": v}
    for d in (15.0, 20.0, 25.0)
    for g in (False, True)
    for v in (None, 0.8)
]   # 3 x 2 x 2 = 12

RULE = ("select the cell with the greatest pooled ExpR improvement over the "
        "veto-off baseline, among cells with N>=30 surviving trades AND an "
        "alert-volume cut <=30%. If no cell satisfies both, no cell is "
        "selected and VALIDATION is NOT spent.")


def cell_id(cell: dict) -> str:
    v = "off" if cell["volume_ratio"] is None else f"{cell['volume_ratio']:.1f}".replace(".", "")
    return f"d{cell['decline_pct']:.0f}_g{'Y' if cell['gap_required'] else 'N'}_v{v}"


CELL_IDS = [cell_id(c) for c in GRID]
CELLS_BY_ID = dict(zip(CELL_IDS, GRID))


def wilson_interval(wins: int, n: int, z: float = 1.96) -> tuple:
    if n <= 0:
        return (0.0, 0.0)
    p = wins / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def load_frames(cache_dir: Path, watchlist_path: Path, tickers: list | None,
                sample_every: int) -> dict:
    watchlist = json.loads(watchlist_path.read_text())
    if tickers:
        symbols = [t for t in tickers if t in watchlist] or tickers
    else:
        symbols = sorted(watchlist)[::sample_every]
    frames = {}
    for sym in symbols:
        p = cache_dir / f"{sym}.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p, index_col="Date", parse_dates=True)
        if len(df):
            frames[sym] = df
    return frames


def _ticker_worker(args) -> tuple:
    """One ticker, all horizons -- the process-pool entry point, so it must
    be module-level and take a single picklable argument. Same per-ticker
    grouping rationale as backtest_scenarios._replay_ticker: the OHLCV frame
    is the expensive thing to move across a process boundary, so one task
    per ticker (not per ticker/horizon pair) minimizes IPC."""
    ticker, df, horizons, window = args
    rows = []
    for hk in horizons:
        for i, plan in replay_scenarios(ticker, df, hk, gates=BASE_GATES,
                                        dcb_params=None):
            signal_date = str(df.index[i].date())
            if not (window[0] <= signal_date <= window[1]):
                continue
            entry_window = df.iloc[:i + 1]
            result = simulate_exit(df, i, plan, scale_out=True)
            row = {"ticker": ticker, "horizon": hk, "entry_index": i,
                   "direction": plan.direction, "outcome": result.outcome,
                   "r_multiple": result.r_total}
            for cid, cell in zip(CELL_IDS, GRID):
                row[cid] = bool(dead_cat_bounce(entry_window, cell)["detected"])
            rows.append(row)
    return ticker, rows


def collect(frames: dict, horizons: list, window: tuple, workers: int | None = None) -> list:
    """One row per accepted (unvetoed) trade inside `window`, carrying the
    outcome plus every grid cell's veto verdict at the entry bar.

    Parallelized across a process pool -- a wall-clock optimization only
    (same math as the serial per-ticker loop), following
    tune_confluence_gates.py's precedent: this replay is CPU-bound over the
    full watchlist x 5 horizons x ~1900 bars, and that script's docstring
    records a single such pass running for HOURS even on 12 cores."""
    tasks = [(ticker, df, horizons, window) for ticker, df in frames.items()]
    rows = []
    if workers == 1 or len(tasks) <= 1:
        results = [_ticker_worker(t) for t in tasks]
    else:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            results = pool.map(_ticker_worker, tasks)
    for ticker, ticker_rows in results:
        print(f"{ticker}: {len(ticker_rows)} entry-bar samples", flush=True)
        rows.extend(ticker_rows)
    return rows


def _aggregate(rows: list) -> dict:
    closed = [r for r in rows if r["outcome"] != "not_triggered"]
    ev = [r for r in closed if r["outcome"] in ("win", "loss")]
    wins = [r for r in ev if r["outcome"] == "win"]
    rs = [r["r_multiple"] for r in closed]
    excl = sum(1 for r in closed if r["outcome"] in ("scratch", "timeout"))
    lo, hi = wilson_interval(len(wins), len(ev))
    return {
        "alerts": len(rows),
        "n": len(ev),
        "wins": len(wins),
        "win_rate": len(wins) / len(ev) * 100 if ev else None,
        "wilson": [lo * 100, hi * 100],
        "expectancy_r": float(np.mean(rs)) if rs else None,
        "scratches": sum(1 for r in closed if r["outcome"] == "scratch"),
        "timeouts": sum(1 for r in closed if r["outcome"] == "timeout"),
        "excl_pct": excl / len(closed) * 100 if closed else 0.0,
        "not_triggered": sum(1 for r in rows if r["outcome"] == "not_triggered"),
    }


def veto_on_rows(rows: list, cid: str) -> list:
    """Bearish rows always survive -- the veto only blocks bullish scenarios
    (`build_scenarios`'s `block_bullish`)."""
    return [r for r in rows if not (r["direction"] == "bullish" and r[cid])]


def score_cell(rows: list, baseline: dict, cid: str) -> dict:
    kept = veto_on_rows(rows, cid)
    after = _aggregate(kept)
    dropped = baseline["alerts"] - after["alerts"]
    return {
        "cell": CELLS_BY_ID[cid], "after": after,
        "alert_cut_pct": dropped / baseline["alerts"] * 100 if baseline["alerts"] else 0.0,
        "expectancy_delta": (after["expectancy_r"] - baseline["expectancy_r"]
                             if after["expectancy_r"] is not None and
                             baseline["expectancy_r"] is not None else None),
    }


def _fmt(b: dict) -> str:
    wr = f"{b['win_rate']:5.1f}" if b["win_rate"] is not None else "  n/a"
    er = f"{b['expectancy_r']:+.3f}" if b["expectancy_r"] is not None else " n/a "
    return f"N={b['n']:>5} WR={wr}% [{b['wilson'][0]:4.1f},{b['wilson'][1]:4.1f}] ExpR={er}"


def print_train_table(baseline: dict, scored: dict) -> None:
    print(f"\nBASELINE (veto off): {_fmt(baseline)} alerts={baseline['alerts']} "
          f"excl={baseline['excl_pct']:.1f}%\n")
    print(f"RULE: {RULE}\n")
    print(f"{'cell':<16} {'N':>5} {'WR':>7} {'ExpR':>8} {'dExpR':>8} "
          f"{'cut%':>7} {'excl%':>6}  qualifies")
    for cid in CELL_IDS:
        s = scored[cid]
        after = s["after"]
        ok = (after["n"] >= MIN_TRAIN_N and s["alert_cut_pct"] <= VOLUME_BUDGET_PCT)
        wr = f"{after['win_rate']:.1f}" if after["win_rate"] is not None else "n/a"
        er = f"{after['expectancy_r']:+.3f}" if after["expectancy_r"] is not None else "n/a"
        de = f"{s['expectancy_delta']:+.3f}" if s["expectancy_delta"] is not None else "n/a"
        print(f"{cid:<16} {after['n']:>5} {wr:>7} {er:>8} {de:>8} "
              f"{s['alert_cut_pct']:>6.1f}% {after['excl_pct']:>5.1f}%  "
              f"{'PASS' if ok else ('fail(N<30)' if after['n'] < MIN_TRAIN_N else 'fail(cut>30%)')}",
              flush=True)


def select_cell(scored: dict) -> tuple:
    qualifying = [cid for cid in CELL_IDS
                 if scored[cid]["after"]["n"] >= MIN_TRAIN_N
                 and scored[cid]["alert_cut_pct"] <= VOLUME_BUDGET_PCT]
    if not qualifying:
        return None, "no cell cleared N>=30 AND alert-cut<=30% -- VALIDATION not spent"
    best = max(qualifying, key=lambda cid: scored[cid]["expectancy_delta"] or -999)
    if (scored[best]["expectancy_delta"] or 0) <= 0:
        return None, "best qualifying cell did not improve pooled ExpR -- VALIDATION not spent"
    return best, "selected"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--train", action="store_true", help="the TRAIN window (default)")
    ap.add_argument("--validation", action="store_true",
                    help="the VALIDATION window -- D9's ONE pre-registered shot only")
    ap.add_argument("--cell", default=None,
                    help="required with --validation: the exact cell id D8 selected "
                         "(e.g. d20_gN_voff)")
    ap.add_argument("--tickers", default=None,
                    help="comma-separated symbols, overrides the SAMPLE_EVERY sample "
                         "(smoke test)")
    ap.add_argument("--horizons", default=None,
                    help="comma-separated horizon keys, overrides HORIZONS_TO_TEST "
                         "(smoke test)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the table but do not write the JSON output")
    ap.add_argument("--cache-dir", default=None,
                    help="OHLCV CSV cache. Defaults to <repo>/data/backtest_cache, "
                         "which is EMPTY inside a git worktree -- point this at the "
                         "main checkout's cache when running from one.")
    ap.add_argument("--json", default=None, help="override the output JSON path")
    ap.add_argument("--workers", type=int, default=None,
                    help="process-pool size for the replay pass (default: "
                         "ProcessPoolExecutor's own CPU-count default). "
                         "--workers 1 forces the serial path.")
    args = ap.parse_args()

    if args.validation and not args.cell:
        print("--validation requires --cell <id>", file=sys.stderr)
        return 1

    window = VALIDATION if args.validation else TRAIN
    label = "VALIDATION" if args.validation else "TRAIN"
    cache_dir = Path(args.cache_dir) if args.cache_dir else CACHE_DIR
    watchlist_path = cache_dir.parent / "watchlist.json"
    if not watchlist_path.exists():
        watchlist_path = ROOT / "data" / "watchlist.json"

    tickers = [t.strip() for t in args.tickers.split(",")] if args.tickers else None
    horizons = [h.strip() for h in args.horizons.split(",")] if args.horizons else HORIZONS_TO_TEST
    sample_every = 1 if tickers else SAMPLE_EVERY

    frames = load_frames(cache_dir, watchlist_path, tickers, sample_every)
    if not frames:
        print(f"No frames loaded from {cache_dir} (watchlist {watchlist_path}) -- "
              f"run scripts/data/fetch_backtest_data.py or pass --cache-dir.",
              file=sys.stderr)
        return 1
    print(f"Window: {label} {window[0]}..{window[1]} | {len(frames)} of "
          f"{len(json.loads(watchlist_path.read_text()))} tickers "
          f"(every {sample_every}{'th' if not tickers else ''}, alphabetical) "
          f"= {sorted(frames)}", flush=True)
    print(f"Horizons: {horizons} | gates: {BASE_GATES}", flush=True)

    workers = 1 if tickers else args.workers
    rows = collect(frames, horizons, window, workers=workers)
    print(f"\nTotal {label} accepted (unvetoed) trades: {len(rows)}", flush=True)
    baseline = _aggregate(rows)

    if args.validation:
        cell_ids = [args.cell]
        if args.cell not in CELLS_BY_ID:
            print(f"Unknown cell id {args.cell!r} -- must be one of {CELL_IDS}",
                  file=sys.stderr)
            return 1
    else:
        cell_ids = CELL_IDS

    scored = {cid: score_cell(rows, baseline, cid) for cid in cell_ids}

    if args.validation:
        s = scored[args.cell]["after"]
        excl_ok = s["excl_pct"] <= 50.0
        gates = {
            "expectancy_r > 0": (s["expectancy_r"] or 0) > 0,
            "win_rate >= 50": (s["win_rate"] or 0) >= 50,
            "N >= 15": s["n"] >= 15,
            "scratches+timeouts <= 50% of closed": excl_ok,
        }
        print(f"\nVALIDATION cell {args.cell} {CELLS_BY_ID[args.cell]}: "
              f"{_fmt(s)} excl={s['excl_pct']:.1f}%", flush=True)
        for name, ok in gates.items():
            print(f"  {'PASS' if ok else 'FAIL'}: {name}", flush=True)
        print(f"  -> {'ALL GATES PASS' if all(gates.values()) else 'AT LEAST ONE GATE FAILED'}",
              flush=True)
    else:
        print_train_table(baseline, scored)
        selected, reason = select_cell(scored)
        print(f"\nSelection: {selected or 'NONE'} ({reason})", flush=True)

    if not args.dry_run:
        out = args.json and Path(args.json) or (OUT_VALIDATION if args.validation else OUT_TRAIN)
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = {"window": {"label": label, "from": window[0], "to": window[1]},
                  "tickers": sorted(frames), "horizons": horizons,
                  "gates": BASE_GATES, "baseline": baseline,
                  "cells": {cid: {"params": scored[cid]["cell"],
                                  "after": scored[cid]["after"],
                                  "alert_cut_pct": scored[cid]["alert_cut_pct"],
                                  "expectancy_delta": scored[cid]["expectancy_delta"]}
                           for cid in cell_ids}}
        if not args.validation:
            payload["rule"] = RULE
            payload["selected"], payload["selection_reason"] = select_cell(scored)
        out.write_text(json.dumps(payload, indent=2))
        print(f"\nWrote {out}", flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
