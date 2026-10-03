# v129 — Acceptance-failure exits: Implementation Plan (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read a part file whole** — pull one task: `grep -n "^### Task V129-4" -A 200 docs/superpowers/plans/2026-10-03-v129-acceptance-failure-exits_1-plan-and-exit-code.md`.

**Bump:** bot patch
**Edge:** harvest
**Spec:** [`docs/superpowers/specs/2026-10-03-v129-acceptance-failure-exits-design.md`](../specs/2026-10-03-v129-acceptance-failure-exits-design.md)

**Goal:** Judge confluence and Break & Retest trades by acceptance (a daily close beyond their level) instead of an intrabar touch, behind an inert flag, and measure both arms once through the v92 harvest gate.

**Architecture:** Two new `TradePlanV2` fields (`acceptance_level`, `acceptance_close_below`) are stamped by one new shared module, `swingbot/core/planning/acceptance_levels.py`. Both plan paths call it: live builders and `backtest._bt_plan`. `exit_sim.acceptance_exit` closes a trade at the bar close inside both exit walks. A replay library (`backtesting/acceptance_replay.py`) builds every entry once with the flag off and then re-simulates it per grid cell. A funnel module (`backtesting/acceptance_exit_funnel.py`) runs Stages 0–3. `scripts/backtest/measure_acceptance_exits.py` drives the runs.

**Tech Stack:** Python 3.11, pandas/numpy, pytest, existing `acceptance.py` / `acceptance_harvest.py` bootstrap machinery.

## Spec corrections (factual conflicts found while planning — the plan follows the code)

1. **`_trade_plan_at` builds no plan.** `backtest.py:179` returns an `(entry, stop, target)` tuple. The backtest's `TradePlanV2` is built by `_bt_plan` (`backtest.py:257`), so the Break & Retest wiring and the trap test target `_bt_plan`. The level still comes from the series `break_retest_entries` computes (V129-2).
2. **The clamp lives at `builders.py:368-383`**, not `:366-383`. `levels.py:707`/`:736` are correct.
3. **The schema path is "add".** `plans` is a hybrid table (`p2_001_plans_and_starred.py`): promoted columns plus `doc JSONB`. Neither new field is a key, index or NOT NULL column, so both ride in `doc`. No Alembic revision (`schema-evolution.md` § The four operations). V129-1 pins that with a repository round-trip test.
4. **A paired MDE already exists:** `acceptance.mde_paired(..., statistic=delta_expectancy_r)` (v100, bootstrap-SE based). The spec asks for an analytic `mde_expectancy_r_paired` from the variance of per-trade ΔR. V129-3 adds it as specified and leaves both existing functions byte-identical.
5. **The disaster stop at exactly the 2% cap differs from the clamp's 1.75%.** `_clamp_stop_to_hard_cap` lands 0.25% inside the cap (`CLAMP_HEADROOM_PCT`) because `plan_manager._step_pending` cancels a stop-entry fill past the trigger whose risk exceeds 2% (`cancelled_risk_cap`). The spec's `max(level − m·atr, entry·0.98)` is implemented verbatim. This is inert while the flag is off. If an arm passes, live stop-entry Z plans pulled to exactly 2% will be cancelled on any fill past the trigger. That is a pre-flip question, recorded in V129-16.
6. **Live exits do not run through `exit_sim`.** Live position management is `plan_manager._step_active` (it carries its own copy of the stall check, `plan_manager.py:643`). The spec lists only `exit_sim.py`, so a passing arm's flag flip would widen live stops (arm Z) with no live close exit. V129-16 therefore does **not** flip `ACCEPTANCE_EXIT_ENABLED`. On a pass it records the result, sets the inert float defaults and asks the partner. Wiring `plan_manager` would be new scope (a follow-up spec).
7. **Measurement details the spec leaves open, filled here as pre-registration (frozen in V129-8 module constants):**
   - Stage 0 `target_n` = `acceptance.project_target_n` from TRAIN closed N (TRAIN 1460 days → VALIDATION 730 days). An arm is `UNDERPOWERED` if **any** of its cells has a paired MDE > +0.10R, because Stage 1 may select any cell.
   - Stage 2 folds are the four TRAIN calendar years 2020–2023. A fold "reverses" when its ΔExpR < 0. The stage fails when more than half of the measurable folds reverse.
   - Stage 3 `not_luck` is a ticker-clustered sign-flip permutation of per-trade ΔR (n=200, seed 42). `permutation_test.py`'s circular shift would need 200 full confluence replays, which is infeasible.
   - The confluence replay uses `replay_scenarios` with live `ScanParams` (`gates=None`). Break & Retest uses `run_backtest(exit_model="v2", scale_out=True, tp2_mode="levels")`, both with `scale_out=True` (the v92 precedent).
