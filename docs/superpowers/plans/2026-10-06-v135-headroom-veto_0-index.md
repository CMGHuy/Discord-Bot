# v135 Headroom veto: Implementation Plan, index

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read a part whole**: pull one task with `/task-brief V135-4` or `grep -n "^### Task V135-4" -A 140 docs/superpowers/plans/2026-10-06-v135-headroom-veto_*.md`.

**Spec:** `docs/superpowers/specs/2026-10-06-v135-headroom-veto-design.md`
**Bump:** none
**Edge:** expectancy

**Goal:** Add one binary gate that rejects a plan when an opposing level confirmed by at least two detector families sits strictly beyond entry and nearer than `h` x the plan's own risk. It ships off and is measured as two separate pre-registered components, `confluence` first and then `strategy`, through the v72/v100 funnel.

**Architecture:** One pure predicate in `swingbot/core/edge/gates.py`, called from the four call sites v122's dry-up gate already uses. The confluence sites hand it the very support/resistance lists the scenario was built from. The strategy sites hand it a unified level map that is built only while the strategy scope is active: on the pass's completed frame live, and on the frame truncated at the signal bar itself in replay, never the engine's 5-bar TP2 bucket. Live, replay and the clause-6 reading therefore judge a plan against the same map. The funnel tooling v122 built is reused; the plan adds only what the headroom predicate needs from it: a tie preference in `select_cell`, a frozen clause-6 baseline reading in `headroom_clauses.py`, and a `--headroom-mechanism` switch in `validate_component.py`.

**Tech Stack:** Python 3.11, pandas, pytest, `scripts/backtest/measure_arms.py` (v100 arm producer), `scripts/backtest/validate_component.py` (funnel judge), `scripts/backtest/permutation_test.py --arms` (v122 clause-5 instrument), `swingbot/core/backtesting/arms/` (engines, selection, clauses, reachability).

## Progress

Not started. Update this block when a phase closes and at close-out (V135-17).

## Where to work

- **Branch and worktree:** `2026-10-06-v135-headroom-veto`, at `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-06-v135-headroom-veto`. Create it in V135-1 Step 0 with the `worktree-lifecycle` skill. Implementation and **all measurement** happen in that worktree. Name the worktree in every subagent dispatch. After each task run `git -C E:/Documents/Private/Projects/Discord-Bot status --short` and confirm the main tree is unchanged.
- **Backtest cache:** `data/` is gitignored, so the worktree has no cache of its own. Prefix every measurement command with `BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache`. The main-tree cache is read-only here: never fetch into it from the worktree.
- **Skills:** `no-lookahead` before editing `edge/gates.py`, `scanning/` or `backtesting/arms/` (V135-2, V135-4, V135-5, V135-8, V135-10). `backtest-gate` before **every** measurement command (V135-12..V135-14). `worktree-lifecycle` before creating the branch (V135-1) and before merging it (V135-17).
- **This plan file is committed on `main`.** Only the implementation branches.

## Global Constraints

