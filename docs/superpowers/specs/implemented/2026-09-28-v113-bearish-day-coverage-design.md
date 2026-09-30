# v113 — Bearish-day coverage: a 1w horizon, a downtrend overbought fade, and inverse-ETF longs

**Version:** ui 1.21.0 · bot 1.10.4 (at writing)
**Bump:** none until wiring; bot minor if any cell ships
**Edge:** volume
**Status:** Closed no-lift 2026-09-30; holdout spent: none; sealed-thin: none; A: NO-LIFT at Stage 1 (no `m` cleared a tier); B: 0/22 proceed (all fail the Tier 1 WR floor); D: NO-LIFT on TRAIN. Shipped inert on `main`: the masked `1w` horizon, the `cells` mask key, the `1w` reward floor, the `limit` entry type, the masked fade, `measure_v113.py`. Live-parity tasks V113-20 … V113-24 and the Part D wiring (V113-25) skipped; nothing went live. Results: `docs/superpowers/results/2026-09-30-v113-*.md`.

## Why this, and the honest prior

On a down-market day the bot posts almost nothing: every live strategy except
a handful of legacy cells is masked `("bullish",)`, and every attempt to earn a
bearish direction back has failed — v17 regime gate (0 of 44), v93 bearish
re-derivation (0 of 7), v101/v102/v103 Fibonacci bearish (every lower bound
negative), v104 Part A (every bearish cell NO-LIFT) and v104 Part B (three
short-only mechanisms, all NO-LIFT at Stage 1).

Every one of those changed the *entry* or the *stop* of a directional short and
kept the long side's exit shape (multi-week hold, 5%+ reward floor) on a
universe that drifted up hard across 2010-2025. Bearish win rates of ~24% say
price comes back before the far target is reached. This spec attacks the two
things never tried:

1. **The exit shape.** A new `1w` horizon (≤ 7 bars, 2% risk, 2% reward floor)
   so a short can be a quick fade instead of a multi-week bet against the drift.
2. **The instrument.** Long 1x inverse index ETFs through the existing bullish
   machinery, which produces setups on exactly the days the book is silent.

Prior: low. Shorts have failed eight times here. The value of this spec is that
a clean NO-LIFT on *these* two axes closes the remaining obvious routes.

**Not a re-run of v17.** No existing strategy is gated by market regime. `1w`
is a new horizon, pattern A is a new mechanism, and D runs existing strategies
unchanged on new tickers.

## Decisions taken with the partner (2026-09-28)

- Goal: more short-side alerts, especially on bearish days; the technique need
  not be the confluence scan.
- Mechanisms: A (downtrend overbought fade) + D (1x inverse-ETF longs).
- A's short hold lives on a **new `1w` horizon**, not inside `2w`.
- **Every existing strategy × direction is also measured on `1w`** (Part B),
  at a stricter Tier-1-only bar because of the cell count.
- D universe: SH, PSQ, RWM, DOG only (no 2x/3x — decay).
- `1w` `max_risk_pct` = 2.0; reward floor = 2.0%.
- A: fixed 2% stop, target grid {1.0, 1.25, 1.5}R.
- D is one pooled cell; a new optional `cells` mask key lets a pass unmask
  exactly one (direction, horizon).

## 1. The `1w` horizon

Added to `strategy_types.HORIZONS`. All values fixed here and in the
pre-registration; **none is ever grid-searched.**

| Key | Value |
|---|---|
| `label` | `"3-7 day swing"` |
| `ema_fast` / `ema_slow` | 5 / 8 |
| `vwap_window` | 5 |
| `fib_lookback` | 10 |
| `sr_lookback` | 5 |
| `atr_stop_multiple` | 1.5 |
| `max_risk_pct` | 2.0 |
| `sr_stop_pct` | 2.0 |
| `sr_target_min_pct` / `sr_target_max_pct` | 2.0 / 5.0 |
| `max_holding_days` | 7 |
| `rs_window` | 10 |

**A horizon-scoped reward floor for strategy plans.** (Corrected 2026-09-28,
with the plan: `MIN_REWARD_PCT` is not a global 5% floor — its config default
is 3.0 and it gates only confluence scenarios; strategy-source plans have no
reward floor today.) `1w` gets a strategy-plan floor of 2.0% via a new
`HORIZONS["1w"]["min_reward_pct"]`, applied identically by the live builder
and the backtest; every other horizon keeps exactly today's value — no floor.
The confluence path and `MIN_REWARD_PCT` are unchanged and never run `1w`. A
test pins that every existing horizon's plan output is byte-identical before
and after.

**Masked by default.** Every strategy's `STRATEGY_MASKS` entry excludes `1w`
until its cell passes. Nothing live changes by adding the horizon.

## 2. Mask schema: the `cells` key

Today `directions` and `horizons` are independent axes, so "MACD bearish only
on `1w`" is inexpressible. Add an optional key:

```python
"MACD": {"directions": ("bullish",), "horizons": (...),
         "cells": {("bearish", "1w")}}  # additionally admitted pairs
```

- Absent → today's behaviour, unchanged.
- Present → a (direction, horizon) pair is admitted if the legacy axes admit it
  **or** it is in `cells`. `entry_filters.entries_for` is the single reader.
- A passing cell adds exactly one pair; no other cell of that strategy moves.

## 3. Part A — Downtrend Overbought Fade (short-only, `1w` only)

New entry in `market/short_entries.py`, added to `SHORT_STRATEGIES`, masked
`{"directions": ()}` until it passes.

**Signal** at the close of bar *t* — uses bars ≤ *t* only:

- Downtrend: `close_t < SMA200_t` **and** `SMA200_t < SMA200_{t-20}`.
- Spike: `RSI(2)_t ≥ 90` (fixed).
- Earnings: skip if an earnings date falls within the next 7 trading days.

**Plan** — what the partner places as resting orders at alert time:

- Entry: sell limit at `close_t`, good for one bar. The backtest fills only if
  bar *t+1*'s high ≥ the limit (at the limit, or at the open if it gaps above).
- Stop: entry × 1.02.
- Target: entry − *m* × (stop − entry), **grid *m* ∈ {1.0, 1.25, 1.5}**.
- Time stop: exit at the close of the 7th bar after entry.
- Sizing: the existing v104 short sizing (fail-closed fixed dollar risk).

Break-even WR at *m* = 1.0 is 50% — exactly the Tier 1 floor. That is intended.

## 4. Part B — every strategy on `1w`

- **Cells:** the 11 legacy strategies × {bullish, bearish} = 22. Excluded, and
  staying masked: the three v104 short-only strategies, Fibonacci Continuation.
- Each cell uses the strategy's own plan builder with the §1 params. No grid:
  Stage 1 is pass/fail on the single cell.
- **Bar: Tier 1 only** (WR ≥ 50 **and** bootstrap lower bound > 0, plus every
  other badge clause). A Tier 2 pass does not ship a Part B cell — 22 tries
  make a lucky Tier 2 too likely.
- Reported per cell: cap-bind rate and floor-drop rate, so an empty cell reads
  as arithmetic, not as a market verdict.

## 5. Part D — inverse-ETF longs

- Fetch SH, PSQ, RWM, DOG into `data/backtest_cache_ext/` for
  2010-01-01..2026-09-25 and record them in the universe manifest.
- Run every **currently live** bullish (strategy, horizon) mask unchanged on
  those four tickers. Masks are not widened for D.
- **One pooled cell**, standard tiers. Per-strategy and per-ticker breakdowns
  are reported, never used to select.
- Known risk: if 2026 was mostly an up year, the holdout may be thin → sealed,
  shot unspent, retryable at 12 months (the v104 rule).

**If D passes:** the four ETFs join the live watchlist with an `inverse` tag;
the embed labels them ("Long SH = short S&P 500"); the bullish RS-leader gate
must never apply to `inverse`-tagged tickers (their RS vs SPY is structurally
negative) — pinned by a test even though that gate is off today.

## 6. Measurement funnel

`scripts/backtest/measure_v113.py`, reusing `scripts/backtest/funnel.py`
exactly as v104 does.

| Stage | Window | Rule |
|---|---|---|
| 1 | TRAIN 2010-01-01..2025-12-31, universe 74 (+4 for D) | tier per cell (Part B: Tier 1 only); A picks a plateau winner over *m* |
| 2 | 13 anchored folds on TRAIN | ≥ 2/3 of qualifying folds positive |
| 3 | Holdout 2026-01-01..2026-09-25 | **one shot per cell**; N < 15 → sealed-thin, unspent |

The pre-registration file (`results/2026-09-28-v113-preregistration.md`) —
grid, §1 params, tier bars, thin floor, windows, cell list — is committed as its
own commit **before any TRAIN number exists**.

Long runs go to `backtest-runner`, chunked per part (A, B in strategy chunks,
D).

## 7. Ship rules

- A cell ships only after passing Stage 3. Shipping = adding its pair via
  `cells` (Part B), unmasking A on `(bearish, 1w)` via `cells`, or adding the
  four ETFs to the watchlist (D).
- **A ships only with live parity** (partner decision 2026-09-28), in the same
  phase, before its unmask — conditional tasks that run only if A passes Stage 3
  (otherwise recorded as skipped): (1) live strategy frames carry the `evt_*`
  earnings columns the fade reads, from the live calendar; (2) `PlanManager`
  fills a limit entry — sell limit at `close_t`, good for the next session only,
  filling only if that session trades at or above the limit, else the plan
  expires unfilled; (3) a whole-position close at the single target
  (`tp1_fraction 1.0`: no PARTIAL, no break-even move); (4) an enforced time
  stop at the close of the 7th session after the fill, distinct from today's
  advice-only recycle notice, which keeps its behaviour for every other plan.
  Each is reached only through plan-level fields the fade's plans declare, so
  no existing plan changes — pinned by byte-identical tests written before the
  change. The alert states the resting orders (limit, stop, target, time stop).
- Registry: the existing rule holds (a strategy's row ships only when every
  admitted direction passes). A `1w` pass gets its own (strategy, `1w`) row.
- Nothing passes → everything stays masked and one row per part goes into
  `docs/claude/backtest-methodology.md`'s closed pre-registrations table, with
  why the cells died.

## 8. Build order

1. `1w` horizon, horizon-scoped reward floor, `cells` mask key, masks excluding
   `1w` — with byte-identical tests for every existing horizon.
2. Pattern A entry + plan builder, masked. NO-LOOKAHEAD tests: signal uses bars
   ≤ *t*; fill requires bar *t+1*'s high.
3. D data fetch + manifest.
4. `measure_v113.py` + pre-registration commit.
5. Runs (TRAIN → folds → holdout), results files, methodology row.
6. Unmask passing Part B cells + registry rows. If A passed: its four
   live-parity pieces (§7), then its unmask + registry row. If D passed: the
   inverse tag, RS exemption and alert label.
7. Methodology rows; full suite as the final task.

Every function written or changed stays under cyclomatic complexity 15.

## Out of scope

- 2x/3x inverse ETFs; options; pair/hedged trades.
- Market-regime gating of any existing strategy (closed, v17).
- Re-running any v93/v101-v104 bearish cell on its original horizons.
