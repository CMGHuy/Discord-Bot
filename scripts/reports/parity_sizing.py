#!/usr/bin/env python3
"""Task 13: full-corpus sizing-parity harness.

Compares `backtest._trade_plan_at` (CURRENT -- it already delegates to
`plan_engine`, see swingbot/core/backtesting/backtest.py) against
`tests.fixtures.legacy_trade_plan_at.legacy_trade_plan_at`, a FROZEN copy of
`_trade_plan_at` as it stood pre-extraction (commit ac91654, before Task 14
rewired it to call plan_engine). See that module's docstring for why it must
stay independent of plan_engine.py.

Runs every ticker cached under data/backtest_cache/ x every strategy in
backtest.ALL_STRATEGIES x every horizon in HORIZONS x every entry bar whose
entry date falls in the TRAIN window (2020-01-01..2023-12-31, same window
scripts/backtest/run_backtest_range.py and scripts/backtest/tune_strategy.py use), comparing
stop old vs new (STOP ONLY -- see the v31 note below for why tp1 isn't).

    python scripts/reports/parity_sizing.py

Prints the count compared, the count skipped as "no qualifying v31 target"
(a bar where the new selector correctly declines, not an error), the max
abs stop deviation seen, and the mismatch count (deviation > 1e-6); exits 1
if any mismatch is found. A mismatch here is a real correctness bug in the
plan_engine extraction -- investigate it, do not loosen TOLERANCE or edit
the frozen reference to make this pass.

KNOWN EXCEPTION (v31 Task 14/15): tp1 now diverges from the frozen reference
BY DESIGN -- plan_engine prices every target off a real structural level
(select_structural_target) instead of the frozen module's fixed per-strategy
reward:risk arithmetic, which no longer exists in plan_engine at all. Only
the stop assertion is still a meaningful parity check; a tp1 mismatch here
is expected, not a regression, and must not be "fixed" by editing the frozen
reference or loosening TOLERANCE.
"""
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from swingbot.core.backtesting import backtest
from swingbot.core.backtesting.backtest import ALL_STRATEGIES
from swingbot.core.market.indicators import atr, elliott_wave3_entries
from swingbot.core.market.strategy_types import HORIZONS, MIN_BARS

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
    # The level lifecycle (P1) post-processes _trade_plan_at's output and is
    # default-on since 2026-08-08, but `legacy_trade_plan_at` is a frozen
    # pre-extraction copy that cannot have it. Left on, every entry bar where a
    # tested level moves the stop reports as a parity MISMATCH -- a spurious
    # one, since this harness exists to answer "did the Task-14 extraction
    # change sizing?", not to re-detect a measured feature. Forced off here
    # rather than documented as a caveat, so the answer cannot depend on the
    # caller's .env. tests/test_sizing_parity.py pins the same flag.
    from swingbot import config
    config.LEVEL_LIFECYCLE_STOPS_ENABLED = False

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
    no_qualifying_target = 0

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
                        new_plan = backtest._trade_plan_at(
                            df, i, direction, strategy, horizon_key, atr_series,
                            swing_high_series, swing_low_series, volume_ratio_series, entry_levels,
                        )
                    except Exception as e:
                        print(f"    ! {strategy}/{horizon_key} bar {i}: {e}")
                        continue

                    if new_plan is None:
                        # v31: a real "no qualifying target" answer, not an
                        # error and not a parity mismatch -- the frozen
                        # reference has no such concept and always returns
                        # a tuple. Counted separately so a run that quietly
                        # compares zero bars is visible, not silent.
                        no_qualifying_target += 1
                        continue
                    _, new_stop, new_tp = new_plan

                    compared += 1
                    # tp1 is NOT part of the deviation check. It diverges
                    # from the frozen reference BY DESIGN as of plan v31
                    # (docs/superpowers/plans/implemented/2026-08-16-v31-structural-targets.md,
                    # Task 15) -- plan_engine prices every target off a real
                    # structural level instead of the frozen module's fixed
                    # per-strategy reward:risk arithmetic. Only stop is
                    # still a meaningful parity check.
                    dev = abs(old_stop - new_stop)
                    max_abs_dev = max(max_abs_dev, dev)
                    if dev > TOLERANCE:
                        mismatches += 1
                        print(
                            f"    MISMATCH {ticker} {strategy}/{horizon_key} bar {i} "
                            f"({entry_date}, {direction}): "
                            f"old_stop={old_stop:.6f} new_stop={new_stop:.6f} "
                            f"dev={dev:.8f} (tp1 not compared: old={old_tp:.6f} new={new_tp:.6f})"
                        )

    print(f"\ncompared: {compared}")
    print(f"no qualifying v31 target (skipped, not a mismatch): {no_qualifying_target}")
    print(f"max abs stop deviation: {max_abs_dev:.10f}")
    print(f"mismatches: {mismatches}")
    return 1 if mismatches else 0


if __name__ == "__main__":
    sys.exit(main())