- Predicate, verbatim from the spec: `headroom_rejects(entry, stop, direction, levels, min_r) -> bool`. `risk = abs(entry - stop)`; `risk <= 0` or `min_r <= 0` returns `False`. A blocker is a `levels.Level` that is (1) strictly beyond `entry` on the target side (above for bullish, below for bearish), (2) nearer than `min_r x risk`: `abs(level.price - entry) < min_r x risk` (strict; a level exactly at the bound does not block), and (3) confirmed by at least `HEADROOM_MIN_FAMILIES = 2` distinct families: `len({levels.strategy_family(s) for s in level.sources}) >= 2`. `levels` empty or `None` returns `False`.
- `HEADROOM_MIN_FAMILIES = 2` is a frozen module constant. It is not a knob and not a grid axis. Changing it is a new pre-registration.
- Knobs: `HEADROOM_SCOPE` is `off | strategy | confluence` (default `off`). `HEADROOM_MIN_R` is a float (default `0.0`, meaning off). Both are `search_class = searchable`, hot-reloadable, and read from `config` at call time. The gate is inert unless `HEADROOM_SCOPE != off` **and** `HEADROOM_MIN_R > 0`.
- Frozen strategy list `HEADROOM_STRATEGIES`: `EMA Crossover`, `VWAP`, `Fibonacci`, `Support/Resistance`, `RSI`, `Elliott Wave`, `MA Ribbon`, `Break & Retest`, `RSI Divergence`. `MACD`, `Volume Profile` and every name in `strategy_types.SHORT_STRATEGIES` are never gated. Adding a name is a new pre-registration.
- Frozen grid: `h in {0.5, 0.75, 1.0}` per component. No bucket table from v125 (`room_atr`) or v133 may move it.
- **Which prices.** Planned prices at the decision point, never a fill. Confluence: `Scenario.entry`, `Scenario.stop_loss`. Strategy: the built plan's `entry_price` when set, else its `trigger_price`, and its `stop_loss` (the convention `acceptance.arm_trade_from_plan` already uses).
- **Which levels.** Confluence: the supports and resistances handed to `levels.build_scenarios` for that bar; no map build is added. Strategy: `levels.build_level_map` on the completed frame the plan was built from (live), and on the frame truncated at the signal bar itself, for every in-scope signal (replay). The gate never reads the engine's 5-bar TP2 bucket (partner decision, 2026-10-06), so live, replay and the clause-6 reading agree exactly and there is nothing to disclose on this scope. The plan handed to `build_strategy_plan` is unchanged: it still receives the bucketed map only when it wants TP2.
- **Gate off means no extra work.** With the gate inactive no call site builds a level map it did not build before, and replay trades are byte-identical (witness, V135-3).
- **NO-LOOKAHEAD.** The gate reads bar `t` and earlier only. The strategy map at bar `t` must be unchanged by truncating or altering the frame after `t` (V135-5).
- **Clause 6 (frozen, same reading as v122).** Mechanism is scored on the **baseline** arm: in-scope trades the predicate flags at `h` are "removed", in-scope trades it does not flag are "retained", out-of-scope trades are in neither group. PASS iff removed WR < retained WR **and** removed ExpR <= 0. Replacement trades count fully in clauses 1-5 and their count is disclosed.
- **Clause 5 (frozen).** `permutation_test.py --arms <stamped VALIDATION arm file> --n 200 --seed 42`, unchanged. A missing p is a FAIL.
- Selection rule: eligible cells pass clauses 2-4 and 6; the chosen `h` needs an eligible grid neighbour and `plateau_report()` `is_plateau`. Among those take the largest dWR; on a tie the **smaller** `h` (smaller cut).
- Each component is its own pre-registration with its own budget. `confluence` goes fully through its funnel first, then `strategy`. Serial, never concurrent, never pooled. Nothing under `swingbot/` or `scripts/backtest/` may be edited while a shot runs: `measure_arms.py` hashes the code before and after, and a mismatch makes the judge refuse the arms.
- v122 must stay byte-identical. `select_cell`'s default tie rule, `--dryup-mechanism` and `dryup_clauses.py`'s behaviour do not change; the tasks that touch shared code carry a witness test.
- Out of scope: moving any target or stop, any score weight, alert or chart text, a "caution" badge instead of a veto, and any use of lifecycle state or touch counts to qualify a blocker.
- Every function written or changed ends at cyclomatic complexity < 15 (`python -m radon cc -s -n C <files>`). Legacy scores measured on 2026-10-06 and never to get worse: `analyze._scan_one` E (36), `backtest_scenarios.replay_scenarios` C (15), `StrategyEngine.iter_trades` C (14), `strategy_pass._emit_signal` C (11).
- Every task runs its own narrow test file (`python scripts/dev/testrun.py file <test>`). The full suite runs **once**, in V135-16. Green means `0 failed` and `0 xfailed`.
- Runs longer than about two minutes go to the `backtest-runner` subagent, one `measure_arms.py` invocation per dispatch, with the flushed `logs/measure_arms.*.progress` percent line as progress.
- No persisted field changes, so `schema-change` does not apply. Known trap (`known-traps.md`): an empty selection table is a measured answer, not a stub; never fill or re-run it.
- Commits are small and scoped as each task's last step states. Never bundle two tasks into one commit.

