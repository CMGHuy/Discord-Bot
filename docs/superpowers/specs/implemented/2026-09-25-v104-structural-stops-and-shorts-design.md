# v104 — Structural stops with dollar-risk sizing, and three short strategies

**Version:** ui 1.21.0 · bot 1.10.3 (at writing)
**Bump:** none until wiring; bot minor if any strategy × direction ships
**Edge:** expectancy
**Status:** Closed no-lift 2026-09-28; holdout spent: MACD bullish (FAIL, win-rate clause), Support/Resistance bullish (FAIL, bootstrap lower bound); sealed-thin: Break & Retest bullish (N=4), Volume Profile bullish (N=9) — each keeps one unspent retry once the holdout reaches 12 months (`HOLDOUT_END ≥ 2026-12-31`). All other Part A cells and all three Part B short mechanisms closed at Stage 0/1/2 on TRAIN, no shot spent. The code (stop_scope, fail-closed sizing, level-lifecycle fix, three masked short strategies) merged to `main`; `STRUCTURAL_STOP_SCOPE` stays empty. Detail: `docs/superpowers/results/2026-09-28-v104-{data,stage0,preregistration,partA,partB,holdout}.md`, `docs/claude/backtest-methodology.md`.

## Why this, and the honest prior

**Goal (the partner's words, 2026-09-25):** use the bot's strategies for both
LONG and SHORT to issue trade plans with high profit.

Two findings drive the design.

**1. The 2% price cap cut structural expectancy.** Fibonacci bullish on the
same 2020–2023 TRAIN window:

- before the cap (structural stop, capped at `max_risk_pct`): N=246, WR 35.4%,
  ExpR +0.232 (registry row, run 2026-09-10);
- after `a3a903d6` capped stops at 2%: N=288, WR 28.8%, ExpR +0.039
  (`results/2026-09-24-v101-fib-diagnostic.md`).

The populations differ, so this is strong evidence, not a controlled test.
**The partner confirmed the 2% rule exists to bound dollar risk per trade, not
price distance.** ExpR is in R, and R is the stop distance, so with
risk-normalised sizing ExpR already *is* dollars per unit of risk. The
price cap is a stricter proxy for a constraint that sizing can enforce
directly.

**2. Every short the bot has measured failed, for structural reasons.**
v93's seven bearish arms all failed, and v103's two Fibonacci bearish arms
failed too. The bearish rules mirror the long rules, but the shared gates
filter out the tape where declines pay:
- `atr_calm` rejects expanding volatility;
- `bear_regime` needs MA200 falling for 120 bars, so it fires about 6 months
  into a decline.

The universe is today's survivors, which biases shorts *against* passing. The
bearish arms stay masked. v104 adds three short mechanisms that are **not**
mirrors.

**Prior:** A is likely to lift at least the structural strategies
(Fibonacci, Support/Resistance, Elliott Wave). The ATR strategies barely
change, because `2 × ATR` rarely exceeds `max_risk_pct`. B's prior is weaker:
shorts on a survivor universe, with a 9-month holdout, may be too thin to
decide. The thin-holdout rule (§5.4) keeps that from burning shots.

Reference: `docs/strategy-types/` (all 12 strategies traced from code, with
the shared mechanics).

## Decisions taken with the partner (2026-09-25)

| Question | Decision |
|---|---|
| How shorts are executed | Short the stock directly (margin and borrow available) |
| What the 2% rule protects | Dollar risk per trade |
| Sequencing | One combined spec (A and B), B measured only under A's risk model |
| Out-of-sample window | A fresh 2026 holdout, never used before; TRAIN on 2010–2025 |
| Short mechanisms | B1 failed breakout, B2 volatility-expansion breakdown, B3 earnings gap-down drift |
| Stop-width ceiling after sizing | The horizon's `max_risk_pct` (3–11%), drop-don't-cap |
| Shorts and earnings | Measured: `hold` vs `exit_before` is a TRAIN grid axis |
| Structure | Per strategy × direction adoption (`STRUCTURAL_STOP_SCOPE`), not a global flip |

## 1. Part 0 — integrity prerequisites

### 1.1 Lifecycle ceiling fix

Today `apply_level_lifecycle` (default on) widens a stop up to the horizon's
`max_risk_pct` after the builders capped it at 2%. The live fill check cancels
such plans (`cancelled_risk_cap`), but the backtest scores them. A 2026-09-25
spot check found **22 of 83** backtest trades with an initial stop over 2%,
the worst 8.87% (`docs/claude/known-traps.md`).

Fix: the lifecycle's widening ceiling becomes `stop_ceiling(strategy,
direction, horizon)` (§2.1). Out of scope, that is 2%. **This changes today's
baseline.** Every out-of-scope number is re-measured in Part 3 as the new
reference, never compared against a pre-fix figure.

### 1.2 Cache extension and holdout freeze

Fetch `data/backtest_cache_ext` from 2010-01-01 to the last complete session
before the fetch. That date is `HOLDOUT_END`, written into the
pre-registration. `data/backtest_cache/` is never written.

### 1.3 Funnel generalisation

`scripts/backtest/fib_funnel.py` moves to `scripts/backtest/funnel.py`
unchanged; it is already grid-agnostic. v102 and v103 re-import from it, and
their tests must pass unchanged. It gains:
- the two-arm comparison Part A needs (§5.2);
- a date guard: any row dated after `TRAIN_END` read outside Stage 3 raises.

## 2. Part A — structural stops with dollar-risk sizing

### 2.1 Scope list and ceiling

- New config field `STRUCTURAL_STOP_SCOPE`: text, default `""`.
  Comma-separated `Strategy:direction` pairs, parsed case- and
  space-insensitively. Unknown names are ignored, never matched.
- Hot-reloaded like every `.env` field. Empty means byte-identical to today
  after Part 0.
- New helper `stop_ceiling(strategy, direction, horizon_key) -> (pct, mode)`:
  - out of scope: `(capped_planned_loss_pct(max_risk_pct), "cap")`, i.e. 2%;
  - in scope: `(max_risk_pct, "drop")`.

### 2.2 Builders

`_atr_plan`, `_fibonacci_plan`, `_sr_plan` and `_elliott_plan` read
`stop_ceiling` instead of computing `capped_planned_loss_pct` inline.

- **`cap` mode:** today's behaviour, pull the stop in to the ceiling.
- **`drop` mode:** a stop beyond the ceiling returns `None`, so no plan is
  built.

In scope, the stop is each strategy's own structure:
- Fibonacci: swing low − 0.25 ATR;
- Elliott Wave: wave 2 − 0.25 ATR;
- ATR family: 2 × ATR, with the opex widening;
- Support/Resistance: `sr_stop_pct`.

The v103 level stop and Fibonacci Continuation already drop, and they are
unchanged. `build_strategy_plan` must stay below CC 15, and every touched
function must end below 15.

### 2.3 Live fill check

In `plan_manager.py`, the pending-fill risk check compares the fill's planned
loss with `stop_ceiling(...)` for that plan's strategy and direction instead
of `HARD_MAX_PLANNED_LOSS_PCT`. `cancelled_risk_cap` notices show the ceiling
actually applied.

### 2.4 Fail-closed dollar-risk sizing (real-money invariant)

The partner places real resting orders from ticket share counts. An in-scope
plan with a 9% stop and a share count sized for 2% would risk 4.5× the
intended dollars.

- **Invariant:** an in-scope plan's ticket share count comes from
  `compute_position_size` in `risk_pct` mode, so that
  `shares × |entry − stop| ≤ risk budget`, with `MAX_RISK_AMOUNT_ABSOLUTE` as
  the backstop.
- **Enforcement:** if sizing for an in-scope plan is unavailable, not in
  `risk_pct` mode, or returns `None`, the plan is **not posted**. It logs an
  error and sends no alert (fail-closed).
- **Tests:**
  - an in-scope plan with a 9% stop yields shares whose risk is at or below
    budget;
  - an in-scope plan with sizing forced to `account_pct` posts nothing.

Before writing this task, the plan author must trace where the ticket's share
count comes from today (`v81` execution feed). This spec does not assume it.

## 3. Part B — three short strategies

Every B strategy:
- is short-only;
- gets its own `ENTRY_FUNCS` entry and structural sizing branch in
  `_STRUCTURAL_BRANCHES`;
- ships masked (`{"directions": ()}`);
- stays out of `backtest.ALL_STRATEGIES` until it passes;
- is always in scope (§2), since it never runs under the 2% cap.

Populations apply the live `rs_combined` laggard rule, as for every bearish
plan (backtest == live). Every rule reads closed bars ≤ t only. Each new
series gets a truncation test (`frame.iloc[:k+1]` equals the full result at
k), and the `no-lookahead` skill is loaded first.

Shared, fixed and not tuned:
- exit model v2;
- 50% off at TP1;
- trail 2.5 × ATR;
- **TP2 off**;
- TP1 by `select_structural_target` (1.5R floor, 2.5R cap).

### 3.1 B1 — Failed-breakout short ("Bull Trap")

- **Level:** `R = max(High over sr_lookback)`, shifted 1, as in
  Support/Resistance.
- **Breakout bar `b`:** `close[b] > R[b]`.
- **Entry:** the first bar `t ∈ (b, b + k]` with `close[t] < R[b]`.
  **Grid k ∈ {1, 2, 3}**, loosest 3.
- **Stop:** `max(High[b..t]) + 0.25 × ATR14`.
- **TP1 candidates:**
  - the 10-bar low before `b`;
  - `min(Low over sr_lookback)`, shifted 1;
  - the ATR ladder.
- **Filters:** `atr_floor`, `vol_ok`. No regime filter.

### 3.2 B2 — Volatility-expansion breakdown

- **Market:** SPY `close < MA50` and `MA50 < MA50[t−20]`. SPY is read through
  the existing market-context frame; the plan author confirms which column.
- **Stock:**
  - `close < S`, where `S = min(Low over sr_lookback)` shifted 1;
  - `Volume ≥ 1.5 × mean20`;
  - 63-bar return below SPY's.
- **Volatility:** `ATR14 ≥ m × mean60(ATR14)`. **Grid m ∈ {1.0, 1.2, 1.4}**,
  loosest 1.0.
- **Stop:** `S + 0.25 × ATR14`.
- **TP1 candidates:** the ATR ladder, plus zigzag swing lows below entry, using
  the horizon's `max_risk_pct` threshold.

### 3.3 B3 — Earnings gap-down drift

- **Event:** an earnings reaction session `d` with
  `Open[d] ≤ Close[d−1] × (1 − g)`. **Grid g ∈ {5%, 8%, 12%}**, loosest 5%.
- **Entry:** `close[d+1]`, only if `close[d+1] < close[d]`.
- **Stop:** `High[d] + 0.25 × ATR14`.
- **TP1 candidates:** the ATR ladder, plus swing lows as in B2.
- **Data:** v82's frozen earnings CSVs (`market_data/earnings/`, untracked,
  73 tickers). *Amended with the plan:* they already cover 2002–2026, so the
  pre-registration records a sha256 of the directory. Stage 0 still reports
  events per year, and missing coverage is recorded, never back-filled.

### 3.4 Earnings axis (B1 and B2)

`e ∈ {hold, exit_before}`. `exit_before` blocks an entry whose next earnings
reaction session is **≤ 1 bar** away. Otherwise it enters and closes the short
at the close of the bar before that session, as a per-plan hold cap.

*Amended 2026-09-25 with the plan.* The original wording blocked entries whose
report fell within `max_holding_days`. Reports come about every 63 sessions
and horizons hold up to 270, so that would have blocked almost every entry.
The forced exit, not the entry block, is the mechanism. B1 and B2 therefore have 3 × 2 = 6 cells each.
The plateau is checked along k or m **within** the same `e`.

## 4. Horizons

- Part A measures every strategy × direction the current `STRATEGY_GATES`
  admits, on its admitted horizons. That is 15 cells:
  - Fibonacci, RSI, MA Ribbon, VWAP, Support/Resistance, MACD, Volume Profile:
    bullish;
  - Break & Retest, EMA Crossover, RSI Divergence, Elliott Wave: both
    directions.
- Part B measures all ten horizons pooled.
- No horizon mask is searched.

## 5. Measurement funnel

### 5.1 Windows

- `TRAIN = 2010-01-01..2025-12-31`.
- Folds: anchored test years 2013..2025, 13 folds, training from 2010-01-01.
- `HOLDOUT = 2026-01-01..HOLDOUT_END`, one shot per candidate, ever.

### 5.2 Part A (no grid)

- **Stage 1:** the in-scope arm clears Tier 1 or Tier 2 on TRAIN, **and** its
  ExpR is above the out-of-scope arm's (re-measured after Part 0) on TRAIN.
  - Tier 1: WR ≥ 50, ExpR > 0, N ≥ 30, scratch+timeout share ≤ 50%.
  - Tier 2: ExpR > 0, and the ticker-cluster bootstrap lower bound on ExpR > 0
    (10,000 resamples, seed 42, 2.5th percentile), with the same N and
    scratch floors.
- **Stage 2:** the in-scope arm has at least 3 folds with test N ≥ 15, and at
  least ⅔ of them have ExpR > 0.
- **Stage 3 (holdout):** one run scores both arms. PASS = the assigned tier
  clears on the in-scope arm (N ≥ 15) **and** in-scope ExpR ≥ out-of-scope
  ExpR on the holdout.

### 5.3 Part B (grids)

- **Stage 0:** fewer than 30 signals at the loosest cell, per earnings
  setting, closes that setting.
- **Stage 1:** Tier 1/2 plus the plateau, as in v103: a cell counts only if
  its grid neighbours pass the same tier. The winner is the highest-ExpR
  Tier 1 plateau cell, else the highest-ExpR Tier 2 plateau cell, else none.
- **Stage 2:** per-fold reselection on 2010..Y−1 (highest ExpR with N ≥ 30).
  It clears with at least 3 folds with test N ≥ 15, and at least ⅔ of them
  ExpR > 0.
- **Stage 3:** one holdout shot at the winning cell, scored on the tier
  Stage 1 assigned.

### 5.4 Thin-holdout rule

If a Stage 3 run finds decided N < 15, the script writes **N and nothing
else**, with no WR, ExpR or rows. It records `status: "sealed-thin"` and the
shot is **unspent**. It may be run exactly once more, when the holdout reaches
12 months (`HOLDOUT_END` ≥ 2026-12-31), and the script refuses earlier. At
that point, N < 15 is a final NO-LIFT.

### 5.5 Multiple testing, stated

There are up to 18 holdout shots (15 A and 3 B). At the 2.5% one-sided
bound, about 0.45 false passes are expected across the set. The results doc
states this beside the verdicts. No correction is applied.

### 5.6 The one-shot rule

The script refuses a Stage 3 run when:
- the pre-registration or evaluate JSON is uncommitted, or
- an output for that candidate exists under any date, except a
  `sealed-thin` output that meets §5.4.

## 6. Shipping (only for passes)

- A Part A pass appends `Strategy:direction` to `STRUCTURAL_STOP_SCOPE`,
  defaulting in `config.py` and `.env.example`, with a help-text prefix naming
  the result.
- A Part B pass unmasks bearish in `STRATEGY_GATES`, freezes the winning
  cell's parameters in `DEFAULT_PARAMS`, and adds the strategy to
  `ALL_STRATEGIES` and the strategy lists (as v103's C wiring task
  specified).
- `STRATEGY_ALERTS_MODE` is never changed. Live only through `!soak`.
- Registry rows are written by the script only, labelled with the holdout
  window. *Amended with the plan:* the registry is keyed `(source, strategy,
  horizon)` with no direction. A Part A pass therefore writes that strategy's
  row only when **every** direction its live gate admits passed; otherwise no
  row is written and the methodology row records why (the v103 rule). A short
  is one direction and gets one row.
- A passing short whose winning cell is `exit_before`, and any passing B3, is
  recorded but **stays masked**. Live has no forced exit on the hold cap, and
  no live earnings context, so live would not equal the measured backtest.
  Each needs its own follow-up plan.
- The sizing-parity harness pins `STRUCTURAL_STOP_SCOPE` to `""`, exactly as
  it pins `LEVEL_LIFECYCLE_STOPS_ENABLED`.

## 7. Plan structure

One plan set, numbered v104:

| Part | Content | Runs on |
|---|---|---|
| 0 | lifecycle ceiling, cache extension, funnel move | worktree |
| 1 | `stop_ceiling`, scope list, builders, fill check, fail-closed sizing | worktree |
| 2 | B1–B3 entry functions, sizing branches, earnings axis | worktree |
| 3 | pre-registration, Stages 0–2, then Stage 3 | main, after merge |
| 4 | wiring for passes, methodology rows, close-out | worktree for wiring |

The full suite runs once, as the final task.

## 8. Not re-run, not in scope

- **Not re-run:** v31 horizon splits, v17 `REGIME_ALLOW`, v84's per-strategy
  axes, v93's mirrored bearish arms, v101, v102, and v103 A/C.
- **Out of scope:**
  - the confluence pipeline's own 2% cap, which is a different path;
  - universe expansion;
  - borrow/short-interest data;
  - TP2 or trail tuning for shorts.

## 9. Risks

- **Real money:** covered by §2.4's fail-closed invariant. This is the one
  failure mode that costs real dollars, and it is tested.
- **Gap-through risk on shorts:** dollar sizing does not cover a gap past the
  stop. It is measured through the earnings axis, and frictions stay on.
- **B3 data coverage:** it may shrink B3's TRAIN window. That is recorded, not
  patched.
- **Survivor universe:** it biases shorts against passing. A fail is recorded
  with that caveat. A pass is conservative.