8. **Further readings frozen while writing Parts 2–3** (also pre-registration; V129-10 copies them into the record):
   - A not-eligible arm Z plan stays in **both** arms with today's exit (ΔR = 0). It dilutes ΔExpR, which is what shipping the arm would do.
   - Arm B's entries are the baseline backtest's one-at-a-time population. An earlier acceptance exit could free the slot for an entry the baseline skipped; that entry is not simulated (the spec's "entries are shared").
   - Stage 1 eligibility is `expectancy_gain`, `win_rate_floor` and `volume` all `PASS`. A tie on the lower-95% ΔExpR goes to the earlier cell in grid order (smaller `m`, then smaller `b`).
   - Stage 2 also fails when **no** fold is measurable.
   - The Stage 3 sign-flip permutation is implemented as a per-ticker arm-label swap on ΔExpR. For a paired trade that is the sign flip of its ΔR, and it also covers entries only one arm triggered. v123 (unimplemented) plans the same instrument as `acceptance_harvest.permutation_p_expectancy`; V129-8 Step 0 reuses it if v123 landed first.
   - Stage 3 replays VALIDATION for the **selected cell only**, so no other cell is ever read on VALIDATION.
   - Universe: every watchlist ticker with a cached frame (`measure_arms.cached_universe()`), all `LEGACY_HORIZONS`. Outputs: `docs/superpowers/results/v129/`.

## Global Constraints

- Windows: TRAIN `2020-01-01..2023-12-31`, VALIDATION `2024-01-01..2025-12-31`. VALIDATION is spent **exactly once per arm**.
- Arm Z (`source == "confluence"`): grid `m ∈ {0.5, 1.0, 1.5}` × `b ∈ {0, 0.25}`, 6 cells. Arm B (Break & Retest): `b ∈ {0, 0.25}`, 2 cells. A pass in one arm never carries the other.
- Disaster stop (Z, bullish): `max(level − m·atr, entry·(1 − 0.02))`, bearish `min(level + m·atr, entry·(1 + 0.02))`. It is written into `stop_loss`, and **1R = entry → disaster stop**.
- Close threshold: `level − b·atr` (bullish; exit on a close **strictly** below it), bearish `level + b·atr` (close strictly above). Stored in `acceptance_close_below`.
- Not eligible (Z): `level` beyond the 2% cap (or on the wrong side of entry). Today's stop is kept, with no acceptance exit. These plans are counted and reported, never dropped.
- `level` and `atr` (ATR14, `_safe_atr_value` fallback) are frozen at the creating bar. **No lookahead.**
- Same-bar order: intrabar stop → target/TP1 → acceptance exit at `close[j]` (reason `"acceptance_exit"`) → stall exit → timeout. The rule is in force for the whole hold.
- A stop hit books exactly −1.0R, gaps included. Gap-throughs are disclosed, never re-priced.
- Stage 0 MDE ceiling **+0.10R** (power 0.80). `win_rate_floor` is **−2.0pp**, live in both arms. `not_luck` permutation n=200.
- `ACCEPTANCE_EXIT_ENABLED` ships **false**. `ACCEPTANCE_EXIT_ARMS` is read only when it is on. With it off, every replay output is byte-identical to the pre-v129 golden.
- No change to entries, targets, the 2% cap, sizing, alert text, charts or badges.
- Every function written or changed ends at cyclomatic complexity **< 15** (`python -m radon cc -s -n C <files>`). A legacy function ≥ 15 never gets worse.
- Per-task test runs: `python scripts/dev/testrun.py file <path>`. The full suite runs **once**, at V129-17.
- Long runs go to the `backtest-runner` agent, chunked per arm, with a percent-progress file past 15 minutes.

## Review Focus

1. **A wider Z stop changes stop-entry pending invalidation.** A component can trigger where the baseline did not, or the reverse. The rows must keep such entries and the populations must disclose them. Pinned by `test_replay_keeps_rows_where_only_a_cell_triggered` (V129-7) and `test_arm_trades_drops_untriggered_side_only` (V129-8).
2. **NaN ATR at the creating bar** (short history) must fall back to `_safe_atr_value`'s 2% of entry, never NaN into a stop. Pinned by `test_atr_at_falls_back_on_short_history` (V129-5).
3. **A level exactly on the 2% boundary is eligible; a level on the profit side of entry is not.** Pinned by `test_confluence_eligible_boundary_and_wrong_side` (V129-5).
4. **A garbage `ACCEPTANCE_EXIT_ARMS` value** (`"x, z ,"`) must parse to the valid subset, never raise. Pinned by `test_enabled_arms_parses_case_and_drops_unknown` (V129-5).
5. **Re-running Stage 3 must be refused** (one-shot budget). Pinned by `test_stage3_refuses_when_output_exists` (V129-9).

## Parts

| Part | File | Tasks |
|---|---|---|
| 1 | `2026-10-03-v129-acceptance-failure-exits_1-plan-and-exit-code.md` | V129-0 .. V129-6 (Phases 1–2) |
| 2 | `2026-10-03-v129-acceptance-failure-exits_2-replay-and-funnel.md` | V129-7 .. V129-9 (Phase 3) |
| 3 | `2026-10-03-v129-acceptance-failure-exits_3-measurement.md` | V129-10 .. V129-17 (Phases 4–5: measurement, close-out, full suite) |

## Parallelisation

Mirrors the spec's groups. V129-0 is added to Group A: it captures the flag-off golden, so it must land before any behaviour-changing task.

- **Group A (parallel):** V129-0, V129-1, V129-2, V129-3. Disjoint files: the golden test plus its fixture; `plan_types.py` plus serialization/repository tests; `entry_filters.py` plus `tests/market/test_break_retest_levels.py`; `acceptance_harvest.py` plus its test. None of them changes behaviour, and no task consumes another's symbol.
- **Group B (after V129-0, V129-1, V129-2), sequential inside:** V129-4 → V129-5. Both edit `planning/acceptance_levels.py` and its tests. V129-4 consumes the V129-1 fields and V129-2's `break_retest_level_at`. V129-5 extends V129-4's stamp functions.
- **Group C (after V129-0, V129-1):** V129-6. It touches only `exit_sim.py` and a new test file, so it runs **in parallel with Group B**.
- **Group D (after Groups B and C, and V129-3), sequential:** V129-7 → V129-8 → V129-9. V129-8 imports V129-7's `CELLS`/`M_STEPS`/`B_STEPS`. V129-9 drives both. V129-7 needs plans that carry the level (B) and the exit rule (C). V129-8 needs `mde_expectancy_r_paired`/`paired_r_deltas` (V129-3).
- **Group E (after D):** arm Z chain V129-10 → V129-11 → V129-12, and arm B chain V129-13 → V129-14 → V129-15. **Each stage consumes the previous stage's verdict JSON**, so the chains are sequential. The two chains have disjoint outputs and may interleave, but dispatch one `backtest-runner` at a time on this machine (CPU contention skews nothing, it only slows both). **One cross-chain edge:** V129-13 starts only after V129-10 Step 3, which commits the pre-registration record covering both arms.
- **Sequential tail:** V129-16 after both chains (it records both arms' verdicts). V129-17 last (the full suite, after V129-16's possible config-default edit, then the release bump and the close-out).

**Cross-plan overlap:** v123 (`2026-10-02-v123-runner-structure-exit`, unimplemented) task V123-3 also splits `_scale_out_exit_walk`, and V123-2 also edits `config.py`/`.env.example`/`tests/test_v115_strategy_work_off.py`. Whichever plan lands second rebases onto the other's split. V129-6 Step 0 says how.
