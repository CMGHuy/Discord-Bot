# Pullback volume dry-up gate — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. The plan is split into parts. Pull one task at a time (`/task-brief V122-4` or `grep -rn "^### Task V122-4" -A 140 docs/superpowers/plans/`). Steps use `- [ ]` for tracking; read the spec with each task.

**Goal:** Add one binary gate that rejects a pullback entry when its pullback leg averaged more than `d` × its impulse leg's volume. Live and replay call it at the same decision point, on completed bars only. It ships off and is measured as two separate pre-registered components, `strategy` and `confluence`, through the v72/v100 funnel.
**Architecture:** One predicate in `swingbot/core/edge/gates.py` reads v121's `market/structure.py:pullback_vol_ratio`. Four call sites ask it before a plan is built: `strategy_pass._emit_signal` and `analyze._scan_one` live (both after `strategy_pass.completed_frame`), and `StrategyEngine.iter_trades` and `backtest_scenarios.replay_scenarios` in replay. Two searchable knobs drive it. The spec relies on funnel tooling that does not exist yet, so the plan adds it first: a Stage 1 judge, the frozen clause-6 baseline reading behind `--dryup-mechanism`, and an extended `permutation_test.py --arms` as the clause-5 instrument. The two components are then measured serially.
**Tech Stack:** Python 3.11, pandas, pytest, the v100 arm producer (`scripts/backtest/measure_arms.py`), the judge (`scripts/backtest/validate_component.py`) and `scripts/backtest/permutation_test.py`.
**Spec:** `docs/superpowers/specs/2026-10-02-v122-pullback-volume-dryup-gate-design.md`, including its frozen amendments: the clause 6 reading, the clause 5 instrument, and completed bars only. It depends on `docs/superpowers/specs/2026-10-02-v121-structure-volume-context-design.md`.
**Bump:** bot patch (only if a scope passes VALIDATION and ships default-on)
**Edge:** expectancy

## Global constraints

- **v121 must be merged first.** The gate calls `swingbot.core.market.structure.pullback_vol_ratio(df, direction, k=PIVOT_K) -> float | None`, the same function v121's snapshot uses. It never re-derives pivots or legs. V122-1 checks this before any code changes.
- Gate rule, verbatim: reject iff `pullback_vol_ratio is not None` **and** `pullback_vol_ratio > d`. `None` passes, and a ratio exactly equal to `d` passes. `PULLBACK_DRYUP_MAX_RATIO = 0` never rejects. One comparison, `gates.ratio_exceeds`, serves both the gate and the clause-6 baseline flags.
- **Completed daily bars only.** A live call site drops today's still-forming bar with `strategy_pass.completed_frame(df, now)` (verified; v119 and `run_strategy_pass` use it) before calling the predicate. Replay slices are completed by construction.
- Knobs: `PULLBACK_DRYUP_SCOPE` is `off | strategy | confluence` (default `off`). `PULLBACK_DRYUP_MAX_RATIO` is a float (default `0.0`, meaning off). Both are `search_class = searchable`, hot-reloadable, and read from `config` at call time.
- Frozen strategy list, as exact `ENTRY_FUNCS` keys: `Fibonacci`, `EMA Crossover` (only while `entry_filters.DEFAULT_PARAMS["EMA Crossover"]["entry_mode"] == "pullback"`), `Break & Retest`, `RSI`, `RSI Divergence`, `MA Ribbon`, `VWAP`. Adding a strategy needs a new pre-registration.
- Frozen grid: `d ∈ {0.60, 0.75, 0.90}` per component. No bucket table from v121's report may move it.
- **Clause 6 (frozen):** mechanism is scored on the **baseline** arm. Predicate-flagged baseline trades are "removed" and unflagged **in-scope** ones are "retained"; out-of-scope trades are in neither group. Replacement trades count fully in clauses 1–5, and their count is disclosed. There is no Stage −1 not-subset halt.
- **Clause 5 (frozen):** `permutation_test.py --arms <stamped arm pair> --n 200 --seed 42` gives a p-value on standardised ΔWR. It covers confluence and strategy rows. Its existing fold-path output is pinned unchanged by a witness test.
- Each component is its own pre-registration with its own budget. The two are measured **serially**, never as concurrent shots. Nothing under `swingbot/` may be edited while a shot runs: `measure_arms.py` hashes `swingbot/**/*.py` before and after, and a mismatch makes `validate_component.py` refuse the arms (`refused:engine-mismatch`).
- Out of scope: `planning/quality.py:component_volume`, any breakout volume rule, any score weight, and alert or chart text.
- Every function written or changed stays below CC 15 (`python -m radon cc -s -n C <files>`). Legacy functions are left at their current scores: `replay_scenarios` (15) and `_scan_one` (39). New logic goes into named helpers that add no branch to them.
- Invoke `edge-module` and `no-lookahead` for the `gates.py` and call-site tasks. Invoke `backtest-gate` before every measurement run or interpretation. No persisted field changes, so `schema-change` does not apply.
- Every task runs its own narrow test file (`python scripts/dev/testrun.py file <test>`). The full suite runs once, in V122-15.
- Branch: implement on `2026-10-02-v122-pullback-volume-dryup-gate` (worktree). Results docs are committed on the same branch before merge.

