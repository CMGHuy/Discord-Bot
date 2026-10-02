# v127 Structure-Break Armed Entries Implementation Plan — index

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-10-02-v127-structure-break-armed-entries-design.md`
**Bump:** none
**Edge:** expectancy

**Goal:** Measure, under the v72 funnel with v88/v90's exact thresholds, whether confluence setups entered on a close beyond the last confirmed minor swing (optionally only after a confirmed higher low) after the zone test beat the same setups entered on the touch — and record the verdict whatever it is.

**Architecture:** A new sibling module `swingbot/core/backtesting/structure_arm.py` holds the walk (arm at the test bar, cancel on a failed zone, trigger on a structure break read from v121's `market/structure.confirmed_pivots`, expire at `i + N`), the touch-episode bookkeeping that replaces `COOLDOWN_BARS`, a per-cell replay and the random-delay permutation. It *calls* `armed_replay.arm_candidates`, `plan_at`, `make_confluence_at` and `delay_permutations` unchanged — **no refactor of `armed_replay.py` is needed** (`plan_at` reads only `cell.b` from its `Cell`, and `delay_permutations`' first-test scan returns the arm bar because v127's arm bar *is* the test bar), so v88/v90 stay byte-identical. `structure_measurement.py` adds the 12-cell grid, a selection whose plateau runs on `N` and `k` only, and the population disclosure, reusing `armed_measurement`'s `score_cell` / `Selection` / blobs / `permutation_p`. `scripts/backtest/measure_structure_arm.py` mirrors `measure_armed_entries.py` (importing its shard helpers) with `OUT_ROOT = data/v127`.

**Tech Stack:** Python 3.11, numpy, pandas, pytest; existing `armed_replay`, `armed_measurement`, `acceptance`, `backtest_wf.plateau_report`, `backtest_scenarios.replay_scenarios`/`levels_asof`, `plan_engine.simulate_exit`, `validate_component.py`; v121's `market/structure.py`.

## Parts

| File | Holds |
|---|---|
| `_0-index.md` (this file) | header, constraints, spec readings, review focus, parallelisation, outcomes |
| `_1-replay-and-grid.md` | `# Phase 1` — V127-1 walk, V127-2 replay + touch episodes, V127-3 permutation, V127-4 grid + scoring |
| `_2-script-and-runs.md` | `# Phase 2` — V127-5 script, V127-6 full suite + merge; `# Phase 3` — V127-7 Run 1, V127-8 Stage 1, V127-9 Stage 0, V127-10 Stage 2, V127-11 Stage 3, V127-12 close-out |

Pull one task with `grep -n "^### Task V127-4" -A 200 docs/superpowers/plans/2026-10-02-v127-structure-break-armed-entries_1-replay-and-grid.md`.

## Global Constraints

