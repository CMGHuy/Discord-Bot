#!/usr/bin/env python3
"""Full-watchlist parity check: simulate_exit(scale_out=False) vs the legacy
run_backtest exit loop it was extracted from (Task 21/23).

For every TRAIN-window (2020-01-01..2023-12-31) trade the legacy loop
produces, across every cached ticker x every strategy x every horizon,
rebuild a market-entry TradePlanV2 and re-walk it through simulate_exit.
Legacy is the specification here -- any real mismatch (outcome or
exit_index differing) means simulate_exit has a bug to fix, not the legacy
loop.

Unlike tests/test_exit_parity.py (which reconstructs the plan from
BacktestTrade's ROUNDED entry/stop_loss/take_profit fields, tolerant to
5e-4 on r), this script reconstructs the plan from the same UNROUNDED
_trade_plan_at() output run_backtest itself used -- recomputing the same
atr/swing-high-low/volume-ratio/entry-level series run_backtest computes
internally (mirrors backtest.py's run_backtest body) -- so the exit-walk
inputs are bit-identical to the legacy walk's and r can be compared near-
exactly rather than within a rounding-noise tolerance. That matters here:
for very-low-priced tickers (e.g. QBTS, entry ~$0.7-1.0) rounding entry/
stop to 4dp shifts the tiny risk-per-share enough to move rr by >5e-4,
which the rounded-reconstruction approach cannot tell apart from a real
simulate_exit bug. The unrounded approach removes that ambiguity entirely.

    python scripts/parity_exits.py
"""
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from fetch_backtest_data import load_cached, load_watchlist
from swingbot.core.backtest import ALL_STRATEGIES, _trade_plan_at, _vectorized_entries, run_backtest
from swingbot.core.indicators import atr, elliott_wave3_entries
from swingbot.core.plan_engine import PlanStatus, TradePlanV2, simulate_exit
from swingbot.core.strategy_types import HORIZONS

TRAIN = ("2020-01-01", "2023-12-31")
R_TOL = 1e-6  # both sides round(r, 3) from the same unrounded inputs


def _series_for(df, strategy, horizon_key):
    """Same precomputation run_backtest does before its per-signal loop
    (backtest.py:170-187) -- reused here so _trade_plan_at sees identical
    unrounded inputs to the legacy walk."""
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


def _plan_from_unrounded(df, i, t, ticker, strategy, horizon_key, series):
    """Market-entry plan built from the same unrounded entry/stop/tp
    _trade_plan_at would hand run_backtest's loop at this signal bar."""
    atr_series, swing_high_series, swing_low_series, volume_ratio_series, entry_levels = series
    entry, stop_loss, take_profit = _trade_plan_at(
        df, i, t.direction, strategy, horizon_key, atr_series,
        swing_high_series, swing_low_series, volume_ratio_series, entry_levels,
    )
    return TradePlanV2(
        plan_id="parity", ticker=ticker, created_at=t.entry_date,
        source="strategy", strategy=strategy, horizon_key=horizon_key,
        direction=t.direction, entry_type="market", trigger_price=entry,
        entry_price=entry, expiry_bars=5, stop_loss=stop_loss,
        tp1=take_profit, tp1_fraction=0.5, tp2=None,
        breakeven_trigger_fraction=0.5, trail_atr_mult=2.5,
        quality_score=0, quality_breakdown=[], tier="C",
        badge="WEAK", badge_stats={}, status=PlanStatus.ACTIVE,
    )


def window_trades(summary, date_from, date_to):
    return [t for t in summary.trades if date_from <= t.entry_date <= date_to]


def main():
    tickers = sorted(load_watchlist())
    n = 0
    m = 0
    mismatch_examples = []
    by_combo = {}

    for ti, ticker in enumerate(tickers, 1):
        df = load_cached(ticker)
        if df is None:
            continue
        date_to_idx = {str(d.date()): i for i, d in enumerate(df.index)}
        print(f"[{ti}/{len(tickers)}] {ticker}", flush=True)
        for horizon_key in HORIZONS:
            for strategy in ALL_STRATEGIES:
                try:
                    summary = run_backtest(ticker, df, strategy, horizon_key)
                except Exception as e:
                    print(f"    ! {strategy}/{horizon_key}: {e}")
                    continue
                trades = window_trades(summary, *TRAIN)
                if not trades:
                    continue
                series = _series_for(df, strategy, horizon_key)
                combo_key = (strategy, horizon_key)
                combo_n, combo_m = by_combo.get(combo_key, (0, 0))
                for t in trades:
                    i = date_to_idx.get(t.entry_date)
                    if i is None:
                        continue
                    plan = _plan_from_unrounded(df, i, t, ticker, strategy, horizon_key, series)
                    res = simulate_exit(df, i, plan, scale_out=False)
                    n += 1
                    combo_n += 1
                    ok = (
                        res.outcome == t.outcome
                        and res.exit_index is not None
                        and str(df.index[res.exit_index].date()) == t.exit_date
                        and abs(res.r_total - t.r_multiple) <= R_TOL
                    )
                    if not ok:
                        m += 1
                        combo_m += 1
                        if len(mismatch_examples) < 20:
                            mismatch_examples.append(
                                f"{ticker}/{strategy}/{horizon_key} {t.entry_date}: "
                                f"v2=({res.outcome}, "
                                f"{df.index[res.exit_index].date() if res.exit_index is not None else None}, "
                                f"{res.r_total}) legacy=({t.outcome}, {t.exit_date}, {t.r_multiple})"
                            )
                by_combo[combo_key] = (combo_n, combo_m)

    if mismatch_examples:
        print("\n-- mismatches (up to 20) --")
        for line in mismatch_examples:
            print(line)

    print("\n-- per strategy x horizon --")
    for (strategy, horizon_key), (combo_n, combo_m) in sorted(by_combo.items()):
        if combo_m:
            print(f"{strategy:22s} {horizon_key:6s} n={combo_n:5d} mismatches={combo_m}")

    print(f"\ntrades: {n}  mismatches: {m}")
    sys.exit(1 if m else 0)


if __name__ == "__main__":
    main()
