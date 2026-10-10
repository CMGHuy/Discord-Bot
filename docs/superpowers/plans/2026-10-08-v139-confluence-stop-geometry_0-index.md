# v139 — Confluence stop geometry: Implementation Plan (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read a part file whole** — pull one task: `grep -n "^### Task V139-4" -A 200 docs/superpowers/plans/2026-10-08-v139-confluence-stop-geometry_1-geometry-and-live-path.md`.

**Bump:** none
**Edge:** expectancy — arm D removes trades (v72 funnel); arm S keeps the entries and moves stop and target geometry, so it is gated as harvest (v92)
**Spec:** [`docs/superpowers/specs/2026-10-08-v139-confluence-stop-geometry-design.md`](../specs/2026-10-08-v139-confluence-stop-geometry-design.md)

**Goal:** Give a confluence plan whose structural stop sits beyond the 2% cap one of two honest geometries behind inert knobs — keep the structural stop up to a ceiling `c` and size to dollar risk (arm S), or issue no plan beyond `c` (arm D) — and measure each arm once on its own budget.

**Architecture:** One new helper, `builders.confluence_stop_geometry`, replaces the bare `_clamp_stop_to_hard_cap` call in `build_confluence_plan` and returns `(stop_loss, stop_ceiling_pct)` or `None` (the arm D drop). An arm S plan stores its ceiling in a new `TradePlanV2.stop_ceiling_pct` field (doc JSONB, no Alembic). `stop_scope.plan_stop_ceiling` returns that stored ceiling, which `plan_manager`'s fill and active checks already read. `analyze.attach_plan_v2` is routed through the same ceiling. Arm D is measured with the standard v72 funnel (`measure_arms.py` + `validate_component.py`). Arm S is measured with a paired replay (`backtesting/confluence_stop_replay.py`), a funnel (`backtesting/confluence_stop_funnel.py`, the v92 harvest gate with the ISO-week bootstrap) and a stage driver (`scripts/backtest/measure_confluence_stop.py`), modelled on v129.

**Tech Stack:** Python 3.11, pandas/numpy, pytest, the existing `acceptance.py` / `acceptance_harvest.py` / `acceptance_exit_funnel.py` machinery, `measure_arms.py` / `validate_component.py` / `permutation_test.py`.

## Spec corrections (the code disagrees with the spec; the plan follows the code)