## File map and interfaces

| File | Responsibility |
|---|---|
| `swingbot/config.py`, `.env.example` | Two `Field`s, `_cast` validation for the scope, and the `searchable` classification (V122-7). |
| `swingbot/core/edge/gates.py` | `PULLBACK_DRYUP_STRATEGIES`, `PULLBACK_VOLUME_REASON`, `ratio_exceeds`, `pullback_dryup_rejects`, `strategy_in_dryup_scope`, `pullback_dryup_scoped`, `pullback_dryup_blocks`, `filter_pullback_dryup`. |
| `swingbot/core/scanning/strategy_pass.py` | Live strategy call site, between the RS gate and `build_strategy_plan_at`, on the `completed_frame` that `run_strategy_pass` already passes. Adds the `PassResult.pullback_volume` counter. |
| `swingbot/core/scanning/analyze.py`, `scan_run.py` | Live confluence call site `_apply_pullback_dryup(..., now=None)`, which trims the forming bar. Adds the `failed_counts["pullback_volume"]` slot and the funnel keys `failed_pullback_volume` and `strategy_pullback_volume`. |
| `swingbot/core/backtesting/arms/strategy_engine.py` | Replay strategy call site `StrategyEngine._gated_plan`. |
| `swingbot/core/backtesting/backtest_scenarios.py` | Replay confluence call site `_dryup_kept`. |
| `swingbot/core/backtesting/arms/reachability.py` | Classifies both knobs `REACHABLE`, observed by confluence and strategy. |
| `swingbot/core/backtesting/arms/selection.py`, `arms/windows.py`, `scripts/backtest/validate_component.py` | Stage 1 judge (`--stage selection`), `with_clause`, disclosure (per direction, horizon share, replacements), and the population split in the Stage −1 output. |
| `swingbot/core/backtesting/arms/dryup_clauses.py`, `validate_component.py --dryup-mechanism` | The frozen clause-6 baseline reading and the `None`-share disclosure. |
| `scripts/backtest/permutation_test.py` | `--arms` mode, the clause-5 instrument. The fold path is unchanged (witness). |

Verified symbols (`git grep -n`): `config.Field`, `config._SEARCH_CLASSES`, `config._cast`, `config.searchable_attrs`, `reachability.REGISTRY`/`Reach`/`REACHABLE`/`CS`, `strategy_pass._emit_signal`/`PassResult`/`_PassDeps`/`build_strategy_plan_at`/`completed_frame`, `session.is_regular_session`/`session_date`, `analyze._scan_one`/`gates_mod` (an existing import of `edge.gates`), `scan_run.failed_counts`/`progress.funnel`/`_maybe_run_strategy_pass`, `StrategyEngine.iter_trades`, `backtest_scenarios.replay_scenarios`, `entry_filters.DEFAULT_PARAMS`/`ENTRY_FUNCS`, `acceptance.evaluate`/`population_split`/`win_rate`/`expectancy_r`/`delta_standardised_win_rate`/`delta_expectancy_r`/`ClauseResult`/`AcceptanceResult`, `backtest_wf.plateau_report`/`gate_win_rate`/`run_folds`, `provenance.check_stamp`/`build_stamp`, `windows.FUNNEL_TO_PRODUCER_STAGE`, `measure_arms.load_frame`, `validate_component.load_arms`/`load_folds`/`_run_gate`, and `permutation_test.permuted_expectancies`/`p_value`/`_fold_run_fn`.

