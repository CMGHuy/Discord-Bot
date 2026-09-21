Bump: bot minor
Edge: volume

# Downside coverage: inverse-instrument alerts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the book downside coverage by adding four unleveraged inverse ETFs
(PSQ, SH, RWM, DOG) to the scanned universe as ordinary symbols, so the
already-shipped **bullish** strategy arms trade them. No gate, mask, threshold or
shared table is modified. Ship only if the pre-registered Q-INV TRAIN measurement
clears on **real** inverse-ETF data, per instrument and pooled, and only once the
existing long book is **proved** unchanged.

**Architecture:** This is a *population* change, not a logic change. A new single
source of truth — `swingbot/core/market/populations.py` — answers "is this symbol
part of the inverse basket?" for every consumer. Four existing seams learn about
that population without changing behaviour for equities: the cohort registry key
(`backtesting/cohort_registry.py`), badge drift (`analytics/calibration.py`), the
open-slot accounting in `scanning/scan_run.py`, and a per-symbol horizon overlay
resolved at call time inside `market/entry_filters.entries_for`. The scan universe
gains the basket by union at `scanning/scan_run.py:192`, behind one config flag.
`STRATEGY_GATES` and `HORIZONS` are never mutated; `entry_filters.gate_override()`
is never called outside tests.

**Tech Stack:** Python 3.11, pandas/numpy, pytest, the existing
`swingbot/core/backtesting/backtest.py:run_backtest` simulator, `yfinance` via
`scripts/data/fetch_backtest_data.py`.

**Spec:** `docs/superpowers/specs/2026-09-21-v98-downside-coverage-design.md`

---

## Discrepancies found against the spec — read before Phase 1

The spec was verified line-by-line against the code on 2026-09-21. Three of its
factual premises are wrong, and two of its requirements need a re-derived shape as
a result. **None of them invalidates the proposal**; each is recorded here rather
than silently designed around, per `CLAUDE.md`.

**DISC-1 — `max_open_positions` is advisory, not binding.** The spec's Isolation
requirement 3 says "Slots are the only binding limiter". They are not a limiter at
all. The only reader of `max_open_positions` in the alert path is
`swingbot/core/scanning/scan_run.py:823-827`:

```python
open_count = trade_log.get_stats()["open"]
max_open = account_cfg.get("max_open_positions", 5)
warning = None
if open_count >= max_open:
    warning = f"{open_count} paper trades already open (limit {max_open}) — consider skipping new size here."
```

It composes a **warning string**. The alert still posts, the paper trade is still
logged, and sizing is untouched. There is no hard slot gate anywhere in
`swingbot/` (`MAX_OPEN_POSITIONS` otherwise only appears as an account default in
`core/planning/account.py:159` and a config Field at `config.py:405`).

The coupling the spec is worried about is still **real**, in a different shape: an
open inverse position inflates `open_count`, which makes that warning line appear
on *long* alerts earlier than it otherwise would. That is a visible change to a
long alert, so it violates the isolation constraint even though no price moves.
Task D4 therefore implements the requirement as (a) `open_count` for the long
warning counts **equity positions only**, and (b) a genuine concurrent cap of 4 on
the inverse population, enforced where nothing is enforced today. The sub-cap is
held outside the 30 by construction, since the two counters never share a number.

**DISC-2 — the four instruments are not tagged as ETFs.** The spec's "Why this is
executable" says "ETFs also skip earnings blackout entirely
(`market/events.py:49`)". `events.get_next_earnings_date` does short-circuit on
`is_etf(ticker)`, but `universe.is_etf()` resolves against `data/universe/etfs.json`
+ `data/universe/sp500.json`, and `data/universe/etfs.json` currently holds 17 rows
containing SPY and QQQ but **none of PSQ, SH, RWM, DOG**. Untagged, each of the
four would take a live `yf.Ticker(...).calendar` lookup per scan that can never
succeed. Task D1 adds the four rows; the earnings claim only becomes true there.

**DISC-3 — the closed-book numbers have already moved.** The spec quotes
N=158 decided, WR 62.0%, mean R +1.537. Re-derived from `data/journal.json` on
2026-09-21 *after* the spec was written: **176 entries, 161 decided, WR 62.73%,
mean R +1.6111**, still 176 bullish / 0 bearish. Nothing is wrong with the spec —
the book is **live and grows every session**, which is precisely why a frozen
absolute-N assertion is a time bomb that will go red for an innocent reason within
a day. Task D15 therefore freezes a snapshot of `(trade_id, r_realized, outcome)`
as of the task's own run and asserts **per-trade-id invariance** of that snapshot
across the flag, which is the property the spec actually wants, plus the
direction-purity assertion (every pre-existing decided trade stays `bullish`).

Two smaller shape notes, handled inside their tasks rather than here:

- `scripts/backtest/emit_cohort_registry.py:_normalize_live_trades` **drops the
  ticker** when it adapts a `trades.json` record, so `aggregate_cells` cannot see
  which population a trade belongs to. D2 carries the ticker through.
- `entry_filters.entries_for()` takes no ticker, so the per-symbol horizon overlay
  needs a new **optional** `ticker=None` keyword. All 12 existing call sites keep
  working unchanged; only the scan and backtest paths pass it. D5.

---

## Global Constraints

- **Nothing ships unless Q-INV clears.** Phase 3 does not start until Task D11
  records a PASS verdict per instrument *and* pooled. On a FAIL, D11 is the last
  implementation task: the results document is committed, Phase 3 is abandoned, and
  the plan closes to `plans/no-lift/` (`docs/claude/document-lifecycle.md`).
