# v136 — Backtest instrument v2: wider window, realistic fills, live parity, honest statistics

**Version:** ui 1.21.1 · bot 2.0.2 (at writing)
**Bump:** bot minor per phase plan (each ships inert behind `--instrument v1`, the default); bot major at the phase-6 cutover
**Edge:** none (integrity) — the enabler for later `expectancy` work; ranked above direct ExpR work because recent closures (v104, v122, v123) were power failures, not measured negatives
**Status:** umbrella spec written 2026-10-06; no plans yet. One plan per phase, each reusing this number (`v136-…_pN`).

## Why

The partner asked for a wider training window and a more precise backtest
mechanism. A read-only sweep of the backtest code (2026-10-06) found both
problems have concrete, located causes.

**The window is not one thing.** Dates are hard-coded per script in four
regimes: 2020–2023 (`scripts/backtest/run_backtest_range.py`, the tuners,
admin jobs), 2018-06 folds (`swingbot/core/backtesting/arms/windows.py`),
2010–2023 (`measure_fib_confluence.py`) and 2010–2025 (`measure_v104.py`).
The standard funnel (`measure_arms.py`) runs the narrowest one, 2018-06..2022,
on the watchlist only, although a 2010+ cache and the point-in-time S&P 500
universe (`scripts/data/build_pit_universe.py`, v112) both exist. Windows
filter on entry date only — no purge, no embargo — so a train-fold trade can
resolve inside its test year. The default universe is today's watchlist
(survivorship). The 2026 holdout is short enough that v104's cells sealed
thin (N=4, N=9).

**The simulation is optimistic.**

- Stops never gap: a stop fills at exactly −1R and a target at exactly TP1
  even when the bar opens beyond them (`swingbot/core/planning/exit_sim.py`).
- Costs are zero on every path that matters: friction lives only in the
  legacy v1 loop; v2, `measure_arms` and the strategy/confluence engines skip
  it, and `backtest_wf` labels its v2 output "friction-adjusted" anyway.
- Market entries fill at the signal bar's close — a price the partner, who
  places resting orders at alert time, can never get.
- Two plan constructors: the backtest builds plans through `_trade_plan_at`
  / inline `TradePlanV2(...)`, live through `build_strategy_plan`. That made
  `DATA_DRIVEN_STOPS_ENABLED` and `STALL_EXIT_ENABLED` unmeasurable by
  construction (`docs/claude/backtest-methodology.md`). No replay runs the
  scan engine, so the RS gate, regime gates, dedup, confidence scoring and
  the 2% cap are invisible to every backtest.
- The bootstrap clusters on ticker, ignoring cross-ticker correlation in a
  market-wide move, and ~40 pre-registrations carry no multiple-testing
  accounting.

## Decisions (settled with the partner, 2026-10-06)

| Topic | Decision |
|---|---|
| Scope | One programme, four pieces (window contract, fill/cost realism, live parity, statistics); umbrella spec, one plan per phase |
| Out-of-sample | Research span 2010-01-01..2025-12-31 with purged folds; forward holdout from 2026-01-01, one shot per pre-registration. Unspent 2024–2025 VALIDATION budgets convert to holdout shots |
| Universe | Verdict on the point-in-time S&P 500; the watchlist is a reported slice that fails the verdict if its ExpR < 0 (when its N ≥ 30) |
| Fills | Gap-through at the open (both directions), costs on every path, next-open entry for market signals, stop-first on a bar that contains both levels |
| Re-baselining | Instrument-versioned registry; one cutover; a tier drop is **flagged for the partner**, never auto-demoted. Closed pre-registrations stay closed and are never re-run under v2 |
| Parity | Retire `_trade_plan_at` **and** build a scan-replay engine |
| Statistics | Week-clustered bootstrap gates the verdict; a pre-registration ledger with a Benjamini–Hochberg q-value is reported, not gating |
| Sequencing | Build v2 behind `--instrument`, v1 stays the default and byte-identical, one cutover at the end |

## Architecture

New package `swingbot/core/backtesting/instrument/`. Each unit has one job
and is tested alone.

| Unit | Does | Depends on |
|---|---|---|
| `contract.py` | `InstrumentSpec(version, universe, research_start, research_end, holdout_start, fold_scheme, purge, embargo_days, fill_model, cost_model)`; `resolve("v1" \| "v2")` is the **only** place window dates, universe and fill/cost rules are defined | — |
| `folds.py` | Purged, embargoed anchored walk-forward folds | contract |
| `fills.py` | `entry_fill(...)` and `exit_fill(...)` — every price-vs-level comparison the simulator makes | contract |
| `costs.py` | Commission + slippage converted to R, applied once at booking | contract |
| `cache.py` | Causal per-ticker indicator/signal frames keyed by `(instrument_version, data_hash, code_hash)` | contract |
| `replay.py` | Bar-by-bar replay of the live scan pipeline with a simulated paper book | builders, scanning, cache |
| `stats.py` | Week-clustered bootstrap; pre-registration ledger and BH q-values | — |

Cross-cutting rules:

1. **v1 is byte-identical until cutover.** `resolve("v1")` reproduces today's
   behaviour exactly, and a pinned golden run proves it at every phase.
2. **Scripts never define dates.** Every backtest script takes
   `--instrument v1|v2` and reads spans from the contract. A guard test fails
   on a date literal under `scripts/backtest/` (an allow-list covers closed,
   historical scripts that must keep reproducing their committed results).
3. **One plan constructor.** Every replay builds plans through
   `build_strategy_plan`; `_trade_plan_at` is deleted.

## 1. Window contract and folds (`contract.py`, `folds.py`)

**v2 spans.** Research span 2010-01-01..2025-12-31: every TRAIN run, grid
and fold measurement. Holdout 2026-01-01 onward, sealed: one shot per
pre-registration, read only after the research verdict is committed. The
v1 split (TRAIN 2020–2023, VALIDATION 2024–2025) survives only inside `v1`.
`backtest-methodology.md` records the conversion of unspent VALIDATION shots
(e.g. v104 Break & Retest / Volume Profile bullish) into holdout shots.

**Folds.** Anchored walk-forward, yearly test folds 2014..2025 (12 folds,
≥ 4 training years before the first). A trade belongs to a test fold by its
**entry** date. In the matching train fold:

- **Purge** — drop a train trade whose **exit** date is on or after the test
  fold's start.
- **Embargo** — drop train trades entered within `embargo_days` after the
  test fold's end; `embargo_days` = the horizon's maximum holding period from
  `strategy_types.py:HORIZONS`.

Anything tuned (a grid, a threshold) is selected on the fold's train data
only. **The verdict statistic is pooled out-of-fold ExpR**: each trade counts
once, in its own test year. A strategy with nothing tuned skips the folds;
its research-span ExpR is its out-of-fold ExpR.

**Universe.** Point-in-time S&P 500 membership checked on the **signal
date** (the existing `*_pit` mask in `run_backtest_range.py`), combined with
the point-in-time liquidity floor already there. The watchlist slice comes
from the same run. Guard: the verdict fails if the watchlist slice's ExpR
< 0 with N ≥ 30; below 30 it reports `thin` and does not block.

**Data precondition.** Phase 3 starts by verifying the OHLCV cache covers
2009-06 onward (indicator warm-up) for every PIT member, and lists gaps
rather than silently shrinking the universe.

## 2. Fills and costs (`fills.py`, `costs.py`) — v2 only

`exit_sim` stops comparing prices to levels itself and calls `fills.py`.

**Entries.**

- *Market signal* (alert after the close) → fills at the **next bar's open**.
  If that open is at or beyond the stop, the trade is cancelled
  (`cancel_reason="gap_through_stop"`) and not counted. Existing chase/cancel
  rules are evaluated against the actual fill price.
- *Limit entry* → fills when the bar trades to the limit; if the bar opens
  through the limit in the trader's favour, fills at the open.
- *Stop entry* (breakout) → fills at the trigger; if the bar opens beyond
  it, fills at the open.

**Exits.**

- Stop / breakeven / runner / chandelier stops fill at the stop, or at the
  **open** if the bar gaps through it — a loss can be worse than −1R.
- TP1 and other targets fill at the target, or at the open if the bar gaps
  through it in the trader's favour (symmetric, so the fix does not just
  move the bias).
- A bar containing both stop and target: **stop first**. On a next-open
  entry bar only the path after the open counts, and stop-first still
  applies.
- A trailing stop computed from a bar's close takes effect on the next bar.

**Costs**, applied once at booking and converted to R with the trade's own
risk per share:

| Item | v2 default |
|---|---|
| Commission | $0 / share (configurable) |
| Slippage — entries, limit and target exits | 5 bps per side |
| Slippage — stop exits (market-on-trigger) | 10 bps |

Defaults live in `contract.py`, are frozen at cutover, and any change to
them is a new instrument version.

**Scope.** One `fills`/`costs` for v2 `exit_sim`, `measure_arms`, the
strategy and confluence engines and `backtest_wf`. The legacy v1 loop's
friction code stays frozen as part of v1; the "friction-adjusted" label is
removed from `backtest_wf`'s v1 output.

## 3. Live parity and scan replay

**One constructor (phase 1).** `backtest.py` stops building `TradePlanV2(...)`
inline / through `_trade_plan_at`; every replay calls `build_strategy_plan`,
inheriting `_resolve_stall_exit_day`, data-driven stops, the reward floor
and every future builder rule. `scripts/backtest/measure_fib_diagnostic.py`
(the last outside caller) migrates; `_trade_plan_at` is deleted. A parity
test asserts that, at sampled bars, the v2 replay plan equals what
`scanning/strategy_pass.py:build_strategy_plan_at` returns for the same
completed frame.

**Scan replay (phase 5, `replay.py`).** For each session 2010..2025, run the
live scan pipeline on data **truncated to completed bars**: strategy pass,
RS gate, regime gates, dedup, confidence scoring, headroom veto (v135) and
the 2% cap. State:

- the per-date cross-section (benchmark, sectors, PIT membership), rebuilt
  each session from the cache;