## File map and interfaces

| File | Responsibility |
|---|---|
| `swingbot/config.py`, `.env.example` | Two `Field`s, the `_MODE_VALUES` entry for the scope (V135-1), the `searchable` classification (V135-7). |
| `swingbot/scan_params.py` | `headroom_scope`, `headroom_min_r` (V135-7; `tests/infra/test_scan_params_coverage.py` requires a field per searchable knob). |
| `swingbot/core/edge/gates.py` | `HEADROOM_MIN_FAMILIES`, `HEADROOM_STRATEGIES`, `HEADROOM_REASON`, `HEADROOM_SCOPES`, `nearest_blocker`, `blocker_inside`, `headroom_rejects`, `strategy_in_headroom_scope`, `headroom_active`, `planned_entry`, `level_map_levels`, `headroom_blocks_plan`, `filter_headroom` (V135-2). |
| `swingbot/core/scanning/strategy_pass.py` | Live strategy call site `_headroom_blocked`, after `build_strategy_plan_at` returns. `PassResult.headroom` counter (V135-4). |
| `swingbot/core/scanning/analyze.py`, `scan_run.py` | Live confluence call site `_apply_headroom`, beside `_apply_pullback_dryup`. Funnel slot `failed_counts["headroom"]`, keys `failed_headroom` and `strategy_headroom` (V135-4). |
| `swingbot/core/backtesting/arms/strategy_engine.py` | `level_map_at` (the signal-bar map), and the veto in `_gated_plan` after `build_strategy_plan` returns. `iter_trades` and its TP2 bucket are not edited (V135-5). |
| `swingbot/core/backtesting/backtest_scenarios.py` | Replay confluence call site `_headroom_kept` (V135-5); `bucket_bar` and `scenarios_at` extracted from `replay_scenarios` without behaviour change (V135-8). |
| `swingbot/core/backtesting/arms/reachability.py` | Classifies both knobs `REACHABLE`, observed by both engines, with the Stage -1 command (V135-7). |
| `swingbot/core/backtesting/arms/selection.py` | `select_cell(..., tie="larger" | "smaller")`; the default keeps v122's rule (V135-9). |
| `swingbot/core/backtesting/arms/headroom_clauses.py` | The frozen clause-6 baseline reading and the no-level-map disclosure (V135-10). |
| `swingbot/core/backtesting/arms/dryup_clauses.py` | One additive public alias, `mechanism_result` (V135-10). |
| `scripts/backtest/validate_component.py` | `--headroom-mechanism`, the per-mechanism selection axis and tie rule (V135-11). |

