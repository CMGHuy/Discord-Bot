# v88 Armed Confluence Entries (A1 measurement) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-09-15-v88-armed-confluence-entries-design.md` (A1 only; §5's A2 is not built by this plan)
**Bump:** none
**Edge:** expectancy

**Goal:** Measure, under the v72 funnel, whether confluence setups that wait for a test and a price reaction at their stop level beat setups entered immediately — and record the verdict whatever it is.

**Architecture:** One pure predicate module (`core/market/reaction.py`, shareable with a future live path), one replay module (`core/backtesting/armed_replay.py`: arm candidates → arm walk → plan at confirmation → per-cell replay → random-delay permutation), one pre-registered arithmetic module (`core/backtesting/armed_measurement.py`: 24 cells, scoring, selection, arm blobs), and one sharded, resumable script (`scripts/backtest/measure_armed_entries.py`) that feeds the existing `validate_component.py`. Code lands on a worktree branch and merges; the runs and results docs are committed on `main`.

**Tech Stack:** Python 3.11, numpy, pandas, pytest; existing `acceptance.py`, `backtest_wf.plateau_report`, `backtest_scenarios.levels_asof`/`replay_scenarios`, `plan_engine.build_confluence_plan`/`simulate_exit`.

## Global Constraints

- **Pre-registration is frozen by the spec (§3–§4).** Grid: mode `M1`/`M2` × `N` 3/5/10 × `k` 0.25/0.5 ATR × `b` 0.10/0.25 ATR = 24 cells. Reactions R1/R2/R3 fixed, not gridded. `STOP_ENTRY_EXPIRY_BARS = 2`. ATR = `indicators.atr(df, 14)`. Nothing here may be retuned after a number is seen.
- **Windows:** Run 1 = 2018-06-01..2023-12-31; selection = **2018-06-01..2020-12-31** only; fold-test years 2021/2022/2023; VALIDATION = 2024-01-01..2025-12-31, **one shot**, replay refused in code without a Stage 2 doc reading `**Overall: PASS**`.
- **Selection rule:** eligible iff volume cut <= 25% **and** `ΔExpR >= −0.01R` **and** mix-standardised `ΔWR > 0`; pick greatest `ΔExpR`, ties → greater `ΔWR`, then smaller `N`; `plateau_report` (tolerance 0.03R) on `N`, `k`, `b` each, holding the rest at the selected values; any spike disqualifies.
- **An alert** is every issued plan on either arm, including a stop-entry that ends `not_triggered`.
- **Frozen constants untouched:** `MIN_RISK_REWARD_RATIO = 1.5`, `MAX_RISK_REWARD_RATIO = 2.5`, `BREAKEVEN_TRIGGER_FRACTION = 0.5`, `tp1_fraction = 0.50`, and every clause constant in `acceptance.py` / `backtest_wf.py`.
- **No `config.Field` for any v88 knob** — they are module constants, so no v75-style search can sweep them.
- **NO-LOOKAHEAD law:** every decision at bar `j` reads bars `<= j`; every new module gets a truncation test (`full.iloc[:-1]`-style comparison).
- **`levels_asof` cache order:** its bucket map is built at the *first* bar that asks. Plan construction at a confirmation bar must reuse the cache `arm_candidates` filled walking bars in order — never a fresh or out-of-order cache.
- Worktree for Parts 1–2: `.claude/worktrees/2026-09-15-v88-armed-confluence-entries/`, branch of the same name. Part 3 runs on `main` after the merge.
- Per-task check: `python scripts/dev/testrun.py file <test file>`. The full suite runs **once**, in AR8, before the first long run.
- Long runs go to the `backtest-runner` subagent, with a flushed percent figure in a progress file that is deleted on completion.
- Never `cd` in a Bash tool command; use absolute paths or `git -C`.
- Commit messages end with the session's attribution lines.

## Parts

| File | Tasks | What |
|---|---|---|
| `_1-replay.md` | AR1–AR4 | reaction predicates, arm candidates and walk, plan at confirmation, per-cell replay |
| `_2-instrument.md` | AR5–AR8 | measurement arithmetic, random-delay permutation, the measurement script, full-suite verification + merge |
| `_3-runs.md` | AR9–AR14 | Run 1, Stage 1, Stage 0, Stage 2, Stage 3, close-out |

## Parallelisation

- **Sequential:** AR1 → AR2 → AR3 → AR4. AR2 consumes `reaction.py`; AR3 and AR4 each extend `armed_replay.py`, the file the previous task created.
- **Group 1 (parallel):** AR5 alongside AR3 or AR4 — AR5 creates only `armed_measurement.py` and its test, and consumes nothing from `armed_replay.py` except `Cell`, which AR2 introduces. So AR5 may start once AR2 is committed.
- **Sequential:** AR6 after AR4 (edits `armed_replay.py` and reuses `plan_at` and `replay_armed`'s confirmed arms). AR7 after AR5 and AR6 (the script imports both). AR8 after AR7.
- **Part 3 is strictly sequential:** each stage reads the previous stage's results doc, and AR13's replay is locked in code behind AR12's PASS.

## Outcomes (spec §4.4)

| Result | Plan ends at | A2 |
|---|---|---|
| `NO_ELIGIBLE_CELL` / `SPIKE` (AR10), MDE refused (AR11), Stage 2 FAIL (AR12) | AR14, budget intact | not written |
| Stage 3 FAIL (AR13) | AR14, budget spent | not written |
| Stage 3 PASS (AR13) | AR14 | brainstormed next |
