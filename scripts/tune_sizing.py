#!/usr/bin/env python3
"""TRAIN-only grid over the four SIZING knobs -- plan v8 Task V17.

    MIN_TARGET_PCT  x  rr  x  atr_stop_multiple  x  trail_atr_mult

Why this is a separate script and not `--grid` on `tune_strategy.py`:
`tune_strategy.py --grid` sweeps `entry_filters.DEFAULT_PARAMS[strategy]`, i.e.
*entry* parameters, and `tune_exit_v2.py` sweeps trail/tp2/entry-type. Neither
has an axis for the target floor, the R:R override or the ATR stop multiple, so
V17's grid could not be expressed in either. Those two scripts are left exactly
as they are; this one adds the missing axes and nothing else.

Selection rule (PRE-REGISTERED, plan v8 V6 Step 3, quoted verbatim in
docs/superpowers/results/2026-08-02-v17-sizing-grid.md before this ran):

    OBJECTIVE   maximise win_rate
    SUBJECT TO  every win >= MIN_TARGET_PCT (2.5%)   <- floor axis starts at 2.5
                expectancy_r > 0
                scratches + timeouts <= 50% of closed trades
    STRETCH     win_rate >= 90%
    FLOOR       reject any config with expectancy_r <= 0 regardless of WR

Trade volume is explicitly NOT an objective and must not tie-break.

Two additions the rule's own preamble requires, not deviations from it:
  * the N>=30 sample gate is applied to **n_independent**, not to the summed
    n_eval. V16/V49 measured that five strategies reuse the same entry signal
    across horizons, so a strategy-level N summed over horizons can overstate
    the evidence ~10x. The reuse ratio is re-measured per config here.
  * Wilson lower bounds are reported beside every win rate (V6 Step 5), also
    computed on the independent sample.

Never point this at the validation window -- there is no flag for it here.
"""
import argparse
import itertools
import json
import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np

from fetch_backtest_data import load_cached, load_watchlist
import swingbot.core.backtest as bt
import swingbot.core.plan_engine as pe
from swingbot import config
from swingbot.core.backtest_windows import TRAIN
from swingbot.core.gate.wr_math import wilson_lower_bound
from swingbot.core.strategy_types import HORIZONS, STRATEGY_RR_OVERRIDE

# The pre-registered grid. MIN_TARGET_PCT starts at 2.5 because the selection
# rule's own constraint is "every win >= 2.5%" -- a lower floor cannot qualify,
# so gridding it would only produce rows that are disqualified by construction.
GRID = {
    "min_target_pct": [2.5, 3.5, 5.0],
    "rr": [0.35, 0.75, 1.25, 2.0],
    "atr_stop_multiple": [1.5, 2.0, 2.5],
    "trail_atr_mult": [2.0, 2.5, 3.0],
}
AXES = list(GRID)

REUSE_FLAG_RATIO = 1.5   # same threshold V49 pinned in run_backtest_range.py


def apply_config(strategy: str, cfg: dict, adopted_exit: dict) -> None:
    """Point every sizing knob at `cfg`. All four are read live on each plan
    build (never captured at import), which is what makes a grid possible at
    all -- see plan_engine.target_floor_price / _rr_for / _atr_plan."""
    config.MIN_TARGET_PCT = cfg["min_target_pct"]
    config.TARGET_FLOOR_ENABLED = True     # the floor is the axis; it must be on
    STRATEGY_RR_OVERRIDE[strategy] = cfg["rr"]
    for h in HORIZONS.values():
        h["atr_stop_multiple"] = cfg["atr_stop_multiple"]
    # tp2 is NOT an axis of V17: it was decided per-strategy by Task 30 and the
    # plan lists tune_exit_v2.py as the place that re-opens it. Keep whatever
    # this strategy adopted and move only the trail.
    pe.EXIT_V2_PARAMS[strategy] = {**adopted_exit, "trail_atr_mult": cfg["trail_atr_mult"]}