1. **The helper needs the target candidates.** The spec's signature is `confluence_stop_geometry(entry, level, is_bull, params)`, and it puts "the arm-S target re-selection and rollback" inside the helper. Rollback is decided by `select_structural_target`, which needs the candidate levels. Those are computed in `build_confluence_plan` *after* the clamp today (`builders.py:460-463`). The plan's signature is `confluence_stop_geometry(entry, level, is_bull, candidates, params)`. The "drop sentinel" is `None`.
2. **`build_confluence_plan` cannot take the drop branch at C(14).** One added branch makes it 15. V139-5 extracts `_confluence_candidates(scenario, level_map)` (removes two decision points), so the function ends at 13 with the drop branch in place. A refactor that changes no behaviour, pinned by the flag-off golden.
3. **`exit_sim.py:567` is not a confluence fill check.** It sits in `_compression_fill`, which only the compression short reaches. A confluence replay never cancels a fill for risk. So `plan_stop_ceiling` matters for confluence only on the **live** path: `plan_manager._step_pending` (`plan_manager.py:731`, `cancelled_risk_cap`) and `_warn_legacy_open_risk` (`:551`). The replay rows disclose `fill_beyond_ceiling` instead: fills the live path would have cancelled.
4. **`analyze.attach_plan_v2` rejects every plan over 2% directly** (`analyze.py:381`, `> HARD_MAX_PLANNED_LOSS_PCT + 1e-9`, reason `risk_cap`). It does not read `plan_stop_ceiling`, so every live arm S plan would be rejected. V139-7 routes that check through `plan_stop_ceiling(plan)`, which is byte-identical while `stop_ceiling_pct` is `None`. That check is the spec's own "live wiring through `plan_stop_ceiling`", not new scope. V139-7 also makes `attach_plan_v2` the call site the spec implies for two things: `risk_sizing_ok` (its only call site today is `strategy_pass.py:255`), and the `stop_beyond_confluence_ceiling` reason (today every `None` plan is recorded as `no_qualifying_target`).
5. **`risk_sizing_ok` is called only for plans with a stored ceiling.** A confluence plan's `strategy` is its primary attribution (`primary_strategy_for`). `in_scope()` can match that name: `SHORT_STRATEGIES` are always in scope, and so is any `STRUCTURAL_STOP_SCOPE` pair. Calling `risk_sizing_ok` on every confluence plan would change today's live behaviour. `attach_plan_v2` therefore calls it only when `plan.stop_ceiling_pct is not None`.
6. **A gap through the stop books exactly −1.0R in the replay.** The spec says "books its real loss beyond −1R". `exit_sim` books every stop hit at −1.0R (`exit_sim.py:203`, `:549-551`), gaps included, as v129 recorded. The gap-through count is disclosed, never re-priced.
7. **"Set the default to the selected `c`, still inert behind a 0 default" cannot both hold.** The knob *is* the ceiling. There is no master flag (v129 had `ACCEPTANCE_EXIT_ENABLED`), so a default of `c` would be live. On a pass the default **stays 0**. The selected `c` is written into the result record, the Field `help` and the `.env.example` comment, and the partner is asked (V139-16). So `Bump: none` holds in every outcome of this plan.
8. **Arm S never adds or removes a plan.** `select_structural_target` returns `None` only when no candidate clears `min_rr × risk`. The structural risk is larger than the clamped one, so a target that qualifies at the structural risk also qualifies at the clamped risk. A rollback *is* today's plan. So plan existence, the per-direction cooldown and the `(signal index, direction)` sequence are identical in the baseline and every cell. V139-8 asserts this and raises if it breaks. Arm S changes only stops, targets, and therefore stop-entry invalidation. Arm D can **add** entries: a dropped plan never sets `last_accepted`, so a later bar inside the 5-bar cooldown can issue. The population split's `added` > 0 then makes clause 6 `SKIPPED` (`acceptance._clause_mechanism`). That is disclosed, not rescued.
9. **The measurement universe.** `measure_arms.cached_universe()` reads the Postgres watchlist (`run_backtest_range._tickers_for_run` → `load_watchlist`). A worktree cannot reach it. v129 hit this and the partner approved the cache listing (commit `5c7f766c`). `validate_component._full_universe` and `permutation_test._full_universe` call the same function for their stamp gates. So V139-3 adds one switch, `MEASURE_ARMS_UNIVERSE=cache`, that all three scripts honour (an environment variable, because `permutation_test` imports `measure_arms` under a second module name). Every measurement command sets it together with `BACKTEST_CACHE_DIR`. The pre-registration records it. **Partner approved the cache listing for v139 on 2026-10-08** (asked after the plan was written), so V139-3 needs no further question.
10. **Measurement details the spec leaves open, frozen here as pre-registration (V139-11 copies them into the record):**
    - Arm S uses v129's windows and constants, imported from `acceptance_exit_funnel`: TRAIN `2020-01-01..2023-12-31`, VALIDATION `2024-01-01..2025-12-31`, `target_n` projected 1460 → 730 days, Stage 0 paired MDE (`mde_expectancy_r_paired`, ticker design effect, as v129), four calendar-year folds, `not_luck` = per-ticker arm-label swap, n = 200, seed 42. Only the bootstrap cluster differs: `cluster="week"` (instrument v2), as the spec requires.
    - Arm S Stage 1: eligible = `expectancy_gain`, `win_rate_floor` (−2.0pp) and `volume` all `PASS`. Selected = the eligible cell with the highest lower-95% ΔExpR whose ±1-step neighbours in `c` are all eligible. A tie goes to the smaller `c`.
    - Arm S Stage −1 is the census (V139-8/9). It closes `refused:zero-diff` when no cell changes any plan. Arm D's Stage −1 **gate** is the standard pilot reachability (`measure_arms.py --stage pilot` at `c = 3.0`, the cell that drops most). The census numbers for arm D are disclosure.
    - Arm D is the standard v72 funnel, instrument v1 (ticker bootstrap), `--gate win_rate` (all six clauses at Stage 3). Its windows are `windows.STAGES`: pilot, fold-train selection 2018-06-01..2022-12-31, walk-forward test years 2021/2022/2023, VALIDATION 2024–2025. Its population is the pooled book (`DEFAULT_ENGINES` = confluence + strategy; the knob reaches only confluence rows). So clause 3's volume cut is measured against the pooled book, and the confluence-only cut is disclosed beside it.
    - `validate_component.py --stage selection` labels its plateau report `PULLBACK_DRYUP_MAX_RATIO` (`select_cell(cells, "PULLBACK_DRYUP_MAX_RATIO")`). The label is cosmetic: `plateau_report` uses it only as the printed parameter name. It changes no verdict. The record says so.
    - An arm S cell that changes no plan in the census (an identical adjacent pair) is reported **before** Stage 0. V139-11 stops and asks the partner rather than spending outcomes on a degenerate axis (v129's `m` axis was silently degenerate).
11. **Admission bounds `d` per horizon at `max(MAX_STOP_LOSS_PCT, max_risk_pct)`** (`gating.scenario_gate_inputs`). Some horizons admit at most 2.0 or 3.0. There, cells above the admission ceiling change nothing more than the admission ceiling does. The census shows this per horizon. Not a defect.

## Global Constraints

- Windows: arm S TRAIN `2020-01-01..2023-12-31`, VALIDATION `2024-01-01..2025-12-31`. Arm D: `windows.STAGES` (pilot `2018-06-01..2020-12-31`, selection `2018-06-01..2022-12-31`, walk-forward test years 2021–2023, validation `2024-01-01..2025-12-31`). VALIDATION is spent **exactly once per arm**. A pass in one arm never carries the other, and the two are never pooled.
- Ceiling grid `c ∈ {3.0, 4.0, 5.0}` percent, shared by both arms. Headroom `CLAMP_HEADROOM_PCT` = 0.25.
- Clamped plan: `source == "confluence"`, the scenario stop is on the stop side of entry, and `planned_loss_pct(entry, scenario.stop_loss) > HARD_MAX_PLANNED_LOSS_PCT` (2.0). `d` = that distance. Every other plan is untouched in both arms.
- Arm S: `d ≤ c − 0.25` → `stop_loss = level`, TP1/TP2 re-selected against the structural risk, `stop_ceiling_pct = c`. No RR-band target at the structural risk → today's clamped plan (rollback, counted). `d > c − 0.25` → today's clamped plan. Sizing `risk_pct`, `risk_sizing_ok` must pass.
- Arm D: `d > c` → no plan, reason `stop_beyond_confluence_ceiling`. `d ≤ c` → today's clamped plan.
- Boundaries carry a `1e-9` tolerance (`STOP_GEOMETRY_TOL`): `d` exactly at `c − 0.25` is arm S; `d` exactly at `c` is kept by arm D.
- With both knobs set, arm S applies first; arm D then drops what is beyond `c_D`. Measurement never sets both.
- `CONFLUENCE_STRUCTURAL_STOP_PCT` and `CONFLUENCE_STOP_DROP_PCT` ship at **0**, `float`, search class `searchable`, each with a reachability row. With both at 0, every replay output is byte-identical to the pre-v139 golden (V139-0). `CLAMP_STOP_TO_HARD_CAP` keeps its meaning and default.
- No change to entries, unclamped plans, strategy plans, the 2% cap constant, `MIN_STOP_DISTANCE_PCT`, `CLAMP_HEADROOM_PCT`, alert text structure, charts or badges.
- Stage 0 MDE ceiling **+0.10R** at power 0.80 (arm S, paired). `win_rate_floor` −2.0pp. `not_luck` n = 200. Arm D clause 3 `VOLUME_MAX_CUT_PCT` = 25%; a cut past it fails, recorded and not rescued.
- `TradePlanV2.stop_ceiling_pct` rides in `plans.doc` (schema-evolution "add" path). No Alembic revision. The repository round-trip test must run against `db-test`, never be left skipped.
- Every function written or changed ends at cyclomatic complexity **< 15** (`python -m radon cc -s -n C <files>`). A legacy function ≥ 15 never gets worse.
- Per-task test runs: `python scripts/dev/testrun.py file <path>`. The full suite runs **once**, at V139-17.
- Long runs go to the `backtest-runner` agent, **one at a time**, with a percent-progress file past 15 minutes. Every measurement command exports `BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache` and `MEASURE_ARMS_UNIVERSE=cache`.
- Work in the worktree `.claude/worktrees/2026-10-08-v139-confluence-stop-geometry` on branch `2026-10-08-v139-confluence-stop-geometry`. Never edit the main tree. Never `cd` in Bash; every path is relative to the worktree session root.

## Review Focus

1. **Boundary arithmetic.** `d` exactly at `c − 0.25` must be arm S, and `d` exactly at `c` must be kept by arm D, despite float error in `planned_loss_pct` (`2.75/100*100` is not exactly 2.75). Pinned by `test_arm_s_applies_at_exactly_c_minus_headroom` and `test_arm_d_keeps_a_plan_exactly_at_c`, both directions (V139-4).
2. **A rollback is today's plan, field for field.** Same stop, TP1, TP2 and `stop_ceiling_pct is None`. Pinned by `test_arm_s_rollback_builds_exactly_todays_plan` (V139-5).
3. **Knobs at 0 change nothing live.** `plan_stop_ceiling` still returns 2.0 for a confluence plan without a stored ceiling. `risk_sizing_ok` is never consulted for one (the `in_scope` leak, Spec correction 5). Pinned by `test_without_a_stored_ceiling_the_two_percent_cap_still_applies` (V139-6) and `test_sizing_is_not_consulted_for_a_plan_without_a_stored_ceiling` (V139-7), plus the golden.
4. **Arm S never changes the entry set.** `paired_plans` raises if it does, rather than pairing the wrong rows. Pinned by `test_paired_plans_refuses_a_changed_entry_set` (V139-8).
5. **The universe switch never falls back silently.** An unknown `MEASURE_ARMS_UNIVERSE` raises. Pinned by `test_unknown_source_raises_never_falls_back` (V139-3).
6. **Re-running arm S Stage 3 is refused** (one-shot budget). Pinned by `test_stage3_refuses_when_output_exists` (V139-10).

## Parts

| Part | File | Tasks |
|---|---|---|
| 1 | `2026-10-08-v139-confluence-stop-geometry_1-geometry-and-live-path.md` | V139-0 .. V139-7 (Phases 1–2) |
| 2 | `2026-10-08-v139-confluence-stop-geometry_2-arm-s-instruments.md` | V139-8 .. V139-10 (Phase 3) |
| 3 | `2026-10-08-v139-confluence-stop-geometry_3-measurement-and-close-out.md` | V139-11 .. V139-17 (Phases 4–5: measurement, record, full suite, close-out) |

## Parallelisation

Mirrors the spec's groups. Before anything: V139-0 Step 1 creates the worktree. Every other task runs inside it.

- **Phase 1, Group A (parallel):** V139-0, V139-1, V139-2, V139-3. Disjoint files:
  - V139-0: the golden test plus its fixture.
  - V139-1: `plan_types.py` plus the serialization and repository tests.
  - V139-2: `config.py`, `scan_params.py`, `reachability.py`, `.env.example`, `tests/test_config_v139_confluence_stop.py`, `tests/market/test_v115_strategy_work_off.py`.
  - V139-3: `scripts/backtest/measure_arms.py` plus `tests/scripts/test_measure_arms.py`.

  None of them changes behaviour, and none consumes another's symbol. V139-3 is a plan addition the spec's Group A does not list (Spec correction 9). It is disjoint, so it joins the group. V139-0 must be **committed** before V139-5, the first task that changes what `build_confluence_plan` returns.
- **Phase 2, Group B (after A), sequential:** V139-4 → V139-5 → V139-6 → V139-7.
  - V139-4 reads the V139-2 `ScanParams` fields.
  - V139-5 edits the same file (`builders.py`) and consumes V139-4's helper and V139-1's field.
  - V139-6 (`stop_scope.py`) consumes the V139-1 field.
  - V139-7 (`analyze.py`) consumes V139-5's `confluence_stop_dropped` and V139-6's ceiling.

  V139-6's files are disjoint from V139-5's. It stays sequential because the spec groups the three stop-path changes, and V139-7 needs both.
- **Phase 3, Group C-instruments (after B), sequential:** V139-8 → V139-9 → V139-10.
  - V139-8 needs plans that carry `stop_ceiling_pct` (V139-5), and `plan_stop_ceiling` reading it (V139-6) for `fill_beyond_ceiling`.
  - V139-9 imports V139-8's `C_STEPS` / `cell_key`.
  - V139-10 drives both, and V139-3's universe switch.
- **Phase 4:**
  - **Group C (Stage −1), after Phase 3:** V139-11 runs the census and arm D's pilot reachability, one `backtest-runner` at a time. It commits the pre-registration record before any run.
  - **Group D (after C):** the arm S chain V139-12 → V139-13 and the arm D chain V139-14 → V139-15. Each stage consumes the previous verdict, so each chain is sequential. The chains have disjoint outputs and may interleave, but dispatch **one** `backtest-runner` at a time on this machine.
- **Sequential tail:** V139-16 after both chains (it records both arms, closed table and ledger together). V139-17 last: the full suite once, complexity, the release step, the close-out.

**Cross-plan overlap:** v135 (`2026-10-06-v135-headroom-veto`, unimplemented) also edits `config.py` (`_SEARCH_CLASSES`), `scan_params.py`, `reachability.py`, `analyze.py` (`_scan_one`, not `attach_plan_v2`) and `backtest_scenarios.py` (`replay_scenarios`). Whichever plan lands second rebases. The conflicts are list insertions and disjoint functions. If v135 lands first, its headroom gate is default-off, so V139-8's entry-set assertion still holds. Re-run the V139-0 golden after the rebase.

## Cross-plan coordination (audit 2026-10-10)

- **v147 — V139-7:** if `loss_pct =` and `_reject_plan(..., plan=plan, margin=…)` exist in `attach_plan_v2` (v147 merged), keep them and swap only the comparison and the margin base to `plan_stop_ceiling(plan)`; drop the `HARD_MAX_PLANNED_LOSS_PCT` import only if no use remains.
- **v158 (date-literal guard) — V139-10:** if `tests/backtesting/instrument/test_date_literal_guard.py` exists, add `scripts/backtest/measure_confluence_stop.py` to its `ALLOW` with a one-line reason and run the guard.
- **v158 (`--instrument`) — V139-11..15:** append `--instrument v1` to every measurement command whose script's `--help` lists it; the record names the instrument.
- **PARTNER DECISION (2026-10-10) — V139-11/12/13, arm S:** arm S runs on v1 as pre-registered, `--instrument v1` pinned when the flag exists. If `swingbot/core/planning/exit_sim_v2.py` exists (v157 merged), the Stage-1 TRAIN paired ΔExpR is also reported with `instrument=resolve("v2")` fills and costs, as a disclosure only: it never gates and is labelled as such in the record.
- **Code-hash stability — V139-11..16:** no merge of `main` into the worktree between the pre-registration commit and the last stage.
- **Closed-table placement — V139-16:** insert the two rows directly under the closed table's header separator (newest first).
- **v135 — V139-2:** v135's `ScanParams` fields are defaulted and placed at the end beside v139's; both plans append `REGISTRY` and `searchable` rows — whichever lands second rebases onto the other's rows.
- **Generic rules:** the swallowed-error ratchet (owner v148) does not apply — no v139 task adds an `except Exception` handler. The complexity gate (owner v149, full text in v149's plan) applies to V139-5's `_confluence_candidates` extraction from `build_confluence_plan`: if `scripts/dev/complexity_gate.py` exists, that task finishes with it and commits the updated baseline.
