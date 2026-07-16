# scripts/tune_exit_v2.py
"""TRAIN-only grid for exit-model-v2 runner params + breakout entry-type.

Selection rule is PRE-REGISTERED (see plan Task 30) and printed with the
output so the result doc can quote it verbatim. Never run this against the
validation window -- the harness flags for that don't even exist here.
"""
import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from swingbot.core import plan_engine
from swingbot.core.backtest import ALL_STRATEGIES, run_backtest
from swingbot.core.strategy_types import HORIZONS, STRATEGY_GATES

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "backtest_cache"
TRAIN = ("2020-01-01", "2023-12-31")
BREAKOUT_CLASS = {"Break & Retest", "Support/Resistance", "EMA Crossover"}
GRID_TRAIL = [2.0, 2.5, 3.0]
GRID_TP2 = ["levels", "none"]
RULE = "WR>=80 and ExpR>0 and N>=30 and excl<=50%; max ExpR wins; else keep defaults"


def _gated_horizons(strategy):
    gates = STRATEGY_GATES.get(strategy, {})
    return list(gates.get("horizons", HORIZONS.keys()))


def _pool(summaries):
    trades = [t for s in summaries for t in s.trades
              if TRAIN[0] <= t.entry_date <= TRAIN[1]]
    if not trades:
        return None
    ev = [t for t in trades if t.outcome in ("win", "loss")]
    wins = [t for t in ev if t.outcome == "win"]
    excl = [t for t in trades if t.outcome in ("scratch", "timeout")]
    return {
        "n": len(ev),
        "win_rate": len(wins) / len(ev) * 100 if ev else 0.0,
        "expectancy_r": float(np.mean([t.r_multiple for t in trades])),
        "excl_pct": len(excl) / len(trades) * 100,
    }


def main():
    frames = {p.stem: pd.read_csv(p, index_col="Date", parse_dates=True)
              for p in sorted(CACHE_DIR.glob("*.csv"))}
    # Optional single-strategy filter (operational only -- lets the full
    # grid be run in per-strategy background chunks so a killed/restarted
    # process only loses one strategy's ~10min of work instead of the full
    # ~90min run; the grid, gates, and selection rule are unchanged).
    strategies = sys.argv[1:] or list(ALL_STRATEGIES)
    print(f"tickers: {len(frames)}  train window: {TRAIN}  rule: {RULE}\n")

    for strategy in strategies:
        entry_axis = ["market", "stop_entry"] if strategy in BREAKOUT_CLASS else ["market"]
        results = []
        for trail, tp2_mode, entry_type in itertools.product(GRID_TRAIL, GRID_TP2, entry_axis):
            plan_engine.TRAIL_ATR_MULT = trail
            plan_engine.STRATEGY_ENTRY_TYPE[strategy] = entry_type
            summaries = [
                run_backtest(tk, df, strategy, hk, exit_model="v2",
                             scale_out=True, tp2_mode=tp2_mode)
                for tk, df in frames.items()
                for hk in _gated_horizons(strategy)
            ]
            stats = _pool(summaries)
            if stats:
                results.append(((trail, tp2_mode, entry_type), stats))
                print(f"{strategy:<20} trail={trail} tp2={tp2_mode:<6} entry={entry_type:<10} "
                      f"N={stats['n']:<4} WR={stats['win_rate']:5.1f} "
                      f"ExpR={stats['expectancy_r']:+.3f} excl={stats['excl_pct']:4.1f}%")
        # restore defaults before scoring the next strategy
        plan_engine.TRAIL_ATR_MULT = 2.5
        plan_engine.STRATEGY_ENTRY_TYPE.pop(strategy, None)

        qualifying = [(cfg, s) for cfg, s in results
                      if s["win_rate"] >= 80 and s["expectancy_r"] > 0
                      and s["n"] >= 30 and s["excl_pct"] <= 50]
        if qualifying:
            cfg, s = max(qualifying, key=lambda x: x[1]["expectancy_r"])
            print(f">>> {strategy}: WINNER trail={cfg[0]} tp2={cfg[1]} entry={cfg[2]} "
                  f"(N={s['n']} WR={s['win_rate']:.1f} ExpR={s['expectancy_r']:+.3f})\n")
        else:
            print(f">>> {strategy}: no config qualifies -- KEEP DEFAULTS (2.5, tp2 on, market)\n")


if __name__ == "__main__":
    main()
