# TRAIN baseline — PRE-reversal control

**Date:** 2026-08-07
**Window:** TRAIN, 2020-01-01 → 2023-12-31
**Code:** `main` @ `2b7bb40` (one-trade-per-ticker + reversal merged)
**Data:** `data/backtest_cache/`, fetched 2026-08-07 — 75 tickers cached,
3 failed (`CRWV`, `SNDK`, `SPCX`: fewer than 260 bars, too recently listed)
**Command:** `python scripts/run_backtest_range.py --train`
**Raw:** `2026-08-07-train-baseline-prereversal.json` (the `.log` is gitignored)

## What this run is — and is not

**It is a control.** It measures behaviour *without* reversals.

**It does not measure the reversal feature.** `evaluate_reversal` is called
from exactly one place — the live scan loop, `scanning/engine.py:1323`. No
backtest path references it, `open_trade_for_ticker`, or any `REVERSAL_*`
setting. The backtest is trade-list based: each signal is simulated
independently to its stop/target by `simulate_exit`, then deduped when pooled
(`backtest_wf._trades_similar`). There is no per-ticker open position that a
later opposite signal could cut short, so reversals are structurally
unrepresentable here today.

Supporting them needs a position state machine over the chronological signal
stream plus the ability to truncate an exit walk at an arbitrary flip bar and
recompute its R. That is a feature in its own right, not a flag.

**Consequence:** `REVERSAL_ENABLED` currently defaults to `true` in live
trading with no backtest behind it.

## Pre-registered selection rule

Quoted from `docs/claude/backtest-methodology.md`, unchanged:

> Acceptance gates: `win_rate >= 80`, `expectancy_r > 0`, `N >= 30` (train) /
> `N >= 15` (validation), scratches+timeouts ≤ 50% of closed trades.

## Results

| Strategy | N | Win% | ExpR | MaxDD% | Scr | Scr% of closed | Excl% | Gate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| EMA Crossover | 66 | 90.9 | +0.145 | -1.9 | 13 | 16.5 | 16% | PASS |
| VWAP | 137 | 81.8 | +0.039 | -6.9 | 35 | 20.3 | 20% | PASS |
| Fibonacci | 276 | 81.2 | +0.063 | -10.9 | 100 | 26.6 | 27% | PASS |
| Support/Resistance | 270 | 81.1 | +0.032 | -7.3 | 128 | 32.2 | 32% | PASS |
| RSI | 51 | 100.0 | +0.209 | -0.8 | 29 | 36.2 | 36% | PASS |
| MACD | 145 | 83.4 | +0.054 | -8.8 | 49 | 25.3 | 25% | PASS |
| Elliott Wave | 108 | 84.3 | +0.063 | -4.5 | 44 | 28.9 | 29% | PASS |
| MA Ribbon | 254 | 81.9 | +0.033 | -7.7 | 83 | 24.6 | 25% | PASS |
| Break & Retest | 318 | 80.8 | +0.019 | -8.5 | 129 | 28.9 | 29% | PASS |
| RSI Divergence | 1604 | 81.0 | +0.058 | -31.2 | 562 | 25.9 | 26% | PASS |
| Volume Profile | 72 | 81.9 | +0.060 | -2.7 | 30 | 29.4 | 29% | PASS |

Every gate re-derived from the JSON independently of the harness's own PASS
column; all eleven pass on all four criteria.

## Observations (recorded, not fixed)

- **`Scr%` is against `closed`, not `N`.** `N` is wins+losses; `closed` adds
  scratches and timeouts. RSI reads 29 scratches on N=51, which looks like 57%
  against the wrong denominator but is 29/80 = 36.2% against the right one.
  Worth stating because the raw table invites the wrong reading.
- **RSI Divergence carries a -31.2% max drawdown** on by far the largest
  sample (N=1604, more than the other ten combined). It passes every gate,
  but that drawdown is 3x the next worst and deserves scrutiny before it is
  leaned on.
- **Break & Retest expectancy is +0.019R** — positive, so it passes, but thin
  enough that frictions or a different window could plausibly flip it.
- **RSI's 100% win rate sits on N=51** with a -0.8% max drawdown. Clean, but a
  perfect win rate is more often a sign of a small, favourably-windowed sample
  than of a perfect strategy. Treat with suspicion, not celebration.
- **Timeouts are 0 everywhere.** Consistent across all eleven strategies,
  which is either correct or means the timeout path is not firing in this
  configuration. Not investigated here.
- The run executed from the main tree, which had unrelated uncommitted chart
  edits from a concurrent session. Those modules are not on the backtest
  import path (verified before running), so the run is unaffected.

## Comparability

Any future reversal-enabled run must use **this same cache snapshot**
(fetched 2026-08-07) and the same window and frictions. If the cache is
refetched, this baseline must be re-run rather than compared across
snapshots — a different snapshot silently changes the universe (e.g. the
three tickers that failed today may cache successfully later).
