"""
Backtesting engine.

Replays a strategy+horizon combination over historical data using the same
signal-detection and trade-plan logic as the live bot, then walks forward
bar-by-bar from each entry to see whether the stop-loss or take-profit was
hit first (same conservative "stop wins same-day ties" rule used live).
Entries themselves come from `entry_filters.entries_for` (via
`_vectorized_entries` below) -- the SAME function the live scanner
(`signals.py`) calls, so a change to entry logic changes backtest and live
signals together; they cannot silently drift apart.

This answers the question the live `!performance` command can't yet answer
early on: "if this strategy had been running for the last N years, would it
have actually worked?"

Four-outcome taxonomy: every closed trade lands in exactly one bucket.
  - "win"     -- take-profit hit before stop-loss.
  - "loss"    -- stop-loss hit before the break-even trigger was reached.
  - "scratch" -- stop-loss hit AFTER the break-even trigger moved the stop
    to entry; realized ~0R, not a loss. See BREAKEVEN_TRIGGER_FRACTION in
    strategy_types.py: once favorable excursion covers that fraction of the
    distance to target, the stop moves to entry for all subsequent bars.
  - "timeout" -- neither stop nor target hit within max_holding_days; the
    trade is marked to market at the closing price on the last bar.
`win_rate` is computed over win+loss only (scratch/timeout are excluded from
the numerator/denominator by design -- they didn't "beat the market", they
were defended). `expectancy_r` is computed over ALL closed trades (wins,
losses, scratches ~0R, and marked-to-market timeouts) -- that is the "does
this strategy make money" number, and the one gated on for PASS/FAIL.

R:R floor rationale (`STRATEGY_RR_OVERRIDE`, strategy_types.py): break-even
win rate at reward:risk ratio X is 1/(1+X); at the hard floor of X=0.30 that
is 76.9%, so the acceptance bar of WR>=80% is still profitable at the floor.
R:R is never tuned below 0.30 -- a strategy could clear 80% win rate and
still lose money if R:R dropped further, which would defeat the point of
gating on win rate at all.

Per-strategy entry-direction/horizon restrictions (`STRATEGY_GATES`,
strategy_types.py) were selected by tuning on a 2020-2023 TRAIN window only
and confirmed once against a 2024-2025 held-out VALIDATION window (see
`docs/superpowers/results/2026-07-train-tuning.md` and
`2026-07-validation.md`). Some strategies that passed on train did not
reproduce on validation -- that gap is reported honestly in the validation
doc, not papered over by retuning after the fact.

Important limitations (stated plainly, not buried):
  - Trades are evaluated independently; overlapping trades on the same
    ticker are all counted, which overstates real deployable capital
    (you can't actually take 4 overlapping positions with 1 account).
  - No fees, slippage, or partial fills.
  - The equity curve assumes trades compound sequentially in the order
    they occurred, which is a simplification, not a portfolio simulation.
  - Survivorship bias applies (yfinance only returns tickers that still
    exist today).
  - Even the strategies that PASS here were tuned/gated against a finite
    2020-2025 sample; three (RSI, MA Ribbon, RSI Divergence) passed the
    train window but failed the held-out validation window, a reminder
    that "passes on cached history" is not a promise of future performance.
This is a directional sanity check, not a guarantee of future performance.
"""
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .indicators import atr, elliott_wave3_entries
from .strategy import HORIZONS, MIN_BARS, SR_VOLUME_MULTIPLE
from .strategy_types import BREAKEVEN_TRIGGER_FRACTION, STRATEGY_GATES, STRATEGY_RR_OVERRIDE


@dataclass
class BacktestTrade:
    entry_date: str
    exit_date: str | None
    direction: str
    entry: float
    stop_loss: float
    take_profit: float
    outcome: str          # "win" | "loss" | "scratch" | "timeout"
    exit_price: float | None
    return_pct: float | None
    r_multiple: float | None
    holding_days: int | None
    runner_outcome: str | None = None


