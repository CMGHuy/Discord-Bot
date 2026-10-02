# Structure-aware runner exit — implementation plan

> **For agentic workers:** Use the repo's `task-brief` and one-task implement/review cycle (superpowers:subagent-driven-development or superpowers:executing-plans). Steps use `- [ ]` for tracking; read the spec with the task.

**Goal:** Measure whether a structure-defined runner rule (`hl_trail`: trail the last confirmed post-entry swing low; `progress_stall`: exit next open on a failed higher high with contracting range and cooling volume) raises pooled ExpR over today's chandelier runner, under the v92 harvest gate.
**Architecture:** Two pure, causal functions in `planning/exit_sim.py` beside `chandelier_stop`/`runner_floor`, fed by one adapter over v121's `market/structure.py` (pivots as-is; the two ratios rebuilt as per-bar series from v121's own `true_range` and windows). Both callers use the same functions: the scale-out walk's runner phase (split into helpers first, CC 30 today) and a completed-daily-bar check in `plan_manager`. Measurement goes through the stamped arm producer and a harvest-mode `validate_component.py`. Each arm has its own serial funnel and its own budget.
**Tech Stack:** Python 3.11, pandas/numpy, pytest, `scripts/backtest/measure_arms.py`, `validate_component.py`.
**Spec:** `docs/superpowers/specs/2026-10-02-v123-runner-structure-exit-design.md` (depends on `docs/superpowers/specs/2026-10-02-v121-structure-volume-context-design.md`)
**Bump:** bot patch (only if an arm passes VALIDATION and ships default-on)
**Edge:** harvest
**Progress:** planning complete; nothing implemented or measured.

## Global constraints

- **v121 must be merged on `main` before any code task (V123-1 onward).** v123 consumes `structure.confirmed_pivots(df, k=3)` and the `range_trend_10_50` / `vol_trend_10_50` series. `k = 3` is frozen. A pivot at `i` is knowable only from `i + 3`. Only pivots with index **after the entry bar** count.
- `hl_trail`: candidate = `Low[SL*] − b × ATR14[j]` (bearish: `High[SH*] + b × ATR14[j]`). Runner stop = `max(current, candidate)` (bearish `min`), it never loosens, and the chandelier trail and runner floor keep applying. Computed at bar `j`'s close, effective from `j + 1`, with the same hit-check-then-update order the chandelier uses. Grid `b ∈ {0.00, 0.25, 0.50}`.
- `progress_stall` fires on runner bar `j` when **all four** hold: (1) a swing high is confirmed at `j` (pivot index `j − 3`, after entry); (2) its High ≤ the previous confirmed post-entry swing high; (3) `range_trend_10_50[j] ≤ c`; (4) `vol_trend_10_50[j] ≤ 1.0` (frozen). Exit at `Open[j + 1]`. If `j` is the last walked bar (`j = n − 1` or `j = end`), the rule defers to timeout. Grid `c ∈ {0.70, 0.85, 1.00}`.
- Both arms act **only after TP1**. `RUNNER_STRUCTURE_EXIT=off` (the default) leaves the walk byte-identical to today, pinned by a witness test.
- Knobs: `RUNNER_STRUCTURE_EXIT` (`off|hl_trail|progress_stall`, default `off`), `RUNNER_HL_TRAIL_ATR_BUFFER` (default `0.0`), `RUNNER_STALL_RANGE_MAX` (default `1.0`). All three are `search_class = searchable` in `swingbot/config.py`.
- The live path evaluates **completed daily bars only**, never a tick price. Paper only: no order is ever placed.
- Measurement uses the v92 harvest gate (`acceptance_harvest.py`), **not** the v72 funnel. The design is paired and exit-only. The two arms are separate budgets, run serially and never pooled. VALIDATION is 2024-01-01..2025-12-31, one shot per arm, and a missing permutation p is a FAIL. The pre-registration is committed **before** any outcome is read, and `backtest-gate` is invoked before every run.
- Not a re-run: v92 H1 (`ADAPTIVE_RUNNER_TRAIL_ENABLED`), v92 H2 (`STALL_EXIT_ENABLED`) and v104 structural stops stay closed. v123 never touches the initial stop or anything before TP1.
- Every function written or changed ends at CC < 15 (`python -m radon cc -s -n C <files>`). A refactor is never mixed with a behaviour change: separate commits, and the witness passes before and after.
- Invoke `no-lookahead` on every new function in `exit_sim.py`/`plan_manager.py`, `alert-surface` before editing wording, and `backtest-gate` before every run. Read `architecture.md`, `known-traps.md` (§ `check_bar()` is unwired), `backtest-methodology.md` and `code-complexity.md` first.
- `config.py` and `reachability.py` are shared with v122. Tasks touching them (V123-2, V123-10, V123-16) never run concurrently with v122's.
- Narrow test per task (`python scripts/dev/testrun.py file <test>`). One full suite run, in the final task.