- **TRAIN only.** Window `2020-01-01..2023-12-31`. The VALIDATION window
  `2024-01-01..2025-12-31` is **not spent by this plan under any outcome.**
- **The arithmetic is frozen** for the whole of Phase 2: v2 exits, scale-out on,
  TP2 `levels`, frictions on. No knob is touched between runs. If nothing clears,
  **no threshold is loosened and no second grid is run on the same question.**
- **v93 is closed** (`docs/claude/backtest-methodology.md:150`). No task here
  touches a `STRATEGY_GATES` direction mask, `bear_regime`, or the RS gate.
- **Do not regenerate `swingbot/core/backtesting/cohort_registry.json`** until Task
  D2 has landed. Running `scripts/backtest/emit_cohort_registry.py` before then
  re-bands existing bullish cells against a diluted `pool_mean_r`.
- **Never mutate `STRATEGY_GATES` or `HORIZONS`**, and never call
  `entry_filters.gate_override()` outside `tests/` — it mutates a module-level dict
  in place and can leak into a concurrent live scan. D5 ships a guard test for this.
- **Do not "fix" `edge/correlation.py` into two-sided clustering.** Its
  `corr > threshold` test (`correlation.py:38`) is one-sided, so an inverse ETF at
  corr ≈ −0.9 never joins an equity cluster and cannot block a long. That is a
  favourable property to preserve, verified by an assertion in D14.
- Per task: `python scripts/dev/testrun.py file tests/<the file that task touched>.py`
  (~7s). **One** `python scripts/dev/testrun.py full`, at the very end (Task D18).
  No task other than D18 runs the full suite.
- Any backtest expected to exceed ~2 minutes is dispatched to the `backtest-runner`
  subagent so per-symbol progress never enters the main context. Anything past 15
  minutes must resolve to a percent figure in a log deleted on completion.
- Tests build OHLCV frames with `tests/conftest.py:make_ohlcv` / `make_trend_df`.
  Read conftest before writing new entry/exit tests.

## Parallelisation

- **Phase 1 (D1–D5): D1 first, then Group 1 (parallel): D2, D3, D4, D5.** D1
  introduces `populations.py`, which the other four all import — a contract
  dependency, so it is strictly first. After it lands, D2 (`cohort_registry.py` +
  `emit_cohort_registry.py`), D3 (`calibration.py` + its two callers), D4
  (`scan_run.py` + `tracking/performance.py`) and D5 (`entry_filters.py` +
  `strategy_types.py`) touch **disjoint files** and consume nothing of each
  other's. They are the genuine parallel opportunity in this plan.
- **Phase 2 (D6–D11): sequential throughout.** D6's friction model is what D9
  measures with; D7's data is what D9 reads; D8 must be **committed before** D9
  runs, or the run is not pre-registered; D9 gates D10 (folds are computed from the
  same run's trades); D10 gates D11 (the verdict needs both). This is the
  "each task consumes the previous task's payload" shape and there is no shortcut
  through it.
- **Phase 2 depends on all of Phase 1.** D9 measures the same overlay resolution
  D5 introduces and the same frictions D6 adds; measuring against code that Phase 1
  has not landed measures something the bot will not run.
- **Phase 3 (D12–D17): D12 first, then D13, then Group 2 (parallel): D14, D15,
  then D16, then D17.** D12 (config) introduces the flag D13 (`scan_run.py`) reads.
  D14 (`tests/scanning/test_inverse_differential.py`) and D15
  (`tests/tracking/test_closed_book_invariance.py`) are one new test file each,
  disjoint, neither consuming the other. D16 is a checklist over D9/D14/D15's
  outputs and must follow all three. D17 is documentation and follows the verdict
  it documents.
- **Phase 4 (D18)** runs after every prior phase that reached implementation, by
  definition of a final verification task.
- **Concurrent sessions share this working tree.** Before dispatching D2/D3/D4/D5
  in parallel, run `git worktree list` and confirm no other session holds
  `scan_run.py` or `entry_filters.py` (`docs/claude/skills-tools.md`).

---


## What lives in each part

One document, one number, three files. The header block, the goal, the
discrepancies, the global constraints and the parallelisation map are **here**
and are not repeated in the parts. Task ids do not change with the file split —
`/task-brief D9` and `grep -rn "^### Task D9" docs/superpowers/plans/` both work
without knowing which part a task landed in.

| Part | Phases | Tasks | What it covers |
|---|---|---|---|
| `_1-isolation-and-measurement.md` | 1, 2 | D1–D11 | The four isolation requirements (D1–D5), then the Q-INV pre-registration, fetch, TRAIN run, fold check and verdict (D6–D11) |
| `_2-wiring-and-verification.md` | 3, 4 | D12–D18 | Config flag, universe union, the differential test, closed-book invariance, the pre-merge gate, docs (D12–D17), and the single full-suite run (D18) |

**Part 2 does not start unless Task D11 recorded a PASS**, per instrument and
pooled. On a FAIL, Part 1's isolation work stays merged, D18 still runs over it,
and the plan closes to `plans/no-lift/`.

## Exit criteria

- Q-INV cleared on TRAIN per instrument **and** pooled, with the selection rule
  quoted verbatim in `docs/superpowers/results/2026-09-21-v98-q-inv-train.md`, and
  VALIDATION not spent (D11).
- The differential test passes with its vacuity guard green: long alerts identical
  with and without the basket (D14).
- All four isolation requirements landed, and `cohort_registry.json` was not
  regenerated during the plan (D16).
- `python scripts/dev/testrun.py full` reports `0 failed`, `0 xfailed` (D18).