Verified on 2026-10-06 with `git grep -n` (re-check each before use): `config.Field`, `config._MODE_VALUES`, `config._cast`, `config._SEARCH_CLASSES`, `config.searchable_attrs`, `ScanParams.from_config`, `gates.pullback_dryup_blocks`, `gates.filter_pullback_dryup`, `levels.Level`, `levels.strategy_family`, `levels.build_level_map`, `levels.build_scenarios`, `levels.Scenario`, `strategy_types.SHORT_STRATEGIES`, `strategy_types.HORIZONS`, `strategy_types.MIN_BARS`, `backtest.ALL_STRATEGIES`, `strategy_pass._emit_signal` / `_dryup_blocked` / `PassResult` / `_PassDeps` / `completed_frame` / `build_strategy_plan_at`, `analyze._apply_pullback_dryup` / `gates_mod`, `scan_run._maybe_run_strategy_pass`, `StrategyEngine.iter_trades` / `_candidate_plan` / `_gated_plan`, `strategy_engine.build_level_map` (module-level import), `backtest_scenarios.levels_asof` / `_dryup_kept` / `replay_scenarios` / `LEVEL_REFRESH_BARS`, `scenario_gate_inputs`, `acceptance.ArmTrade` / `arm_trade_from_plan` / `ClauseResult` / `win_rate` / `expectancy_r`, `selection.select_cell` / `_selection_rank` / `evaluate_cell` / `with_clause` / `removed_disclosure`, `dryup_clauses._mechanism_result` / `knob_context` / `NotADryupArm`, `knobs.apply_knobs`, `arms.engine.run_arm`, `reachability.REGISTRY` / `Reach` / `REACHABLE` / `CS`, `validate_component._cell_mechanism` / `_run_gate` / `stage_selection` / `_frame_for` / `load_arms`, `measure_arms.load_frame`, `windows.STAGES`, `permutation_test.py --arms`, `tests/backtesting/test_v74_fixture.py:load_v74_fixture`, `tests/scanning/test_strategy_pass_emit.py:_Store` / `_Log` / `_plan`, `tests/scanning/test_engine_v2_plans.py:_setup_minimal_scan` / `_structured_df`, `tests/helpers.py:make_ohlcv`, `tests/backtesting/test_validate_component_stamps.py:UNIVERSE` / `rows` / `vc`, `tests/infra/test_env_example_sync.py`, `tests/infra/test_scan_params_coverage.py`.

Created by this plan (do not `git grep` for them before their task): everything in the `gates.py` row above (V135-2), `strategy_pass._headroom_blocked` and `analyze._apply_headroom` (V135-4), `strategy_engine.level_map_at` and `backtest_scenarios._headroom_kept` (V135-5), `backtest_scenarios.bucket_bar` and `scenarios_at` (V135-8), `select_cell`'s `tie` parameter (V135-9), `headroom_clauses` and `dryup_clauses.mechanism_result` (V135-10), `validate_component._headroom_mechanism_for` / `_baseline_headroom` / `_selection_axis` (V135-11).

## Review focus

1. **A level exactly at the bound, or exactly at entry.** The comparison is strict on both sides. `blocker_inside` is the one comparison the gate and the clause-6 flags share, so they cannot disagree at the boundary (V135-2, V135-10).
2. **The gate must cost nothing when off.** `HEADROOM_SCOPE=off`, or any scope with `HEADROOM_MIN_R=0`, must build no level map and call no predicate. Pinned by spies that raise (V135-4, V135-5) and by the build count in the witness (V135-3).
3. **Two maps in replay, never mixed.** The builder still receives the 5-bar TP2 bucket, `level_map if wants_tp2 else None`, untouched; the veto reads only a map built at the signal bar. Handing the signal-bar map to the builder would move stops through the level lifecycle and break the baseline. Letting the veto read the TP2 bucket would make replay disagree with live whenever that bucket is stale. Both directions are pinned by `test_the_veto_never_reads_the_tp2_bucket_map` (V135-5).
4. **A malformed `.env` scope** (`Strategy`, `both`, `""`) must fall back to `off` and never half-enable the gate (V135-1).
5. **The clause-6 reading replays the baseline.** `headroom_clauses` forces both knobs off while it rebuilds plans, so an operator `.env` with the gate on cannot leak into the baseline reading (V135-10).

## Parallelisation