## File map and interfaces

| File | Responsibility |
|---|---|
| `swingbot/core/planning/exit_sim.py` | `runner_structure_frame` (v121 adapter), `structural_runner_stop`, `prev_post_entry_pivot`, `progress_stall_fires`, `runner_structure_step`; `_scale_out_exit_walk` split into phase helpers, with the runner phase calling the step. |
| `swingbot/core/planning/plan_manager.py` | `entry_bar_position`, `_structure_runner_step` and its helpers on `PlanManager`, injected `daily_frame_fn`, and `_step_partial` decomposition. |
| `swingbot/config.py`, `swingbot/scan_params.py`, `.env.example` | Three knobs, search class, `_cast` validation, ScanParams fields. |
| `swingbot/core/backtesting/arms/reachability.py` | Registry rows: `outside_replay` until wired, then `reachable`. |
| `swingbot/core/presentation/instructions.py`, `swingbot/core/scanning/lifecycle_embeds.py` | Wording for the `tp1_runner_progress_stall` close. |
| `swingbot/core/backtesting/backtest_wf.py`, `acceptance_harvest.py`, `scripts/backtest/validate_component.py`, `scripts/backtest/permutation_test.py` | Harvest walk-forward gate, ΔExpR permutation p, `--gate harvest` for the walkforward/validation stages. |
| `scripts/backtest/harvest_select.py` (new) | Stage 1 fold-train selection over a grid of stamped arm files. |
| `scripts/reports/runner_headroom.py` (new) | Task 0: baseline runner capture on TRAIN replay. |

**Verified symbols** (`git grep -n` on `c5af1b92`): `exit_sim._scale_out_exit_walk` (CC 30), `chandelier_stop`, `runner_floor`, `_effective_trail_mult`, `_safe_atr_value` (targets.py), `simulate_exit`, `ExitResult`. In `plan_manager.PlanManager`: `_step_partial` (CC 19), `_close_runner`, `_days_since_entry`, `_manager()` and module-level `_live_atr`/`_plan_line`. Also `strategy_pass.completed_frame`, `session.is_regular_session`/`session_date`, `StrategyEngine.iter_trades`, `replay_scenarios`, `measure_arms.cached_universe`/`load_frame`/`_write_progress`, `acceptance.bootstrap_delta`/`delta_expectancy_r`/`_group_by_ticker`/`population_split`/`ArmTrade`, `acceptance_harvest.evaluate_harvest`, `backtest_wf.plateau_report`/`gate_win_rate`, `provenance.check_stamp`, `knobs.parse_knob`/`apply_knobs`, `tests.helpers.make_ohlcv`, `tests.planning.test_exit_sim_single._plan`, `tests.planning.test_plan_engine_model._plan`, `tests.fake_feed.FakePriceFeed`, and `tests/test_v115_strategy_work_off.FLAGS_OFF`. **Not yet on `main` (v121):** `swingbot/core/market/structure.py` with `confirmed_pivots`, `PIVOT_COLUMNS`, `true_range`, `SHORT_WINDOW`/`LONG_WINDOW`, `MIN_BARS` and `structure_features`. The names come from the uncommitted v121 plan (`docs/superpowers/plans/2026-10-02-v121-structure-volume-context.md`). V123-1 confines the pivot column names to one mapping table and re-checks them on the merged code. v121 has **no per-bar ratio series** (scalars only), so V123-1 builds them from v121's `true_range` and windows and pins them to v121's scalars.

