#!/usr/bin/env python3
"""Confluence scenario replay VALIDATION run (plan Task 41) -- SINGLE run over
the out-of-sample 2024-01-01..2025-12-31 window, using the Task-40-adopted
CONFLUENCE_GATES (swingbot.core.backtest_scenarios), never retuned after
seeing these results.

The literal plan command (`run_backtest_range.py --validation --scenarios`)
reproduces run_scenario_backtest's serial per-ticker loop, which Task 37's
own notes clock at ~27.5s per ticker per horizon -- full 75-ticker x
10-horizon coverage is hours, not minutes (an earlier uncommitted session
attempted exactly this and was abandoned mid-run; see git history around
2026-07-17). This script reproduces the SAME gates/window/scale_out replay
(same replay_scenarios + simulate_exit call shape tune_confluence_gates.py's
_ticker_worker uses) but:

  1. Resumes from per-ticker chunk files already on disk under
     CHUNK_DIR (docs/superpowers/results/_confluence_validation_chunks/),
     one JSON file per ticker shaped {horizon_key: [{"outcome","r_total"}, ...]}.
  2. Fans the REMAINING tickers only out across a ProcessPoolExecutor.
  3. Writes each new ticker's chunk file as it completes, so an interrupted
     run loses no completed work.
  4. Aggregates ALL chunk files (existing + new) into pooled + per-horizon
     stats using the same math as backtest_scenarios._aggregate /
     run_backtest_range.pool+passes (WR>=80, ExpR>0, N>=15, excl<=50%).

This is a one-shot execution script, not imported by swingbot/ or tests/.
"""
import json
import sys
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np

from fetch_backtest_data import load_cached, load_watchlist
from swingbot.core.backtest_scenarios import CONFLUENCE_GATES, replay_scenarios
from swingbot.core.plan_engine import simulate_exit
from swingbot.core.strategy_types import HORIZONS

VALIDATION = ("2024-01-01", "2025-12-31")
MIN_N = 15
CHUNK_DIR = ROOT / "docs" / "superpowers" / "results" / "_confluence_validation_chunks"


def _ticker_worker(args):
    """Same replay_scenarios + simulate_exit shape as
    tune_confluence_gates.py's _ticker_worker, but records are trimmed to
    plain {"outcome","r_total"} dicts (JSON-serializable, matches the
    existing chunk-file shape) rather than raw ExitResult objects."""
    ticker, df, start, end, gates, scale_out, horizons = args
    out = {hk: [] for hk in horizons}
    for hk in horizons:
        for i, plan in replay_scenarios(ticker, df, hk, gates=gates):
            signal_date = str(df.index[i].date())
            if start and signal_date < start:
                continue
            if end and signal_date > end:
                continue
            r = simulate_exit(df, i, plan, scale_out=scale_out)
            out[hk].append({"outcome": r.outcome, "r_total": r.r_total})
    return ticker, out


def _aggregate_records(records: list) -> dict:
    """Same math as backtest_scenarios._aggregate, operating on the plain
    {"outcome","r_total"} dicts chunk files store (no runner_outcome field
    is persisted in chunks, so no runner breakdown here -- the validation
    table/gates don't need it)."""
    closed = [r for r in records if r["outcome"] != "not_triggered"]
    ev = [r for r in closed if r["outcome"] in ("win", "loss")]
    wins = [r for r in ev if r["outcome"] == "win"]
    return {
        "n": len(ev),
        "wins": len(wins),
        "losses": len(ev) - len(wins),
        "scratches": sum(1 for r in closed if r["outcome"] == "scratch"),
        "timeouts": sum(1 for r in closed if r["outcome"] == "timeout"),
        "not_triggered": sum(1 for r in records if r["outcome"] == "not_triggered"),
        "win_rate": len(wins) / len(ev) * 100 if ev else None,
        "expectancy_r": float(np.mean([r["r_total"] for r in closed])) if closed else None,
    }


def _row_stats(agg: dict) -> dict:
    """Adapt _aggregate_records' shape to the n_eval/excluded_share shape
    run_backtest_range.py's pool()/passes()/_scenario_row_stats use."""
    closed = agg["n"] + agg["scratches"] + agg["timeouts"]
    return {
        "n_eval": agg["n"], "win_rate": agg["win_rate"],
        "expectancy_r": agg["expectancy_r"],
        "scratches": agg["scratches"], "timeouts": agg["timeouts"],
        "excluded_share": (agg["scratches"] + agg["timeouts"]) / closed if closed else 0.0,
    }


