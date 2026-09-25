# Fibonacci level-stop (A) and measured-move continuation (C) — Implementation Plan (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-09-24-v103-fib-level-stop-and-continuation-design.md`
**Bump:** none until Task V103-13; `bot minor` there only if a mechanism × direction ships
**Edge:** expectancy

**Goal:** Test two Fibonacci mechanisms that fit inside the 2% planned-loss cap, each per direction on TRAIN_EXT 2010–2023 with one VALIDATION shot per mechanism × direction on 2024–25. A puts the stop at the tested level and drops, never caps. C is a new strategy that enters a held retracement's break back through the swing extreme.

**Architecture:**
- **A** adds a vectorised `fib_level_stop_series` helper in `entry_filters.py`, read by `fibonacci_entries` to drop ineligible signals and, sliced to the bar, by `_fibonacci_plan` (shared by backtest and live) as the stop. Two flags, off by default: `FIB_LEVEL_STOP_ATR` and `FIB_LEVEL_STOP_DIRECTIONS`.
- **C** is a new `"Fibonacci Continuation"` entry function, a structure helper and its own sizing builder with correct extension targets. It ships masked in `STRATEGY_GATES`.
- `build_strategy_plan`'s strategy dispatch is table-driven first, so C lands without raising its complexity (CC 26 today).
- **Measurement** is a new `scripts/backtest/measure_fib_v103.py` on a grid-agnostic `scripts/backtest/fib_funnel.py`, which v102's script also moves onto. It adds a Tier 2 (ExpR bootstrap lower bound) beside the badge tier.

**Tech Stack:** Python 3.11+, pandas, numpy, pytest.

## Parts

| Part | File | Tasks |
|---|---|---|
| 1a — Code (worktree branch) | `2026-09-24-v103-fib-level-stop-and-continuation_1a-code.md` | V103-1 … V103-5 |
| 1b — Code (same branch) | `2026-09-24-v103-fib-level-stop-and-continuation_1b-code.md` | V103-6 … V103-8 |
| 2 — Data and measurement (on `main`) | `2026-09-24-v103-fib-level-stop-and-continuation_2-measurement.md` | V103-9 … V103-14 |

`grep -n "^### Task" docs/superpowers/plans/2026-09-24-v103-*` lists every task.

## Global Constraints

