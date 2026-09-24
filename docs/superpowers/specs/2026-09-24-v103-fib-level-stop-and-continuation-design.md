# v103 — Fibonacci under the 2% cap: level-stop (A) and measured-move continuation (C)

**Version:** ui 1.21.0 · bot 1.10.3 (at writing)
**Bump:** none until wiring; bot minor if any mechanism × direction ships
**Edge:** expectancy

## Why this, and the honest prior

**Goal (the partner's words, 2026-09-24):** Fibonacci-derived alerts should
add positive expectancy to the paper book. The VALIDATED badge is a
consequence, not the target.

**Diagnosis.** Five Fibonacci mechanisms are closed (v84 1.0 extension; v101
#1 structural stop, #2 deeper-ratio stop, #4 reclaim entry; v102 Rolling S/R
confluence). None of them touched the change that actually broke the
strategy:

- `_fibonacci_plan` stops at `swing_low − 0.25·ATR`, then caps planned loss
  at `risk_limits.HARD_MAX_PLANNED_LOSS_PCT = 2.0`. The swing extreme is
  never within 2% (v101: the cap binds 100% of plans), so **every Fibonacci
  stop is an arbitrary 2% noise stop**, unrelated to the structure.
- Before the cap, Fibonacci made **+0.232R** per trade (TRAIN 2020–23,
  N=246, v84 closed row). After it, **+0.039R** (same window, N=288, v101).
  Win rate was ~29–35% both times. The cap did not make the entries worse.
  It removed their invalidation point.
- Entries fire within `FIB_TOLERANCE_PCT = 2%` *of the swing range* of a
  level, so the tested level typically sits only 0.2–1% below price. That is
  where the thesis is actually wrong, and it fits inside the cap.

**The 2% cap is fixed** ("non-negotiable", `risk_limits.py`). This spec
works inside it.

**Prior.** Filters in this repo have typically moved win rate by a few
points. A has a mechanistic reason to do better: it restores structure
instead of filtering. C is untested. The funnel is built to reach "no"
cheaply at Stage 0.

## What is closed and must not be re-run

v101 #1/#2/#4, v102 confluence, v84 1.0 extension, v31 horizon splits, v17
`REGIME_ALLOW`. v103 adds no regime condition and no horizon mask. A differs
from v101 #2 in the part that matters: #2 moved the stop and then **let the
cap drag it back to 2%**. A **drops** any signal whose level-stop does not
fit, and never caps.

## Mechanism A — Fibonacci level-stop (a mode of `Fibonacci`)

- **Entry signal:** unchanged (`fibonacci_entries`).
- **Tested level ℓᵢ:** the ratio level (`DEFAULT_PARAMS["Fibonacci"]["ratios"]`)
  nearest `Closeᵢ`, over the same trailing `fib_lookback` swing.
- **Stop:** `ℓᵢ − b·ATR14ᵢ` for bullish, `ℓᵢ + b·ATR14ᵢ` for bearish.
- **Eligibility:** the stop must be on the losing side of entry, and
  `planned_loss_pct(entry, stop) ≤ capped_planned_loss_pct(h["max_risk_pct"])`.
  Otherwise **the signal is dropped** (in the entry function) and **no plan
  is built** (in the builder). Never capped.
- **Target:** unchanged, `select_structural_target` over `fib_target_candidates`
  in the 1.5–2.5R band, where R is now the level-stop distance.
- **Flags:** `FIB_LEVEL_STOP_ATR` (b; 0 = off) and `FIB_LEVEL_STOP_DIRECTIONS`
  (comma list; empty = off). Both off by default, so output is bit-identical
  to today. The direction scope lets A ship for one direction only.
- **Grid:** `b ∈ {0.1, 0.25, 0.5}`. 0.25 is `STRUCTURE_BUFFER_ATR`.
- **Single source:** one helper computes the level-stop series (NaN where
  ineligible). `fibonacci_entries` uses it to drop signals, and
  `_fibonacci_plan` reads the same helper at the bar (sliced to the bar) for
  both `backtest._trade_plan_at` and `build_strategy_plan`.

## Mechanism C — Fibonacci Continuation (new strategy)

Bullish at bar i (bearish mirrors it). L = the horizon's `fib_lookback`. The
structure uses bars **strictly before i**, and only the trigger bar's close
is read at i.

- **Impulse:** over window [i−L, i−1], swing low A precedes swing high H.
- **Held retracement:** R = the lowest Low after H within the window, with
  ≥ 2 bars after H. Depth d = (H − R)/(H − A), required `0.382 ≤ d ≤ d_max`.
- **Trigger:** `Closeᵢ > H`. This is the first close above H by construction:
  H is the max High of the prior L bars, so no earlier close in the window
  exceeded it. The next bar cannot re-trigger, because H then sits on bar
  i with 0 bars after it.
- **Stop:** `H − 0.25·ATR14`, under the same drop-don't-cap rule as A.
- **Targets:** measured move `R + (H−A)`, 1.272 extension `H + 0.272(H−A)`,
  1.618 extension `H + 0.618(H−A)`, through `select_structural_target` in
  the 1.5–2.5R band.
- **Gates:** the shared gates (regime, trend50, ATR floor/calm, volume).
- **Exits:** `EXIT_V2_PARAMS` gets an explicit entry equal to the table's
  missing-key defaults (trail 2.5, tp2 on), fixed before any scoring.
- **Grid:** `d_max ∈ {0.5, 0.618, 0.786}`.
- **Ships masked:** `STRATEGY_GATES["Fibonacci Continuation"] = {"directions": ()}`.
  The v93 strategy pass loops `ENTRY_FUNCS` and would otherwise build shadow
  plans for it at once. It is **not** added to `backtest.ALL_STRATEGIES`
  until it passes, because the sizing-parity tests compare every
  `ALL_STRATEGIES` member against a frozen legacy fixture that has no
  branch for it.

**Recorded finding, not fixed:** `fib_target_candidates` computes "1.272" as
`swing_high + 1.272 × range`, which is a 2.272 extension. Fixing it would move
today's Fibonacci baseline, so it stays out of scope. C uses its own correct
candidates.

## Windows, populations and funnel (pre-registered before any scoring)

- **Data:** v102's extended cache `data/backtest_cache_ext/` (2010–2025), read
  through `BACKTEST_CACHE_DIR`. The script refuses to run on the shared cache.
- **Windows:** `TRAIN_EXT = 2010-01-01..2023-12-31`; anchored folds with test
  years 2013..2023, training from 2010-01-01; `VALIDATION = 2024-01-01..2025-12-31`,
  **one shot per mechanism × direction, ever** (at most four).
- **Populations:** the live gate is used where it admits the direction, and
  `gate_override` unmasks it where it does not. Bearish populations take the v93
  laggard rule. That gives A-bullish on the live gate, A-bearish unmasked + laggard,
  C-bullish unmasked, C-bearish unmasked + laggard. Exits are v2 with scale-out,
  TP2 levels and frictions. `apply_level_lifecycle` runs as it does today.
- **Survivorship bias:** declared, not corrected. The universe is today's
  watchlist, which biases WR and ExpR upward in early years.

| Stage | Rule |
|---|---|
| 0 count (free) | Signals per cell × direction × year, plus **per-horizon** totals. At the loosest cell (A: b=0.1, C: d_max=0.786), < 30 closes that mechanism × direction |
| 1 selection | Each cell scored on both tiers. Plateau: the cell's grid neighbours pass the same tier. Winner: the highest-ExpR plateau-passing Tier 1 cell; failing that, the highest-ExpR plateau-passing Tier 2 cell; else none |
| 2 walk-forward | Per fold, the cell is re-selected on 2010..Y−1 (highest ExpR with N ≥ 30; none → unselected). ≥ 3 folds with test N ≥ 15, and ≥ 2/3 of them ExpR > 0 |
| 3 VALIDATION | One run at the winner cell, scored on the tier Stage 1 assigned, N ≥ 15 |

**Tier 1 (VALIDATED → main ledger):** WR ≥ 50, ExpR > 0, decided N ≥ 30
(≥ 15 on VALIDATION), scratch+timeout share ≤ 50%.
**Tier 2 (WEAK-live → weak ledger):** ExpR > 0, **and** the ticker-cluster
bootstrap lower bound on ExpR > 0 (`acceptance.cluster_bootstrap`, empty
baseline arm, `BOOTSTRAP_RESAMPLES = 10_000`, seed 42, lower bound = the
`100·ALPHA/2` = 2.5th percentile, the same convention `acceptance.py` uses).
N and scratch floors as Tier 1, no WR floor. VALIDATION never changes the
tier; it only passes or fails it.

## Wiring (only for passing mechanism × direction cells)

- **A:** set `FIB_LEVEL_STOP_ATR` to the winner's b and
  `FIB_LEVEL_STOP_DIRECTIONS` to the passing directions; add bearish to
  `STRATEGY_GATES["Fibonacci"]` if bearish passes; update the golden
  Fibonacci stop tests.
- **C:** set `STRATEGY_GATES` directions to the passing ones, set `d_max` to the winner,
  add C to `ALL_STRATEGIES` (and to the `!backtest`/slash choices), and extend
  the sizing-parity fixture exclusion. The registry strategy count in
  `test_registry.py` goes from 11 to 12.
- **Registry rows** only through the script's `emit-registry`: `VALIDATED` for
  Tier 1, `WEAK` for Tier 2.
- **Going live stays behind v93's `!soak` rule.** v103 never changes
  `STRATEGY_ALERTS_MODE`.
- A closed row goes into `backtest-methodology.md` whatever the outcome.

## Also fixed (small, in scope)

- `admin/queries._gate_description` renders `{"directions": ()}` as "no
  gate", which is wrong. A fully-off strategy must read "disabled".
- v102's deferred minors #3–#5, in the new script: `validation` reads the
  committed `evaluate` output and refuses a cell or direction that did not
  proceed, or an uncommitted pre-registration; it runs only the requested
  direction; `emit-registry` refuses a failing JSON and refuses to mix
  mechanisms.
- v102's grid-dependent funnel functions move into a grid-agnostic
  `scripts/backtest/fib_funnel.py`, which both scripts share. v102's tests
  stay unchanged and green.

## Testing

- A: flag-off bit-identity against an **independent** re-implementation, on
  frames that actually fire signals (the v102 review lesson); drop-don't-cap
  in both the entry function and the builder; builder stop == helper stop.
- C: a synthetic breakout fires exactly once; depth outside the bounds does not
  fire; fewer than 2 pullback bars does not fire; the target formula; masked in
  `entries_for`; no crash through `_trade_plan_at` and `build_strategy_plan`.
- Both: truncation no-lookahead tests (`full.iloc[:k+1]` equals the full result at k).
- Funnel: tier and plateau logic, fold re-selection, bootstrap determinism, and
  the refusals.
- The full suite runs once, as the plan's final task.

## Non-goals

No change to the 2% cap, to other strategies, to the shared cache or
TRAIN/VALIDATION constants, to the confluence path, or to
`fib_target_candidates`.

## Parallelisation

- **Group 1 (parallel):** A's entry side (`entry_filters.py` Fibonacci section,
  `config.py`, `.env.example`) and the admin gate fix (`admin/queries.py`) touch
  disjoint files.
- **Sequential:**
  - A's builder side comes after A's entry side, because it consumes the helper.
  - C's entry side also edits `entry_filters.py`, so it runs after A's entry side.
  - C's builder side comes after C's entry side and after A's builder side
    (both edit `builders.py` and `backtest.py`).
  - `fib_funnel.py` can go at any point before the v103 script, which consumes it.
  - Data stages run strictly in order: Stage 0 → pre-registration commit →
    Stages 1–2 → VALIDATION → wiring. Each reads the previous stage's output.