@dataclass
class BacktestSummary:
    ticker: str
    strategy: str
    horizon_key: str
    total_signals: int
    evaluated: int
    wins: int
    losses: int
    timeouts: int
    scratches: int
    win_rate: float | None
    avg_return_pct: float | None
    avg_r_multiple: float | None
    expectancy_r: float | None
    max_drawdown_pct: float | None
    avg_holding_days: float | None
    trades: list = field(default_factory=list)
    runner_tp2: int = 0
    runner_trail: int = 0
    runner_be: int = 0
    runner_timeout: int = 0
    avg_win_r: float | None = None


def _vectorized_entries(df: pd.DataFrame, strategy: str, horizon_key: str):
    """Single source of entry logic lives in entry_filters.py -- shared with
    the live scanner so backtest and live signals cannot drift. Kept as a
    named function here because backtest_confluence.py imports it."""
    from .entry_filters import entries_for
    return entries_for(strategy, df, horizon_key)


def _trade_plan_at(df, i, direction, strategy, horizon_key, atr_series, swing_high_series=None, swing_low_series=None, volume_ratio_series=None, entry_levels=None):
    """Sizing lives in plan_engine (single source of truth shared with live
    plans); this wrapper only picks the branch from the precomputed series.
    Parity with the original inline implementation is locked by
    tests/test_plan_engine_sizing.py."""
    from .plan_engine import (
        _atr_plan,
        _elliott_plan,
        _fibonacci_plan,
        _safe_atr_value,
        _sr_plan,
    )

    entry = float(df["Close"].iloc[i])
    atr_val = _safe_atr_value(entry, float(atr_series.iloc[i]))

    if strategy == "Fibonacci" and swing_high_series is not None:
        stop_loss, take_profit = _fibonacci_plan(
            entry, atr_val, float(swing_high_series.iloc[i]),
            float(swing_low_series.iloc[i]), direction, horizon_key)
    elif strategy == "Support/Resistance" and volume_ratio_series is not None:
        stop_loss, take_profit = _sr_plan(
            entry, float(volume_ratio_series.iloc[i]), direction, horizon_key)
    elif strategy == "Elliott Wave" and entry_levels and i in entry_levels:
        stop_loss, take_profit = _elliott_plan(
            entry, atr_val, entry_levels[i]["wave2"], direction, horizon_key)
    else:
        stop_loss, take_profit = _atr_plan(entry, atr_val, direction, horizon_key, strategy)

    return entry, stop_loss, take_profit