def passes(stats: dict, min_n: int) -> bool:
    return (stats["n_eval"] >= min_n
            and stats["win_rate"] is not None and stats["win_rate"] >= 80
            and stats["expectancy_r"] is not None and stats["expectancy_r"] > 0
            and stats["excluded_share"] <= 0.5)


def main():
    CHUNK_DIR.mkdir(parents=True, exist_ok=True)
    tickers = sorted(load_watchlist())
    frames = {}
    for ticker in tickers:
        df = load_cached(ticker)
        if df is not None:
            frames[ticker] = df
    print(f"loaded {len(frames)}/{len(tickers)} cached tickers", flush=True)
    print(f"VALIDATION {VALIDATION} gates={CONFLUENCE_GATES} "
          f"horizons={list(HORIZONS)}", flush=True)

    existing = {p.stem for p in CHUNK_DIR.glob("*.json")}
    remaining = [t for t in sorted(frames) if t not in existing]
    print(f"{len(existing)} ticker(s) already chunked, {len(remaining)} remaining",
          flush=True)

    if remaining:
        jobs = [(t, frames[t], VALIDATION[0], VALIDATION[1], CONFLUENCE_GATES,
                 True, list(HORIZONS)) for t in remaining]
        with ProcessPoolExecutor() as ex:
            futures = [ex.submit(_ticker_worker, job) for job in jobs]
            for fut in as_completed(futures):
                ticker, out = fut.result()
                (CHUNK_DIR / f"{ticker}.json").write_text(json.dumps(out), encoding="utf-8")
                print(f"chunk done: {ticker}", flush=True)

    # Aggregate ALL chunk files (existing + newly computed).
    by_horizon_records = {hk: [] for hk in HORIZONS}
    n_tickers = 0
    for p in sorted(CHUNK_DIR.glob("*.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        n_tickers += 1
        for hk in HORIZONS:
            by_horizon_records[hk].extend(data.get(hk, []))

    print(f"\naggregated {n_tickers} ticker chunk file(s)\n")
    header = f"{'Strategy':22s} {'N':>5s} {'Win%':>6s} {'ExpR':>7s} {'Scr':>5s} {'TO':>5s} {'Excl%':>6s}  PASS"
    lines = [f"== VALIDATION {VALIDATION[0]} .. {VALIDATION[1]} | confluence scenario replay | "
             f"pass: WR>=80, ExpR>0, N>={MIN_N}, excl<=50% ==", header]
    all_records = []
    per_horizon_stats = {}
    for hk in HORIZONS:
        recs = by_horizon_records[hk]
        all_records.extend(recs)
        agg = _aggregate_records(recs)
        st = _row_stats(agg)
        per_horizon_stats[hk] = st
        if st["n_eval"] == 0 and st["scratches"] == 0 and st["timeouts"] == 0:
            continue
        wr = f"{st['win_rate']:.1f}" if st["win_rate"] is not None else "n/a"
        er = f"{st['expectancy_r']:+.3f}" if st["expectancy_r"] is not None else "n/a"
        flag = "PASS" if passes(st, MIN_N) else "FAIL"
        lines.append(f"{'confluence/' + hk:22s} {st['n_eval']:5d} {wr:>6s} {er:>7s} "
                     f"{st['scratches']:5d} {st['timeouts']:5d} {st['excluded_share']*100:5.0f}%  {flag}")

    pooled_agg = _aggregate_records(all_records)
    pooled = _row_stats(pooled_agg)
    wr = f"{pooled['win_rate']:.1f}" if pooled["win_rate"] is not None else "n/a"
    er = f"{pooled['expectancy_r']:+.3f}" if pooled["expectancy_r"] is not None else "n/a"
    flag = "PASS" if passes(pooled, MIN_N) else "FAIL"
    lines.append(f"{'confluence/pooled':22s} {pooled['n_eval']:5d} {wr:>6s} {er:>7s} "
                 f"{pooled['scratches']:5d} {pooled['timeouts']:5d} {pooled['excluded_share']*100:5.0f}%  {flag}")

    report = "\n".join(lines)
    print("\n" + report)

    summary = {
        "window": list(VALIDATION), "gates": CONFLUENCE_GATES,
        "n_tickers": n_tickers, "min_n": MIN_N,
        "by_horizon": {hk: {**per_horizon_stats[hk], "pass": passes(per_horizon_stats[hk], MIN_N)}
                       for hk in HORIZONS},
        "pooled": {**pooled, "pass": passes(pooled, MIN_N)},
    }
    out_path = ROOT / "docs" / "superpowers" / "results" / "confluence_validation.json"
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nSaved {out_path}")


if __name__ == "__main__":
    main()