- **Pre-registration is frozen by the spec (§3.3, §4).** Grid: `trigger` MSB/HL × `N` 5/10/15 bars × `k` 0.25/0.5 ATR = **12 cells**, `cell_id = {trigger}-N{n}-k{k:.2f}` (`MSB-N10-k0.25`, `HL-N5-k0.50`). `b = 0.10` ATR frozen (`STOP_BUFFER_ATR`), zone-fail buffer `0.10` ATR (`ZONE_FAIL_ATR`), `STOP_ENTRY_EXPIRY_BARS = 2`, pivot order `k = 3` (v121's `PIVOT_K`, not re-tuned). ATR = `indicators.atr(df, 14)`. Nothing here may be retuned after a number is seen.
- **No `config.Field` for any v127 knob** — `TRIGGERS`, `N_GRID`, `K_GRID`, `STOP_BUFFER_ATR`, `ZONE_FAIL_ATR` stay module constants.
- **v88/v90 code paths stay byte-identical:** `swingbot/core/backtesting/armed_replay.py`, `armed_measurement.py`, `scripts/backtest/measure_armed_entries.py` and `swingbot/core/market/reaction.py` are **not modified** by any task. Their tests (`tests/backtesting/test_armed_replay.py`, `test_armed_measurement.py`, `tests/scripts/test_measure_armed_entries.py`) stay unchanged and green. V127-6 verifies with `git diff`.
- **Windows (spec §4.1):** Run 1 = 2018-06-01..2023-12-31; selection = **2018-06-01..2020-12-31** only; fold-test years 2021/2022/2023; VALIDATION = 2024-01-01..2025-12-31, **one shot**, replay refused in code without a Stage 2 doc reading `**Overall: PASS**`.
- **Selection rule (spec §4.1, unchanged from v88/v90):** eligible iff volume cut <= 25% **and** `ΔExpR >= −0.01R` **and** mix-standardised `ΔWR > 0`; greatest `ΔExpR`, ties → greater `ΔWR`, then smaller `N`; `plateau_report` (tolerance 0.03R) on `N` and on `k`, holding the others at the selected values; `trigger` categorical — both rows reported, not plateau-checked; any spike disqualifies. No threshold, margin or tolerance may be edited.
- **Clause (c) is the partner's standing win-rate constraint:** no cell with `ΔWR <= 0` can be selected at any expectancy.
- **An alert** is every issued plan on either arm, including a stop-entry that ends `not_triggered`.
- **Stage 0:** `validate_component.py --stage mde`, `--observed-days 945` (the selection window, 2018-06-01..2020-12-31 inclusive), `--target-days 730`.
- **Stage 3:** clauses 1–5; clause 6 `SKIPPED` (not a subset feature) and a SKIP never blocks; **a missing permutation p is a FAIL.** Permutation n = 200, seed 42.
- **Bespoke instrument:** `measure_arms.py` (v100) has no armed-entry engine, so every `validate_component.py` call passes `--bespoke-instrument "structure_arm: v127 armed structure-break replay (measure_arms.py has no armed-entry engine)"` (`measure_structure_arm.BESPOKE_REASON`); the reason is printed into each results doc.
- **Inspection discipline (spec §4.3):** the Stage 1 window has never been inspected for swing structure; folds 2021–23 and 2024–25 never by anyone. **No one may query any v88/v90/v121/v125 output for structure-break behaviour outside the Stage 1 window before the corresponding stage runs.** The `summary` and `select` commands read the selection window only, by construction.
- **v125 ordering:** v125's report (`volume_context_report.py` with v125 keys) must not run before this plan is committed (v125 §Scope); committing this plan satisfies that. v125's tables may not change this grid. v127 does **not** depend on v125 code.
- **Hard dependency — v121:** `swingbot/core/market/structure.py:confirmed_pivots(df, k=PIVOT_K) -> pd.DataFrame` with columns `PIVOT_COLUMNS = ("last_sh_pos", "last_sh", "prior_sh_pos", "prior_sh", "last_sl_pos", "last_sl", "prior_sl_pos", "prior_sl")`, positional indices as floats, NaN where none, truncation-stable (v121 plan Task V121-1). V127-1 Step 1 verifies it on `main` and stops `BLOCKED` otherwise.
- **NO-LOOKAHEAD:** every decision at bar `j` reads bars `<= j`. Truncation tests on the walk and on the real-pipeline replay.
- **Recorded limitations,** quoted in every results doc (`armed_measurement.LIMITATIONS`): daily-bar ordering is conservative (stop before target on the same bar); the universe is today's cached tickers (survivorship).
- **Complexity:** every new function < 15 (`python -m radon cc -s -n C <files>`); no legacy function touched.
- Worktree for Phases 1–2: `.claude/worktrees/2026-10-02-v127-structure-break-armed-entries/`, branch of the same name, from `main`. Phase 3 runs on `main` after the merge. Never `cd` in a Bash tool command; use absolute paths or `git -C`.
- Per-task check: `python scripts/dev/testrun.py file <test file>`. The full suite runs **once**, in V127-6, before the first long run. Long runs go to the `backtest-runner` subagent with flushed percent progress in `data/v127/<run>/progress.txt`, deleted on completion.
- Commit messages end with the session's attribution lines. `Bump: none`: no `VERSION.json` change anywhere in this plan.

## Spec readings fixed by this plan

The spec was approved section by section; these are the places where its text admits more than one implementation. Each is fixed here, before any number is seen, and is not revisited.

1. **Where an arm opens.** "Opens at the first bar `i` whose low comes within `k·ATR14[i]` of the scenario's level" — implemented as: the replay walks `arm_candidates` (v88's per-bar confluence scenarios, unchanged) in bar order, and an arm opens at a candidate bar `i` whose **own bar tests its level** (`reaction.is_test(bars, i, level, direction, k, ATR14[i])`). So `cand.index == i` is the test bar, the arm window is `(i, i + N]`, and `expired` resolves at `i + N`.
2. **The zone-failed cancel uses the touch low known before the bar.** Spec §3.1 writes `Close[j] < L_j − 0.10·ATR14[j]` with `L_j = min(Low[i..j])`; since `Low[j] <= Close[j]`, an inclusive `L_j` can never cancel. The cancel therefore reads `min(Low[i..j−1])` (bearish `max(High[i..j−1])`). The **stop** keeps the inclusive `L_j` exactly as spec'd (`plan_at`'s `min(level, Low[first_test..j]) − b·ATR`).
3. **`SH_j` is `confirmed_pivots(df).last_sh[j]`** — the most recent swing high confirmed by bar `j`, wherever it sits (it may predate `i`). NaN → no trigger. Bearish: `last_sl[j]`, close below it.
4. **The higher low is the last confirmed swing low:** `last_sl_pos[j] > i` and `last_sl[j] > L_j` (inclusive `L_j`). Bearish: `last_sh_pos[j] > i` and `last_sh[j] < max(High[i..j])`. A later lower low therefore voids an earlier higher low.
5. **Same-bar order:** the cancel is checked before the trigger.
6. **"The same level"** for touch episodes is `(direction, round(level, 6))` — the scenario's stop price as `arm_candidates` emits it. A level map rebuilt at a 5-bar bucket boundary that moves the price is a different level (prototype on AAPL 4w, 900 bars: 19 of 22 consecutive-bar candidates kept the exact price).
7. **Release** = some bar `t` with `terminal < t < i'` (strictly after the terminating bar, strictly before the new arm bar) closing beyond `level ± (k + 1)·ATR14[t]` in the trade's favour. An `unresolved` arm holds its direction to the end of the frame.
8. **Counts and population.** An arm that triggers is `issued` or one of v88's regate codes; both count as *triggered* and both enter the permutation population (`confirmed`). The funnel buckets every `regate_*` as `regated`.
9. **Population disclosure is windowed by arm date**, selection window only (per-ticker `<ticker>.arms.json` records), so the disclosure never reads fold years. The alert-volume ratio is `component_n / baseline_n`.
10. **The permutation reuses `armed_replay.delay_permutations` unchanged** with `Cell(n, k, 0.10)`: draws uniform on `[i, min(i + N, last bar)]`, stop-entry at the drawn bar's high, stop anchored from `i`.
11. **Horizons:** `LEGACY_HORIZONS` (10 keys, `1w` masked) — the spec's "all 10 horizons".

## Review Focus

Inputs the spec implies but its own test list does not exercise, most likely first. Each has a test in the owning task.

1. **Arm records colliding with trade rows on disk** — `measure_armed_entries.read_rows` globs `*.jsonl`; arm records written as `.jsonl` would crash `select` with `KeyError: 'arm'` (this happened in the prototype). Expect them in `<ticker>.arms.json`. Test: V127-5 `test_arm_records_are_never_read_as_trade_rows`.
2. **A bar that both fails the zone and breaks structure** — expect the cancel. Test: V127-1 `test_a_cancel_on_the_same_bar_as_a_break_wins`.
3. **NaN ATR14 early in a frame** — expect no spurious cancel inside a walk and no arm on a NaN bar. Tests: V127-1 `test_a_nan_atr_bar_neither_cancels_nor_crashes`, V127-2 `test_a_nan_atr_frame_arms_nothing`.
4. **The frame ending mid-arm** — expect `unresolved`, the direction held to the end, and identical earlier decisions on any truncation. Tests: V127-2 `test_an_arm_running_off_the_frame_is_unresolved_and_holds_the_direction`, `test_replay_never_reads_past_the_deciding_bar`.
5. **A corrupt cache CSV** in an unattended multi-hour replay — expect an empty shard and an empty arm file, not a crash. Test: V127-5 `test_replay_survives_a_corrupt_cache_csv`.

## Parallelisation

- **Sequential:** V127-1 first — creates `structure_arm.py` (`StructCell`, `TRIGGERS`, `walk_structure_arm`) and the shared fixture module that every later code task consumes.
- **Sequential:** V127-2 → V127-3. Both edit `structure_arm.py`; V127-3's tests consume V127-2's `confirmed` population shape.
- **Group 1 (parallel):** V127-4 may run alongside V127-2/V127-3 — it creates only `structure_measurement.py` and its test file (disjoint files) and consumes only V127-1's `StructCell`/`TRIGGERS`.
- **Sequential:** V127-5 after V127-3 and V127-4 (the script imports `replay_structure`, `structure_permutations` and the measurement module). The spec's "CLI skeleton in parallel" is folded into V127-5: an argparse skeleton without the replay has no test a reviewer could reject independently.
- **Sequential:** V127-6 after V127-5 (the one full-suite run, then the merge).
- **Phase 3 is strictly sequential:** V127-7 → V127-8 → V127-9 → V127-10 → V127-11 → V127-12; each stage reads the previous stage's committed results doc, and V127-11's replay is locked in code behind V127-10's `**Overall: PASS**`.

## Outcomes (spec §4.4)

| Result | Plan ends at | Live ARMED lifecycle |
|---|---|---|
| `NO_ELIGIBLE_CELL` / `SPIKE` (V127-8), MDE refused (V127-9), Stage 2 FAIL (V127-10) | V127-12, budget intact | not written |
| Stage 3 FAIL (V127-11) | V127-12, budget spent | not written |
| Stage 3 PASS (V127-11) | V127-12 | brainstormed and specced next |