def run_backtest(
    ticker: str,
    df: pd.DataFrame,
    strategy: str,
    horizon_key: str,
    one_at_a_time: bool = True,
    exit_model: str = "v1",
    scale_out: bool = False,
    tp2_mode: str = "none",
) -> BacktestSummary:
    """
    Run a backtest for one (ticker, strategy, horizon) combination.

    one_at_a_time: if True (default), skip new entry signals while a prior trade
    from the same (strategy, horizon) pair is still open. This simulates realistic
    trading where you don't stack multiple overlapping positions on the same setup.

    exit_model: "v1" (default) walks the inline stop/target/BE-trigger loop
    below exactly as it always has. "v2" routes every trade through
    `plan_engine.simulate_exit` instead; the v1 loop is left completely
    untouched and remains the default until it is deleted at Task 91.
    `scale_out` and `tp2_mode` are only meaningful when `exit_model="v2"`.
    """
    min_bars = MIN_BARS[horizon_key]
    if len(df) < min_bars + 10:
        return BacktestSummary(
            ticker=ticker, strategy=strategy, horizon_key=horizon_key,
            total_signals=0, evaluated=0, wins=0, losses=0, timeouts=0, scratches=0,
            win_rate=None, avg_return_pct=None, avg_r_multiple=None,
            expectancy_r=None, max_drawdown_pct=None, avg_holding_days=None,
        )

    bullish_entries, bearish_entries = _vectorized_entries(df, strategy, horizon_key)
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

    high = df["High"].values
    low = df["Low"].values
    n = len(df)

    trades: list[BacktestTrade] = []
    total_signals = 0
    runner_counts: dict[str, int] = {}
    _lm_cache_key = None
    _lm_supports: list = []
    _lm_resistances: list = []
    if exit_model == "v2":
        from .plan_engine import (
            TRAIL_ATR_MULT, PlanStatus, TradePlanV2, select_tp2, simulate_exit,
        )

    entry_idx = np.where((bullish_entries.values | bearish_entries.values))[0]
    _open_until: int = -1  # bar index after which the current trade has exited
    for i in entry_idx:
        if i < min_bars:
            continue
        total_signals += 1
        # Deduplication: skip while a prior trade is still open (realistic capital use)
        if one_at_a_time and i <= _open_until:
            continue
        direction = "bullish" if bullish_entries.values[i] else "bearish"
        entry, stop_loss, take_profit = _trade_plan_at(
            df, i, direction, strategy, horizon_key, atr_series,
            swing_high_series, swing_low_series, volume_ratio_series, entry_levels
        )
        risk_per_share = abs(entry - stop_loss)
        if risk_per_share <= 0:
            continue

        if exit_model == "v2":
            tp2 = None
            if tp2_mode == "levels":
                cache_key = i // 5
                if cache_key != _lm_cache_key:
                    from .levels import build_level_map
                    _lm_supports, _lm_resistances = build_level_map(
                        df.iloc[:i + 1], HORIZONS[horizon_key], entry)
                    _lm_cache_key = cache_key
                tp2 = select_tp2(
                    [lv.price for lv in _lm_resistances],
                    [lv.price for lv in _lm_supports],
                    direction, entry, take_profit)

            plan = TradePlanV2(
                plan_id="bt", ticker=ticker, created_at=str(df.index[i].date()),
                source="strategy", strategy=strategy, horizon_key=horizon_key,
                direction=direction, entry_type="market", trigger_price=entry,
                entry_price=entry, expiry_bars=5, stop_loss=stop_loss,
                tp1=take_profit, tp1_fraction=0.5, tp2=tp2,
                breakeven_trigger_fraction=BREAKEVEN_TRIGGER_FRACTION,
                trail_atr_mult=TRAIL_ATR_MULT, quality_score=0, quality_breakdown=[],
                tier="C", badge="WEAK", badge_stats={}, status=PlanStatus.ACTIVE,
            )
            res = simulate_exit(df, i, plan, scale_out=scale_out)
            exit_i = res.exit_index
            exit_price = res.legs[-1]["exit_price"]
            outcome, r_multiple = res.outcome, res.r_total
            if res.runner_outcome:
                runner_counts[res.runner_outcome] = runner_counts.get(res.runner_outcome, 0) + 1

            _open_until = exit_i
            # Derived from r_multiple (the fraction-weighted blend across
            # legs), NOT from legs[-1]'s exit price alone -- a multi-leg
            # scale-out win's return spans both legs, which a single exit
            # price can't represent.
            return_pct = r_multiple * (risk_per_share / entry) * 100
            holding_days = exit_i - i

            trades.append(BacktestTrade(
                entry_date=str(df.index[i].date()), exit_date=str(df.index[exit_i].date()),
                direction=direction, entry=round(entry, 4), stop_loss=round(stop_loss, 4),
                take_profit=round(take_profit, 4), outcome=outcome,
                exit_price=round(exit_price, 4), return_pct=round(return_pct, 3),
                r_multiple=round(r_multiple, 3), holding_days=holding_days,
                runner_outcome=res.runner_outcome,
            ))
            continue

        # ---- v1 walk-forward loop (unchanged below) ----
        close_vals = df["Close"].values
        outcome, exit_price, exit_i = "timeout", None, None
        max_holding_days = HORIZONS[horizon_key]["max_holding_days"]
        end = min(i + max_holding_days, n - 1)

        target_dist = abs(take_profit - entry)
        if direction == "bullish":
            be_trigger = entry + BREAKEVEN_TRIGGER_FRACTION * target_dist
        else:
            be_trigger = entry - BREAKEVEN_TRIGGER_FRACTION * target_dist
        stop_moved = False

        for j in range(i + 1, end + 1):
            hi, lo = float(high[j]), float(low[j])
            cur_stop = entry if stop_moved else stop_loss
            if direction == "bullish":
                hit_stop = lo <= cur_stop
                hit_target = hi >= take_profit
                reached_trigger = hi >= be_trigger
            else:
                hit_stop = hi >= cur_stop
                hit_target = lo <= take_profit
                reached_trigger = lo <= be_trigger

            # Conservative ordering: stop first (original stop still governs
            # the bar that first reaches the trigger), then target. The moved
            # stop only protects bars AFTER the trigger bar.
            if hit_stop:
                outcome = "scratch" if stop_moved else "loss"
                exit_price, exit_i = cur_stop, j
                break
            if hit_target:
                outcome, exit_price, exit_i = "win", take_profit, j
                break
            if reached_trigger and not stop_moved:
                stop_moved = True

        if outcome == "timeout":
            exit_price, exit_i = float(close_vals[end]), end

        _open_until = exit_i
        sign = 1 if direction == "bullish" else -1
        return_pct = (exit_price - entry) / entry * sign * 100
        r_multiple = (exit_price - entry) * sign / risk_per_share
        holding_days = exit_i - i

        trades.append(BacktestTrade(
            entry_date=str(df.index[i].date()), exit_date=str(df.index[exit_i].date()),
            direction=direction, entry=round(entry, 4), stop_loss=round(stop_loss, 4),
            take_profit=round(take_profit, 4), outcome=outcome,
            exit_price=round(exit_price, 4), return_pct=round(return_pct, 3),
            r_multiple=round(r_multiple, 3), holding_days=holding_days,
        ))

    evaluated_trades = [t for t in trades if t.outcome in ("win", "loss")]
    wins      = [t for t in evaluated_trades if t.outcome == "win"]
    losses    = [t for t in evaluated_trades if t.outcome == "loss"]
    scratches = [t for t in trades if t.outcome == "scratch"]
    timeouts  = [t for t in trades if t.outcome == "timeout"]

    win_rate = len(wins) / len(evaluated_trades) * 100 if evaluated_trades else None
    avg_return_pct   = float(np.mean([t.return_pct   for t in evaluated_trades])) if evaluated_trades else None
    avg_r_multiple   = float(np.mean([t.r_multiple   for t in evaluated_trades])) if evaluated_trades else None
    avg_holding_days = float(np.mean([t.holding_days for t in evaluated_trades])) if evaluated_trades else None

    # Expectancy over ALL closed trades -- wins, losses, scratches (~0R) and
    # timeouts (marked to market). This is the "does it make money" number.
    expectancy_r = float(np.mean([t.r_multiple for t in trades])) if trades else None

    max_drawdown_pct = None
    if trades:
        equity = [1.0]
        for t in trades:
            equity.append(equity[-1] * (1 + t.return_pct / 100))
        equity = np.array(equity)
        running_max = np.maximum.accumulate(equity)
        drawdowns = (equity - running_max) / running_max
        max_drawdown_pct = float(drawdowns.min() * 100)

    return BacktestSummary(
        ticker=ticker, strategy=strategy, horizon_key=horizon_key,
        total_signals=total_signals, evaluated=len(evaluated_trades),
        wins=len(wins), losses=len(losses), timeouts=len(timeouts),
        scratches=len(scratches),
        win_rate=win_rate, avg_return_pct=avg_return_pct, avg_r_multiple=avg_r_multiple,
        expectancy_r=expectancy_r, max_drawdown_pct=max_drawdown_pct,
        avg_holding_days=avg_holding_days, trades=trades,
        runner_tp2=runner_counts.get("runner_tp2", 0),
        runner_trail=runner_counts.get("runner_trail", 0),
        runner_be=runner_counts.get("runner_be", 0),
        runner_timeout=runner_counts.get("runner_timeout", 0),
        avg_win_r=float(np.mean([t.r_multiple for t in wins])) if wins else None,
    )