- **The 2% cap is fixed:** `risk_limits.HARD_MAX_PLANNED_LOSS_PCT = 2.0`, read through `capped_planned_loss_pct(h["max_risk_pct"])`. A level-stop or continuation stop over it **drops the signal / builds no plan. It is never capped.**
- **Windows (verbatim from the spec):** `TRAIN_EXT = 2010-01-01..2023-12-31`; test years `2013..2023`, anchored, training from 2010-01-01; `VALIDATION = 2024-01-01..2025-12-31`, **one shot per mechanism × direction, ever**.
- **Grids:** A `b ∈ {0.1, 0.25, 0.5}` (loosest 0.1; reference baseline b=0 = today's swing stop, never a candidate). C `d_max ∈ {0.5, 0.618, 0.786}` (loosest 0.786; `d_min = 0.382`, `min_pullback_bars = 2` fixed).
- **Tier 1:** WR ≥ 50, ExpR > 0, decided N ≥ 30 on TRAIN_EXT (≥ 15 on VALIDATION), scratch+timeout share ≤ 50%.
- **Tier 2:** ExpR > 0, `acceptance.cluster_bootstrap` lower bound on ExpR > 0 (empty baseline arm, `BOOTSTRAP_RESAMPLES = 10_000`, seed 42, lower bound = 2.5th percentile = `100·ALPHA/2`), plus the same N and scratch floors. No WR floor.
- **Stage 1:** a cell's grid neighbours must pass the same tier (plateau). The winner is the highest-ExpR plateau-passing Tier 1 cell, else the highest-ExpR plateau-passing Tier 2 cell, else none.
- **Stage 2:** per fold, the highest-ExpR cell with N ≥ 30 on 2010..Y−1 is selected (none means unselected). It clears when ≥ 3 folds have test N ≥ 15 and ≥ 2/3 of those have ExpR > 0.
- **Stage 0:** fewer than 30 signals at the loosest cell closes that mechanism × direction. Per-horizon counts are always reported.
- **Populations:** the live gate where it admits the direction; `gate_override(strategy, _unmasked_gates(strategy))` where it does not. The v93 laggard rule applies to every bearish population. Arithmetic: v2 exits, scale-out, TP2 levels, frictions on.
- **The shared cache `data/backtest_cache/` is never written.** Every v103 measurement runs with `BACKTEST_CACHE_DIR=data/backtest_cache_ext`.
- **Not re-run:** v101 #1/#2/#4, v102 confluence, v84 1.0 extension, v31 horizon splits, v17 `REGIME_ALLOW`. No regime condition, no horizon mask.
- **Ships inert:** both A flags off; `STRATEGY_GATES["Fibonacci Continuation"] = {"directions": ()}`; C is **not** in `backtest.ALL_STRATEGIES`. `STRATEGY_ALERTS_MODE` is never changed by this plan.
- **NO-LOOKAHEAD:** load the `no-lookahead` skill before V103-1 and V103-4. Every new series gets a truncation test (`frame.iloc[:k+1]` equals the full result at k).
- **Complexity:** every function written or changed has radon CC < 15 (`python -m radon cc -s -n C <file>`). `build_strategy_plan` (CC 26 today) must end **lower**, never higher.
- **Tests:** iterate with `python scripts/dev/testrun.py file <path>`. Use `... fast` only where a task says so (a refactor crossing files). The full suite runs once, in V103-14.
- **Green means `0 failed` and `0 xfailed`.** Never add an `xfail`.
- **No `cd` in commands.** V103-1..8 run on a worktree branch; V103-9..14 run on `main` after the merge.
- **Commit trailer:** end every commit message with `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`.

## Review Focus

1. **NaN bars inside a lookback** (a missing session in a cached CSV): the level-stop and continuation series must return NaN or False on those bars and never raise. Pinned in V103-1 (`test_nan_bars_give_nan_not_raise`) and V103-4 (`test_nan_bars_do_not_fire`).
2. **A flat range** (swing high == swing low, a halted or illiquid ticker): C's depth divides by the impulse and must not fire, warn or raise. Pinned in V103-4 (`test_flat_frame_never_fires`).
3. **A messy `FIB_LEVEL_STOP_DIRECTIONS` value** (`" Bullish , bearish "`): an operator expects case- and space-insensitive parsing. Unknown names are ignored, never matched. Pinned in V103-1 (`test_directions_parsing_is_forgiving`).
4. **A negative bar index on the live path** (`index=-1`): the at-bar readers must normalise it, so live and backtest read the same bar. Pinned in V103-1 (`test_at_bar_accepts_negative_index`) and V103-4 (`test_continuation_at_accepts_negative_index`).
5. **A second VALIDATION run for the same cell:** the script must refuse when that shot's output already exists, so "one shot ever" is enforced by the script, not only by procedure. Pinned in V103-8 (`test_validation_refuses_a_second_shot`).

## Parallelisation

- **Group 1 (parallel):** V103-1 (`entry_filters.py` Fibonacci section, `config.py`, `.env.example`), V103-2 (`builders.py` dispatch refactor), V103-6 (`admin/queries.py`), V103-7 (`scripts/backtest/fib_funnel.py`, `measure_fib_confluence.py`). Disjoint files, and none consumes another's symbols.
- **Sequential:**
  - V103-3 after V103-1 and V103-2: it consumes `fib_level_stop_at` and edits the extracted `_fib_branch`.
  - V103-4 after V103-1, because both edit `entry_filters.py`.
  - V103-5 after V103-3 and V103-4, because it edits `builders.py`/`backtest.py` again and consumes `fib_continuation_at`.
  - V103-8 after V103-5 and V103-7: it consumes both mechanisms' knobs and `fib_funnel`.
  - Part 2 is a strict chain (V103-9 → 14), and V103-10 must be committed before V103-11 measures anything.
- **Cross-plan:** v100 (arm producer) and v67/v91/v99 are live and unimplemented, and touch none of these files. If v100 has merged by V103-10, the pre-registration says v103's funnel is self-contained and does not use `validate_component.py`.