- **Phase 1:** V135-1 first (creates the worktree and the knobs every later task reads). Then **Group A (parallel):** V135-2 (`gates.py` and its test) and V135-3 (a test file and a fixture). Disjoint files; neither consumes the other.
- **Phase 2:** **Group B (parallel):** V135-4 (live files) and V135-5 (replay files). Disjoint files, both consume only V135-2's predicate. Both start **after V135-3 is committed**, because the witness must be captured on pre-gate code. **Group C (parallel):** V135-6 (one new parity test file) and V135-7 (`config.py`, `scan_params.py`, `reachability.py`). Disjoint files. V135-6 consumes V135-4 and V135-5; V135-7 consumes V135-5.
- **Phase 3:** V135-8 after V135-5 (both edit `backtest_scenarios.py`). V135-9 touches only `selection.py` and its test and may run any time after V135-1, in parallel with anything. V135-10 after V135-2, V135-5 and V135-8 (consumes `nearest_blocker`, `level_map_at`, `scenarios_at`). V135-11 after V135-7, V135-9 and V135-10 (its test stamps arms with the two knobs, and it consumes `tie=` and `headroom_clauses`).
- **Phase 4:** sequential throughout. V135-12 (pre-registration) after every code task. V135-13 (confluence funnel) then V135-14 (strategy funnel): one shot at a time, no edit under `swingbot/` or `scripts/backtest/` while a shot runs. V135-15 needs both verdicts. V135-16 is the only full-suite run. V135-17 closes out on `main`.
- **Cross-plan edges (v128, v129):** both live plans also edit `swingbot/config.py` and `swingbot/core/backtesting/arms/reachability.py`; v128 also edits `scripts/backtest/validate_component.py`. V135-1, V135-7 and V135-11 must not run concurrently with a v128 or v129 task touching the same file. If either has landed first, rebase the worktree and re-apply the edit beside the new neighbours; never overwrite them.

## Parts

| Part | Tasks | Content |
|---|---|---|
| `2026-10-06-v135-headroom-veto_0-index.md` | -- | Header, where to work, global constraints, file map, review focus, parallelisation (this file) |
| `2026-10-06-v135-headroom-veto_1-gate-and-call-sites.md` | V135-1 .. V135-7 | Phase 1 (knobs, predicate, witness) and Phase 2 (call sites, parity, reachability) |
| `2026-10-06-v135-headroom-veto_2-funnel-and-measurement.md` | V135-8 .. V135-17 | Phase 3 (funnel tooling) and Phase 4 (pre-registration, serial measurement, ship or close, full suite, close-out) |

## Cross-plan coordination (audit 2026-10-10)

- **v146 (V146-7) — V135-5, V135-8:** if `replay_scenarios_detailed` / `_bar_scenarios` exist in `backtest_scenarios.py` (v146 merged), V135-5 puts `_headroom_kept(_dryup_kept(scenarios, window), supports, resistances)` in `_bar_scenarios`' return, and V135-8 makes `scenarios_at` the pre-gate body of `_bar_scenarios`, which then calls it and applies both gates. Otherwise as written.
- **v146 (V146-7) — V135-8 Step 3:** `tests/scripts/test_fvg_attribution.py::test_replay_still_has_the_shape_the_recorder_patches` is rewritten to read the whole module (`inspect.getsource(bs)`); v146 makes the same update — whichever lands second keeps the existing one.
- **v147 (`_scan_params_of`) and v139 (V139-2) — V135-7:** `headroom_scope: str = "off"` and `headroom_min_r: float = 0.0` go at the END of `ScanParams`, defaulted, beside v139's defaulted fields, so v147's rebuild of stored rows never raises. v139 also appends `reachability.REGISTRY` and `searchable` rows; whichever lands second rebases onto the other's rows.
- **v158 (`--instrument`) — V135-12..14:** append `--instrument v1` to every measurement command whose script's `--help` lists it; the pre-registration record names the instrument.
- **Code-hash stability — V135-12..15:** no merge of `main` into the worktree between the pre-registration commit and the last stage (`measure_arms` stamps `code_hash()` over `swingbot/*.py`).
- **Closed-table placement — V135-17:** rows go directly under the closed table's header separator (newest first); the top row is no longer v122.
- **Generic rules:** the swallowed-error ratchet (owner v148) does not apply — no v135 task adds an `except Exception` handler. The complexity gate (owner v149, full text in v149's plan) applies to V135-8's extraction from `replay_scenarios` (a legacy C (15) function): if `scripts/dev/complexity_gate.py` exists, V135-8 finishes with it and commits the updated baseline.