**Spec reconciliations (read before Phase 3):**
1. The spec places the live call in "the completed-daily-bar check (the path that already updates the chandelier trail)". In code the chandelier is updated only in the intraday poll (`_step_partial`). The bar check `check_bar()` is unwired, and `known-traps.md` forbids wiring it. This plan therefore evaluates **completed daily bars from inside `_step_partial`**: each new completed bar is evaluated once per plan, from `strategy_pass.completed_frame()`, never on a tick price. That keeps the spec's intent with the one live authority.
2. The live close reason is `tp1_runner_progress_stall`, not bare `progress_stall`. `_close_runner` classifies a close as a win only when its reason starts with `tp1_`, and `performance.py` uses the same prefix. The replay leg and `runner_outcome` use `runner_progress_stall`, matching the `runner_*` vocabulary.
3. `hl_trail` stop hits keep the existing `runner_trail`/`tp1_runner_trail` strings: a structure stop is a trail stop, and about 30 files pattern-match those strings. The `structure_trail` reason appears on the live log line written when `working_stop` moves.
4. `StrategyEngine` is one-trade-at-a-time (`open_until = result.exit_index`), so an earlier runner exit can admit a later entry. Identical entries hold for paired keys only. `evaluate_harvest(..., structurally_immune_to_wr=True)` verifies immunity itself and bootstraps the floor if trades were added or removed. The outcome-flip count is `population_split()['changed']`, which must be 0. Added and removed counts are disclosed.

## Review focus

1. **A pivot confirmed at bar `j` must never move the stop that bar `j` itself is checked against.** Only `j + 1` onward may see it. V123-5 pins this with the walk's `trace`.
2. **A gap open on the stall exit bar.** When `Open[j+1]` is already below the runner stop, the stall exits at the open (the price a live trader gets), not at the stop. V123-5 pins the exit price.
3. **A stall marked after the close must not close in after-hours or premarket.** It closes only at the first regular-session tick of a later session. A restart re-derives the decision from the frame without double-closing. V123-7 tests this.
4. **The TP1 session's own bar is never evaluated.** Legacy PARTIAL plans with no parseable ACTIVE timestamp, no `runner_floor_session`, or a failing `daily_frame_fn` are skipped, never crashed. V123-7 tests each case.
5. **Short history** (fewer than 50 bars, so the v121 ratios are NaN) **never fires** `progress_stall`, and a NaN pivot never yields a stop. V123-4 tests this.

## Parallelisation

- **Group A (parallel, disjoint files, no contract):** V123-0 (`scripts/reports/` only, reads the baseline), V123-11 (`backtest_wf.py`, `acceptance_harvest.py`, `validate_component.py`, `permutation_test.py`), V123-12 (new `harvest_select.py`), V123-8 (`instructions.py`, `lifecycle_embeds.py`; the reason string is fixed by this plan, not by a symbol). Each can run beside any Phase 1–3 task.
- **Sequential spine (exit_sim.py):** V123-1 → V123-3 → V123-4 → V123-5. Every task edits `exit_sim.py`, and V123-4/5 consume V123-1's frame columns.
- **V123-2** may run beside V123-1/3/4, but never beside a v122 task (shared `config.py`/`reachability.py`). V123-5 consumes its knobs.
- **V123-6** (plan_manager refactor) may run beside the exit_sim spine (different file). **V123-7** follows V123-4 (it calls the pure functions) and V123-6 (it edits the decomposed `_step_partial`).
- **V123-9** follows V123-5 and V123-7: the parity test needs both callers. **V123-10** follows V123-9, because reachability is claimed only once both paths are wired and tested.
- **V123-13** (pre-registration) follows V123-0, V123-10, V123-11 and V123-12: it freezes their instruments and the headroom verdict.
- **Phase 5 is serial:** V123-14 (`hl_trail`) → V123-15 (`progress_stall`) → V123-16 (close-out/ship) → V123-17 (full suite). The arms are separate budgets, and the ship rule compares their VALIDATION ΔExpR.
- **If V123-0 trips the frozen 75% stop rule,** skip V123-14 and V123-15 and go straight to V123-16. If V123-0 finishes before any code task starts, ask the partner (`AskUserQuestion`) whether to build the inert code or close at once.

## Parts

| File | Phases | Tasks |
|---|---|---|
| `2026-10-02-v123-runner-structure-exit_1-replay.md` | 0 Headroom, 1 Contract and knobs, 2 Replay | V123-0 .. V123-5 |
| `2026-10-02-v123-runner-structure-exit_2-live-measurement.md` | 3 Live, 4 Instruments, 5 Measurement | V123-6 .. V123-17 |

Pull one task with `/task-brief V123-<n>` or `grep -n "^### Task V123-<n>:" -A 150 docs/superpowers/plans/2026-10-02-v123-runner-structure-exit_*.md`.