- a **simulated paper book**, so the 2% cap and dedup see that date's open
  positions. Journal-dependent inputs (e.g. `days_to_half_r` for the stall
  exit) read the **replay's own simulated journal up to that date**, never
  the live journal.

Outputs: (1) a **per-plan ledger** of every plan emitted and every plan a
gate rejected, tagged with the rejecting gate — a gate's effect is emitted
vs rejected ExpR; (2) a **book-level summary** of what the alert stream would
have done. Verdicts stay per-plan pooled ExpR (§1); the book summary is
reported.

**Cost control (`cache.py`).** Recomputing indicators on a truncated frame
per date is quadratic. Causal frames are computed once per ticker, cached by
`(instrument_version, data_hash, code_hash)`, and read at bar `i`. A
**lookahead guard test** recomputes on truncated frames at random dates and
asserts equality with the cache (the no-lookahead rule as a test).

**Live parity check.** Replay the most recent N live scan dates and compare
**alert identity** (ticker, strategy, direction, entry, stop, TP1) with what
production posted. Identity only, never outcomes, so the 2026 holdout stays
sealed. Acceptance: mismatch ≤ 5% of alerts, every mismatch with a recorded
cause.

## 4. Statistics (`stats.py`)

- **Week-clustered bootstrap** — trades grouped by the ISO week of their
  entry date across all tickers; whole weeks resampled, 10,000 replicates,
  seeded. Replaces ticker clustering for every v2 verdict. The acceptance
  thresholds in `backtest-methodology.md` are unchanged; only the resampling
  unit changes.
- **Pre-registration ledger** — committed file
  `docs/superpowers/results/preregistration-ledger.jsonl`, one row per
  pre-registration: id, hypothesis, instrument version, N, ExpR, p-value,
  verdict. A git-tracked record, not a runtime store (no Postgres). Existing
  pre-registrations are backfilled from their results docs; those without a
  recorded p-value carry `p: null`. Every new verdict prints its BH q-value
  across the ledger — **reported, not gating**.

## 5. Cutover (phase 6)

1. Run the full registry under v2 with a warm cache.
2. Registry rows gain an `instrument_version` column via an Alembic revision
   (`docs/claude/schema-evolution.md`); v1 rows are kept, badges read v2.
3. A **flag report** lists every live strategy or gate whose badge tier drops
   or whose ExpR CI now crosses 0. The partner decides each one; nothing is
   auto-demoted.
4. `backtest-methodology.md` is updated: new spans, the holdout rule, the
   VALIDATION-to-holdout conversion, and the instrument-version rule (a
   change to fills, costs or spans is a new version; a closed
   pre-registration is never re-run under a new version).
5. `--instrument` default flips to `v2`.

## Phases

| # | Phase | Ships | Needs |
|---|---|---|---|
| 1 | One plan constructor | `build_strategy_plan` everywhere, `_trade_plan_at` deleted, constructor parity test, v1 golden test, `contract.py` skeleton (`InstrumentSpec` + `resolve("v1")`, fill/cost fields only) | — |
| 2 | Fills and costs | `fills.py`, `costs.py`, `resolve("v2")` fill/cost fields, `exit_sim` routed through them under v2, gap/stop-first/cancel fixtures | 1 (fills act on the one constructor's plans; needs the contract skeleton) |
| 3 | Window contract | span/universe/fold fields in `contract.py`, `folds.py`, `--instrument` on every backtest script, date-literal guard, cache-coverage check | 1 |
| 4 | Statistics | `stats.py`, ledger + backfill, week-clustered bootstrap in every v2 verdict | — (parallel with 1–3) |
| 5 | Cache + scan replay | `cache.py` with lookahead guard, `replay.py`, per-plan and book ledgers, live parity check | 1, 2, 3 |
| 6 | Cutover | full v2 registry, Alembic revision, flag report, methodology update, default flip | 1–5 |

Phases 2 and 3 can run in parallel worktrees once 1 lands (they touch
`exit_sim`/engines vs scripts/windows). Phase 4 touches nothing else and can
start immediately. Each phase plan ends with one full-suite task.

## Testing

- Unit fixtures: gap-through on stop, target and limit fills; stop-first on a
  bar containing both levels; cancel on a next-open gap through the stop;
  purge/embargo boundary trades; bootstrap cluster assignment; cost-to-R
  conversion.
- **v1 golden test** — a pinned 3-ticker v1 run is byte-identical at every
  phase.
- Constructor parity (phase 1), lookahead guard and live parity check
  (phase 5), date-literal guard (phase 3).
- Every new function < complexity 15 (`docs/claude/code-complexity.md`).

## Runtime budget

With a warm cache, a full v2 `measure_arms` over the PIT S&P 500, 2010–2025,
finishes in ≤ 60 minutes, chunked per strategy through `backtest-runner`.
A cold cache build is a one-time overnight job, run on the Hetzner VM if the
laptop is too slow (scheduled there per `working-conventions.md` § Scheduling).

## Out of scope

- Widening the **live** scan universe beyond the watchlist.
- Gating on the BH q-value.
- Intraday data or intrabar path modelling beyond stop-first.
- Re-running any closed pre-registration under v2.
