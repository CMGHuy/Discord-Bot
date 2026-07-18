#!/usr/bin/env python3
"""Grid sweep of one strategy's tunables over the TRAIN window ONLY
(2020-01-01 .. 2023-12-31). Never point this at the validation window --
that is the whole point of having one.

Selection rule (spec section 9): among configs with WR>=80, ExpR>0, N>=30,
pick max expectancy. If none qualify, the ranking output still shows the
best candidates so the failure policy (gating directions/horizons) can be
applied by hand in Task 19."""
import argparse
import itertools
import sys
import warnings
from collections import defaultdict
from pathlib import Path

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import numpy as np

from fetch_backtest_data import load_cached, load_watchlist
import swingbot.core.backtest as bt
import swingbot.core.entry_filters as ef
from swingbot.core.strategy_types import HORIZONS

TRAIN = ("2020-01-01", "2023-12-31")

PARAM_GRID = {
    "EMA Crossover":      {"rsi_dip": [40, 45, 50], "ext_atr": [0.75, 1.0, 1.5]},
    "VWAP":               {"ext_pct": [1.0, 1.5, 2.0], "hold_bars_other": [2, 3]},
    "Fibonacci":          {"ratios": [(0.382, 0.5, 0.618), (0.5, 0.618)],
                           "rsi_bull": [(35, 58), (40, 60)]},
    "Support/Resistance": {"base_atr": [3.0, 4.0, 5.0], "close_frac": [0.3, 0.4, 0.5]},
    "RSI":                {"os_level": [30, 35], "confirm": ["prev_high", "prev_close"]},
    "MACD":               {"ext_atr": [0.75, 1.0, 1.5]},
    "Elliott Wave":       {"depth_min": [0.30, 0.38], "depth_max": [0.78, 0.80]},
    "MA Ribbon":          {"ext_pct": [6.0, 8.0, 10.0]},
    "Break & Retest":     {"hold_tol_pct": [0.3, 0.5, 0.8]},
    "RSI Divergence":     {"rsi_reclaim": [38, 40, 45]},
    "Volume Profile":     {"node_share": [6.0, 8.0, 10.0], "prox_pct": [1.0, 1.5, 2.0]},
}


def run_config(strategy, dfs, exit_model="v1", scale_out=False):
    tp2_mode = "levels" if exit_model == "v2" else "none"
    trades = []
    for ticker, df in dfs.items():
        for hk in HORIZONS:
            try:
                s = bt.run_backtest(ticker, df, strategy, hk, one_at_a_time=True,
                                    exit_model=exit_model, scale_out=scale_out,
                                    tp2_mode=tp2_mode)
            except Exception:
                continue
            trades.extend(t for t in s.trades if TRAIN[0] <= t.entry_date <= TRAIN[1])
    ev = [t for t in trades if t.outcome in ("win", "loss")]
    wins = sum(1 for t in ev if t.outcome == "win")
    closed = len(trades)
    excl = sum(1 for t in trades if t.outcome in ("scratch", "timeout"))
    return {
        "n_eval": len(ev),
        "win_rate": wins / len(ev) * 100 if ev else None,
        "expectancy_r": float(np.mean([t.r_multiple for t in trades])) if trades else None,
        "excluded_share": excl / closed if closed else 0.0,
    }


def _parse_grid_value(s: str):
    low = s.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if low in ("none", "null"):
        return None
    for cast in (int, float):
        try:
            return cast(s)
        except ValueError:
            pass
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", required=True)
    ap.add_argument("--be-trigger", type=float, default=None)
    ap.add_argument("--grid", nargs="+", default=None, metavar="KEY=V1,V2",
                    help="override the built-in grid, e.g. "
                         "--grid max_adx=20,25,30 require_bb_range=true,false "
                         "(sweeps ONLY these keys; other params stay at "
                         "DEFAULT_PARAMS)")
    ap.add_argument("--exit-model", dest="exit_model", choices=["v1", "v2"],
                    default="v1")
    ap.add_argument("--scale-out", dest="scale_out", action="store_true")
    args = ap.parse_args()
    strategy = args.strategy
    if args.grid:
        grid_override = {}
        for spec in args.grid:
            key, _, vals = spec.partition("=")
            if not vals:
                ap.error(f"bad --grid spec {spec!r}, expected KEY=V1,V2,...")
            grid_override[key] = [_parse_grid_value(v) for v in vals.split(",")]
        PARAM_GRID[strategy] = grid_override
    if strategy not in PARAM_GRID:
        ap.error(f"unknown strategy {strategy!r}; one of {list(PARAM_GRID)}")
    if args.be_trigger is not None:
        bt.BREAKEVEN_TRIGGER_FRACTION = args.be_trigger

    dfs = {t: d for t in sorted(load_watchlist()) if (d := load_cached(t)) is not None}
    print(f"{len(dfs)} tickers loaded from cache")

    grid = PARAM_GRID[strategy]
    keys = list(grid)
    baseline = dict(ef.DEFAULT_PARAMS[strategy])
    rows = []
    try:
        for combo in itertools.product(*(grid[k] for k in keys)):
            params = dict(zip(keys, combo))
            ef.DEFAULT_PARAMS[strategy].update(params)
            stats = run_config(strategy, dfs, exit_model=args.exit_model,
                               scale_out=args.scale_out)
            rows.append((params, stats))
            wr = f"{stats['win_rate']:.1f}" if stats["win_rate"] is not None else "n/a"
            er = f"{stats['expectancy_r']:+.3f}" if stats["expectancy_r"] is not None else "n/a"
            print(f"  {params} -> N={stats['n_eval']} WR={wr} ExpR={er} excl={stats['excluded_share']*100:.0f}%")
    finally:
        ef.DEFAULT_PARAMS[strategy] = baseline

    qualifying = [(p, s) for p, s in rows
                  if s["n_eval"] >= 30 and (s["win_rate"] or 0) >= 80
                  and (s["expectancy_r"] or 0) > 0 and s["excluded_share"] <= 0.5]
    print(f"\n{len(qualifying)}/{len(rows)} configs qualify (WR>=80, ExpR>0, N>=30, excl<=50%)")
    ranked = sorted(qualifying or rows,
                    key=lambda r: (r[1]["expectancy_r"] or -9), reverse=True)
    print("Top 5:")
    for p, s in ranked[:5]:
        print(f"  {p} -> N={s['n_eval']} WR={s['win_rate'] and round(s['win_rate'],1)} ExpR={s['expectancy_r'] and round(s['expectancy_r'],3)}")


if __name__ == "__main__":
    main()