def score(trades: list, by_horizon: dict) -> dict:
    """Pooled stats for one config, plus the horizon-reuse correction."""
    ev = [t for t in trades if t.outcome in ("win", "loss")]
    wins = sum(1 for t in ev if t.outcome == "win")
    closed = len(trades)
    excl = sum(1 for t in trades if t.outcome in ("scratch", "timeout"))

    # V49 Step 3: distinct (date, entry, direction) signatures against the
    # summed count. A ratio near 1.0 means the horizons genuinely disagree.
    per_hz = {hk: sigs for hk, sigs in by_horizon.items() if sigs}
    n_eval = len(ev)
    n_indep, distinct, ratio = n_eval, None, 1.0
    if len(per_hz) >= 2:
        union = set().union(*per_hz.values())
        summed = sum(len(s) for s in per_hz.values())
        if union:
            distinct = len(union)
            ratio = summed / distinct
            if ratio >= REUSE_FLAG_RATIO:
                n_indep = round(n_eval / ratio)

    wr = wins / n_eval * 100 if ev else None
    lb = wilson_lower_bound(round((wr or 0) / 100.0 * n_indep), n_indep) * 100
    return {
        "n_eval": n_eval,
        "n_independent": n_indep,
        "n_distinct_signals": distinct,
        "horizon_overcount": round(ratio, 2),
        "win_rate": wr,
        "wilson_lb": lb,
        "expectancy_r": float(np.mean([t.r_multiple for t in trades])) if trades else None,
        "excluded_share": excl / closed if closed else 0.0,
    }


def run_config(strategy, dfs, exit_model, scale_out, tp2_mode):
    trades, by_horizon = [], {}
    for hk in HORIZONS:
        sigs = set()
        for ticker, df in dfs.items():
            try:
                s = bt.run_backtest(ticker, df, strategy, hk, one_at_a_time=True,
                                    exit_model=exit_model, scale_out=scale_out,
                                    tp2_mode=tp2_mode)
            except Exception:
                continue
            in_window = [t for t in s.trades if TRAIN[0] <= t.entry_date <= TRAIN[1]]
            trades.extend(in_window)
            sigs.update((t.entry_date, t.entry, t.direction) for t in in_window)
        by_horizon[hk] = sigs
    return score(trades, by_horizon)


def qualifies(s: dict) -> bool:
    """The pre-registered constraint set. N is the INDEPENDENT sample."""
    return (s["n_independent"] >= 30
            and (s["expectancy_r"] or 0) > 0
            and s["excluded_share"] <= 0.5)