ALL_STRATEGIES = (
    "EMA Crossover", "VWAP", "Fibonacci", "Support/Resistance", "RSI",
    "MACD", "Elliott Wave", "MA Ribbon", "Break & Retest", "RSI Divergence", "Volume Profile",
)


def run_full_backtest(ticker: str, df: pd.DataFrame) -> list[BacktestSummary]:
    """Backtest all strategies x all horizons for one ticker."""
    results = []
    for horizon_key in HORIZONS:
        for strategy in ALL_STRATEGIES:
            results.append(run_backtest(ticker, df, strategy, horizon_key))
    return results


def run_backtest_daterange(
    ticker: str,
    df: pd.DataFrame,
    strategy: str,
    horizon_key: str,
    date_from: str,
    date_to: str,
) -> BacktestSummary:
    """
    Same as run_backtest() but only evaluates signals whose entry_date falls
    within [date_from, date_to] (both inclusive, ISO format YYYY-MM-DD).
    The full df is still used for indicator warmup; the filter is applied
    after the backtest so indicator values are correct for every bar.
    """
    summary = run_backtest(ticker, df, strategy, horizon_key)
    if date_from or date_to:
        from_dt = date_from or "0000-01-01"
        to_dt   = date_to   or "9999-12-31"
        summary.trades = [
            t for t in summary.trades
            if from_dt <= t.entry_date <= to_dt
        ]
        ev       = [t for t in summary.trades if t.outcome in ("win", "loss")]
        wins     = [t for t in ev if t.outcome == "win"]
        losses   = [t for t in ev if t.outcome == "loss"]
        scratches = [t for t in summary.trades if t.outcome == "scratch"]
        timeouts  = [t for t in summary.trades if t.outcome == "timeout"]
        summary.total_signals = len(summary.trades)
        summary.evaluated     = len(ev)
        summary.wins          = len(wins)
        summary.losses        = len(losses)
        summary.timeouts      = len(timeouts)
        summary.scratches     = len(scratches)
        summary.win_rate      = len(wins) / len(ev) * 100 if ev else None
        if summary.trades:
            summary.expectancy_r   = float(np.mean([t.r_multiple for t in summary.trades]))
            equity = [1.0]
            for t in summary.trades:
                equity.append(equity[-1] * (1 + t.return_pct / 100))
            equity = np.array(equity)
            running_max = np.maximum.accumulate(equity)
            summary.max_drawdown_pct = float(((equity - running_max) / running_max).min() * 100)
        else:
            summary.expectancy_r = summary.max_drawdown_pct = None
        if ev:
            summary.avg_return_pct   = float(np.mean([t.return_pct   for t in ev]))
            summary.avg_r_multiple   = float(np.mean([t.r_multiple   for t in ev]))
            summary.avg_holding_days = float(np.mean([t.holding_days for t in ev]))
        else:
            summary.avg_return_pct = summary.avg_r_multiple = summary.avg_holding_days = None
    return summary




# Confluence backtest engine (ConfluenceTrade, run_confluence_backtest, ...)
# lives in its own sibling module, backtest_confluence.py -- imported back
# here (deliberately at the BOTTOM of this file, after ALL_STRATEGIES and
# _vectorized_entries above are already defined) so every name that used
# to live directly in this module is still importable from
# swingbot.core.backtest exactly as before the split. backtest_confluence.py
# imports ALL_STRATEGIES/_vectorized_entries back from this module, so this
# one-directional ordering (define here first, then pull in the sibling)
# avoids a circular import between the two.
from .backtest_confluence import (
    CONFLUENCE_HORIZONS, CONFLUENCE_MIN_AGREE, CONFLUENCE_RR,
    ConfluenceTrade, run_confluence_backtest, run_confluence_backtest_daterange,
    summarize_confluence_trades,
)
