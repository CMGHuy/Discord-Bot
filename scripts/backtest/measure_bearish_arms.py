#!/usr/bin/env python3
"""Measure one strategy's bearish arm on TRAIN; never spends VALIDATION."""
from __future__ import annotations
import argparse, json, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(Path(__file__).resolve().parent)]
from run_backtest_range import TRAIN, _build_asof_map, _tickers_for_run, _with_context, load_cached, window_trades
from swingbot.core.backtesting import arm_rule
from swingbot.core.backtesting.backtest import run_backtest
from swingbot.core.backtesting.backtest_wf import ANCHORED_FOLDS
from swingbot.core.edge.rs_gate import rs_verdict
from swingbot.core.market.entry_filters import gate_override
from swingbot.core.market.strategy_types import HORIZONS, STRATEGY_GATES
from swingbot.core.marketdata.universe import data_quality_issues, liquidity_reason

ALL_HZ = tuple(HORIZONS)

def _unmasked_gates(strategy):
    gates = dict(STRATEGY_GATES.get(strategy) or {})
    gates["directions"] = ("bullish", "bearish")
    gates.pop("horizons", None); gates.pop("horizons_by_direction", None)
    return gates

def bearish_arm_trades(strategy, frames, asof_map, *, date_from, date_to, horizons=ALL_HZ):
    rows = []
    with gate_override(strategy, _unmasked_gates(strategy)):
        for index, (ticker, frame) in enumerate(sorted(frames.items()), 1):
            print(f"[{index}/{len(frames)}] {ticker}", flush=True)
            for horizon in horizons:
                summary = run_backtest(ticker, frame, strategy, horizon, one_at_a_time=True,
                    exit_model="v2", scale_out=True, tp2_mode="levels", frictions=True, asof=asof_map.get(ticker))
                rows.extend({"ticker": ticker, "horizon_key": horizon, "trade": trade}
                            for trade in window_trades(summary, date_from, date_to) if trade.direction == "bearish")
    return rows

def apply_laggard_rule(rows):
    return [row for row in rows if rs_verdict(row["ticker"], "bearish",
            (getattr(row["trade"], "context", None) or {}).get("rs_combined") or 50.0,
            rs_available=(getattr(row["trade"], "context", None) or {}).get("rs_combined") is not None)["status"] != "block"]

def _stats(rows): return arm_rule.pooled_stats([row["trade"] for row in rows])
def _fold_stats(by_fold, horizons):
    return [{"test_year": year, "stats": _stats(rows if horizons is None else [r for r in rows if r["horizon_key"] in horizons])} for year, rows in sorted(by_fold.items())]

def evaluate(strategy, rows_train, rows_by_fold, *, horizons_mask):
    masked = rows_train if horizons_mask is None else [r for r in rows_train if r["horizon_key"] in horizons_mask]
    stage1 = {"masked": {"horizons": horizons_mask, "pooled": _stats(masked), "folds": _fold_stats(rows_by_fold, horizons_mask)},
              "all": {"horizons": ALL_HZ, "pooled": _stats(rows_train), "folds": _fold_stats(rows_by_fold, None)}}
    for arm in stage1.values(): arm["verdict"] = arm_rule.stage1_verdict(arm["pooled"], arm["folds"])
    decision, chosen = "fail", None
    if horizons_mask is not None and stage1["masked"]["verdict"]["clears"]: decision, chosen = "clear_masked", horizons_mask
    elif stage1["all"]["verdict"]["clears"]: decision = "clear_all"
    stage2 = {"allowed": False, "candidates": []}
    if decision == "fail" and arm_rule.stage2_allowed(stage1["all"]["pooled"]):
        stage2["allowed"] = True
        per_horizon = {h: _stats([r for r in rows_train if r["horizon_key"] == h]) for h in ALL_HZ}
        for size in range(2, 6):
            for start in range(len(ALL_HZ) - size + 1):
                subset = ALL_HZ[start:start + size]
                if not all((per_horizon[h]["expectancy_r"] or 0) > 0 for h in subset): continue
                selected = [r for r in rows_train if r["horizon_key"] in subset]
                pooled = _stats(selected); verdict = arm_rule.stage1_verdict(pooled, _fold_stats(rows_by_fold, subset))
                neighbours = [_stats([r for r in rows_train if r["horizon_key"] in n]) for n in arm_rule.neighbour_subsets(subset, ALL_HZ)]
                stage2["candidates"].append({"horizons": subset, "pooled": pooled, "verdict": verdict, "plateau": arm_rule.plateau_ok(pooled, neighbours)})
        cleared = [c for c in stage2["candidates"] if c["verdict"]["clears"] and c["plateau"]]
        if cleared:
            best = max(cleared, key=lambda c: c["pooled"]["expectancy_r"])
            decision, chosen = "clear_subset", best["horizons"]
    return {"strategy": strategy, "stage1": stage1, "stage2": stage2, "decision": decision, "chosen_horizons": chosen, "n_bearish_before_rs": None, "n_bearish_after_rs": len(rows_train)}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--strategy", required=True); ap.add_argument("--out", required=True); ap.add_argument("--universe"); ap.add_argument("--tickers")
    args=ap.parse_args(); started=time.monotonic(); tickers=args.tickers.split(",") if args.tickers else _tickers_for_run(args.universe)
    frames={ticker: _with_context(load_cached(ticker)) for ticker in tickers}; frames={t: f for t,f in frames.items() if f is not None and liquidity_reason(f) is None and not data_quality_issues(f,t)}
    all_rows=bearish_arm_trades(args.strategy, frames, _build_asof_map(list(frames), frames, args.universe), date_from=TRAIN[0], date_to=TRAIN[1])
    rows=apply_laggard_rule(all_rows); folds={start[:4]: [r for r in rows if start <= r["trade"].entry_date <= end] for _,_,start,end in ANCHORED_FOLDS}
    result=evaluate(args.strategy, rows, folds, horizons_mask=(STRATEGY_GATES.get(args.strategy) or {}).get("horizons")); result.update(n_bearish_before_rs=len(all_rows), universe_n=len(frames), elapsed_s=round(time.monotonic()-started,1))
    Path(args.out).write_text(json.dumps(result, indent=1, default=str), encoding="utf-8"); print(f"{args.strategy}: decision={result['decision']} -> {args.out}")

if __name__ == "__main__": main()
