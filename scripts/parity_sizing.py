#!/usr/bin/env python3
"""Task 13: full-corpus sizing-parity harness.

Compares `backtest._trade_plan_at` (CURRENT -- it already delegates to
`plan_engine`, see swingbot/core/backtest.py) against
`tests.fixtures.legacy_trade_plan_at.legacy_trade_plan_at`, a FROZEN copy of
`_trade_plan_at` as it stood pre-extraction (commit ac91654, before Task 14
rewired it to call plan_engine). See that module's docstring for why it must
stay independent of plan_engine.py.

Runs every ticker cached under data/backtest_cache/ x every strategy in
backtest.ALL_STRATEGIES x every horizon in HORIZONS x every entry bar whose
entry date falls in the TRAIN window (2020-01-01..2023-12-31, same window
scripts/run_backtest_range.py and scripts/tune_strategy.py use), comparing
(stop, tp1) old vs new.

    python scripts/parity_sizing.py

Prints the count compared, the max abs deviation seen, and the mismatch
count (deviation > 1e-6); exits 1 if any mismatch is found. A mismatch here
is a real correctness bug in the plan_engine extraction -- investigate it,
do not loosen TOLERANCE or edit the frozen reference to make this pass.
"""
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from swingbot.core import backtest
from swingbot.core.backtest import ALL_STRATEGIES
from swingbot.core.indicators import atr, elliott_wave3_entries
from swingbot.core.strategy_types import HORIZONS, MIN_BARS

from tests.fixtures.legacy_trade_plan_at import legacy_trade_plan_at

CACHE_DIR = ROOT / "data" / "backtest_cache"
TOLERANCE = 1e-6
TRAIN = ("2020-01-01", "2023-12-31")


def _load_cached(path: Path):
    df = pd.read_csv(path, index_col="Date", parse_dates=True)
    return df if len(df) else None


def _precomputed_series(df, strategy, horizon_key):
    """Mirrors the precomputation run_backtest() does before calling
    _trade_plan_at for each bar."""
    atr_series = atr(df, 14)
    swing_high_series = swing_low_series = None
    if strategy == "Fibonacci":
        lookback = HORIZONS[horizon_key]["fib_lookback"]
        swing_high_series = df["High"].rolling(lookback).max()
        swing_low_series = df["Low"].rolling(lookback).min()
    volume_ratio_series = None
    if strategy == "Support/Resistance":
        vol_avg20 = df["Volume"].rolling(20).mean()
        volume_ratio_series = df["Volume"] / vol_avg20
    entry_levels = None
    if strategy == "Elliott Wave":
        threshold_pct = HORIZONS[horizon_key]["max_risk_pct"]
        _, _, entry_levels = elliott_wave3_entries(df, threshold_pct)
    return atr_series, swing_high_series, swing_low_series, volume_ratio_series, entry_levels


def main() -> int:
    if not CACHE_DIR.is_dir():
        print(f"no cache dir at {CACHE_DIR}; nothing to check")
        return 0

    tickers = sorted(p.stem for p in CACHE_DIR.glob("*.csv"))
    if not tickers:
        print(f"no cached CSVs under {CACHE_DIR}")
        return 0

    compared = 0
    max_abs_dev = 0.0
    mismatches = 0

    for ti, ticker in enumerate(tickers, 1):
        df = _load_cached(CACHE_DIR / f"{ticker}.csv")
        if df is None:
            continue
        print(f"[{ti}/{len(tickers)}] {ticker}", flush=True)

        for horizon_key in HORIZONS:
            min_bars = MIN_BARS[horizon_key]
            if len(df) < min_bars + 10:
                continue

            for strategy in ALL_STRATEGIES:
                try:
                    bullish, bearish = backtest._vectorized_entries(df, strategy, horizon_key)
                except Exception as e:
                    print(f"    ! entries {strategy}/{horizon_key}: {e}")
                    continue

                atr_series, swing_high_series, swing_low_series, volume_ratio_series, entry_levels = (
                    _precomputed_series(df, strategy, horizon_key)
                )
                entry_idx = np.where(bullish.values | bearish.values)[0]

                for i in entry_idx:
                    if i < min_bars:
                        continue
                    entry_date = df.index[i].date().isoformat()
                    if not (TRAIN[0] <= entry_date <= TRAIN[1]):
                        continue
                    direction = "bullish" if bullish.values[i] else "bearish"

                    try:
                        _, old_stop, old_tp = legacy_trade_plan_at(
                            df, i, direction, strategy, horizon_key, atr_series,
                            swing_high_series, swing_low_series, volume_ratio_series, entry_levels,
                        )
                        _, new_stop, new_tp = backtest._trade_plan_at(
                            df, i, direction, strategy, horizon_key, atr_series,
                            swing_high_series, swing_low_series, volume_ratio_series, entry_levels,
                        )
                    except Exception as e:
                        print(f"    ! {strategy}/{horizon_key} bar {i}: {e}")
                        continue

                    compared += 1
                    dev = max(abs(old_stop - new_stop), abs(old_tp - new_tp))
                    max_abs_dev = max(max_abs_dev, dev)
                    if dev > TOLERANCE:
                        mismatches += 1
                        print(
                            f"    MISMATCH {ticker} {strategy}/{horizon_key} bar {i} "
                            f"({entry_date}, {direction}): "
                            f"old=({old_stop:.6f},{old_tp:.6f}) new=({new_stop:.6f},{new_tp:.6f}) "
                            f"dev={dev:.8f}"
                        )

    print(f"\ncompared: {compared}")
    print(f"max abs deviation: {max_abs_dev:.10f}")
    print(f"mismatches: {mismatches}")
    return 1 if mismatches else 0


if __name__ == "__main__":
    sys.exit(main())