def _fmt(cfg: dict) -> str:
    return (f"floor={cfg['min_target_pct']:<4} rr={cfg['rr']:<5} "
            f"stop={cfg['atr_stop_multiple']:<4} trail={cfg['trail_atr_mult']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", required=True)
    ap.add_argument("--exit-model", dest="exit_model", choices=["v1", "v2"], default="v2",
                    help="v2 (default) is what production runs; v1 only for comparison.")
    ap.add_argument("--no-scale-out", dest="scale_out", action="store_false", default=True)
    ap.add_argument("--tp2-mode", dest="tp2_mode", default="levels", choices=["levels", "none"])
    ap.add_argument("--grid", nargs="+", default=None, metavar="AXIS=V1,V2",
                    help="override one or more of the four axes (smoke tests only -- "
                         "the shipped grid is the pre-registered one)")
    ap.add_argument("--max-tickers", type=int, default=None, help="smoke-test shortcut")
    ap.add_argument("--json", type=str, default=None)
    args = ap.parse_args()
    strategy = args.strategy

    grid = {k: list(v) for k, v in GRID.items()}
    if args.grid:
        for spec in args.grid:
            key, _, vals = spec.partition("=")
            if key not in grid or not vals:
                ap.error(f"bad --grid spec {spec!r}; axes are {AXES}")
            grid[key] = [float(v) for v in vals.split(",")]

    tickers = sorted(load_watchlist())
    if args.max_tickers:
        tickers = tickers[:args.max_tickers]
    dfs = {t: d for t in tickers if (d := load_cached(t)) is not None}

    combos = [dict(zip(AXES, c)) for c in itertools.product(*(grid[a] for a in AXES))]
    print(f"{len(dfs)} tickers loaded from cache | strategy={strategy} "
          f"exit={args.exit_model} scale_out={args.scale_out} tp2={args.tp2_mode}", flush=True)
    print(f"TRAIN window {TRAIN[0]}..{TRAIN[1]} | {len(combos)} configs", flush=True)
    print("rule: max WR s.t. ExpR>0, independent N>=30, dead<=50% "
          "(plan v8 V6 Step 3; N corrected for horizon reuse per V49)\n", flush=True)

    # The level map is the whole cost of an exit-v2 run and none of its inputs
    # is a sizing knob, so every config after the first re-reads it. Exact-key
    # memo: it cannot change a result, only skip recomputing one. ~30x.
    bt.enable_level_map_memo()

    # Everything below mutates module-level state shared with the live bot's
    # code path; the finally block is not optional.
    saved = {
        "MIN_TARGET_PCT": config.MIN_TARGET_PCT,
        "TARGET_FLOOR_ENABLED": config.TARGET_FLOOR_ENABLED,
        "rr": STRATEGY_RR_OVERRIDE.get(strategy),
        "stops": {hk: h["atr_stop_multiple"] for hk, h in HORIZONS.items()},
        "exit": pe.EXIT_V2_PARAMS.get(strategy),
    }
    adopted_exit = dict(saved["exit"] or {})
    rows = []
    try:
        for n, cfg in enumerate(combos, 1):
            apply_config(strategy, cfg, adopted_exit)
            t0 = time.time()
            stats = run_config(strategy, dfs, args.exit_model, args.scale_out, args.tp2_mode)
            rows.append({"params": cfg, **stats})
            wr = f"{stats['win_rate']:.1f}" if stats["win_rate"] is not None else "n/a"
            er = f"{stats['expectancy_r']:+.3f}" if stats["expectancy_r"] is not None else "n/a"
            # One flushed line per config: this is a multi-hour job whose stdout
            # is always redirected (CLAUDE.md's long-running-script rule).
            print(f"[{n}/{len(combos)}] {_fmt(cfg)} -> N={stats['n_eval']:<5} "
                  f"Nind={stats['n_independent']:<5} WR={wr:>5} LB={stats['wilson_lb']:.1f} "
                  f"ExpR={er} dead={stats['excluded_share']*100:.0f}% "
                  f"({time.time()-t0:.0f}s)", flush=True)
    finally:
        config.MIN_TARGET_PCT = saved["MIN_TARGET_PCT"]
        config.TARGET_FLOOR_ENABLED = saved["TARGET_FLOOR_ENABLED"]
        if saved["rr"] is None:
            STRATEGY_RR_OVERRIDE.pop(strategy, None)
        else:
            STRATEGY_RR_OVERRIDE[strategy] = saved["rr"]
        for hk, v in saved["stops"].items():
            HORIZONS[hk]["atr_stop_multiple"] = v
        if saved["exit"] is None:
            pe.EXIT_V2_PARAMS.pop(strategy, None)
        else:
            pe.EXIT_V2_PARAMS[strategy] = saved["exit"]
        bt.disable_level_map_memo()

    qualifying = [r for r in rows if qualifies(r)]
    print(f"\n{len(qualifying)}/{len(rows)} configs qualify "
          f"(ExpR>0, independent N>=30, dead<=50%)", flush=True)
    ranked = sorted(qualifying or rows, key=lambda r: (r["win_rate"] or -9), reverse=True)
    print("Top 5 by win rate:" if qualifying
          else "NO config qualifies -- KEEP DEFAULTS. Best unqualified rows, for the record:")
    for r in ranked[:5]:
        print(f"  {_fmt(r['params'])} -> N={r['n_eval']} Nind={r['n_independent']} "
              f"WR={r['win_rate'] and round(r['win_rate'], 1)} LB={r['wilson_lb']:.1f} "
              f"ExpR={r['expectancy_r'] and round(r['expectancy_r'], 3)}", flush=True)

    if args.json:
        Path(args.json).write_text(json.dumps({
            "strategy": strategy,
            "train_window": list(TRAIN),
            "exit_model": args.exit_model,
            "scale_out": args.scale_out,
            "tp2_mode": args.tp2_mode,
            "adopted_exit_params": adopted_exit,
            "n_tickers": len(dfs),
            "grid": grid,
            "rows": rows,
            "qualifying": len(qualifying),
            "best": ranked[0] if qualifying else None,
        }, indent=2))
        print(f"Wrote results to {args.json}", flush=True)


if __name__ == "__main__":
    main()