Not in the tree yet:
- `structure.pullback_vol_ratio` comes from v121. Its signature is taken from the uncommitted v121 plan `2026-10-02-v121-structure-volume-context.md`, and V122-1 checks it.
- `selection`, `dryup_clauses` and `permutation_test.arm_pair_permutation` are created by V122-8, V122-9 and V122-10.

## Review focus

1. **Today's forming bar must never reach the predicate.** Its partial volume drags the pullback mean down intraday, and an unfinished candle can sit among a pivot's `k` confirming bars. Live trims the bar with `completed_frame`, and replay never has one. V122-4 pins the trim during RTH and the no-trim case after the close. V122-6 pins live/replay agreement on a frame that carries a heavy forming bar, which would flip the verdict if it leaked through.
2. **Hot reload between scans.** A change to `PULLBACK_DRYUP_SCOPE` in `config` must change the next verdict; nothing may capture it at import. V122-2 tests a flip between two calls.
3. **A malformed `.env` scope** (`Strategy`, `both`, `""`) must fall back to `off`. It must neither crash nor half-enable the gate. V122-1 tests this.
4. **The gate costs nothing when off.** With scope `off` or ratio `0`, `pullback_vol_ratio` is never called. A disabled flag must not add replay or scan time. V122-2 and V122-5 use a spy that raises if called.
5. **A NaN ratio** must pass, like `None`. That covers v121 returning `float("nan")` on degenerate volume. V122-2 pins it, and `ratio_exceeds` keeps the clause-6 flags identical.

## Parallelisation

- **Phase 1:** V122-1 runs first. It checks v121 and adds the knobs V122-2 reads. Then **Group A (parallel):** V122-2 (`gates.py` and its tests) and V122-3 (the witness capture, which touches only a test and a fixture). Their files are disjoint and neither consumes the other.
- **Phase 2:** **Group B (parallel):** V122-4 (live files) and V122-5 (replay files). Their files are disjoint and both consume only V122-2's predicate. Both start **after V122-3 is committed**, because the witness must be captured on pre-gate code. **Group C (parallel):** V122-6 (the parity test file) and V122-7 (`config.py`, `reachability.py` and the reachability test). Their files are disjoint. V122-6 consumes V122-4 and V122-5, and V122-7 consumes V122-5.
- **Phase 3, tooling:** V122-8 has no dependency on Phases 1–2 and may start any time after V122-1. V122-9 comes after V122-8, because both edit `validate_component.py` and V122-9 consumes `with_clause` and `evaluate_cell(mechanism=)`. V122-9 also comes after V122-2, because it consumes `ratio_exceeds` and `strategy_in_dryup_scope`. V122-10 touches only `permutation_test.py` and its own test and witness, consumes nothing from V122-8 or V122-9, and may run in parallel with either.
- **Phase 3, measurement:** sequential throughout. V122-11 (the pre-registration) comes after all code tasks. V122-12 (strategy funnel) then V122-13 (confluence funnel): one shot at a time, with no edits under `swingbot/` or `scripts/backtest/` while a shot runs. V122-14 (ship or close) needs both verdicts. V122-15 is the only full-suite run.
- **Cross-plan edge (v123):** v123's plan also edits `swingbot/config.py`, `backtesting/arms/reachability.py` and `scripts/backtest/validate_component.py` (its harvest walk-forward and validation gates). The v122 tasks that touch those files are V122-1, V122-7, V122-8, V122-9 and V122-14. None of them may run concurrently with a v123 task touching the same file. V122-8 Step 4 says to rebase onto v123's `validate_component.py` shape if v123 has landed first.

## Parts

| Part | Tasks | Content |
|---|---|---|
| `2026-10-02-v122-pullback-volume-dryup-gate_0-index.md` | -- | Header, global constraints, file map, review focus, parallelisation (this file) |
| `2026-10-02-v122-pullback-volume-dryup-gate_1-gate-and-call-sites.md` | V122-1 .. V122-7 | Phase 1 (knobs, predicate, witness) and Phase 2 (call sites, parity, reachability) |
| `2026-10-02-v122-pullback-volume-dryup-gate_2-funnel-and-measurement.md` | V122-8 .. V122-15 | Phase 3 (Stage 1 judge, clause-6 reading, clause-5 instrument, pre-registration, serial measurement, ship/close, full suite) |
