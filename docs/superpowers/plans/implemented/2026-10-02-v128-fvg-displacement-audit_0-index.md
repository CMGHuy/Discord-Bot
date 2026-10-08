# v128 FVG lift audit (all vs off vs displacement-only): Implementation Plan, index

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read a part whole**: pull one task with `grep -n "^### Task V128-7" -A 140 docs/superpowers/plans/2026-10-02-v128-fvg-displacement-audit_*.md`.

**Bump:** bot patch
**Edge:** expectancy
**Spec:** `docs/superpowers/specs/2026-10-02-v128-fvg-displacement-audit-design.md`

**Goal:** Add an inert `FVG_LEVELS_MODE` (`all | displacement | off`) and `FVG_DISPLACEMENT_ATR_K` to the level map. Measure the four frozen candidates through the funnel under both the v72 and v92 gates, and flip the default only if exactly one winner passes its one VALIDATION shot.

**Architecture:** `fvg.py` gains a causal displacement predicate and a mode filter applied after the existing "freshest 3 per side" truncation. `levels.collect_candidate_levels` reads the two `ScanParams` fields outside any `try` and passes them to that filter. That function is the single code point live and replay share, so the knob reaches both replay engines through `apply_knobs`. Measurement uses the standard `measure_arms.py` → `validate_component.py` funnel. The spec assumes tooling that does not exist: a harvest walk-forward and VALIDATION route, a frozen clause-6 reading, a dual-gate Stage 1 judge, and a ΔExpR permutation p. The plan adds each of these in the script layer and freezes how it is used in the pre-registration record before any arm exists.

**Tech Stack:** Python 3.11, pandas/numpy, pytest, `scripts/backtest/measure_arms.py` (v100 producer), `scripts/backtest/validate_component.py` (funnel judge), `swingbot/core/backtesting/acceptance.py` (v72), `acceptance_harvest.py` (v92), `backtest_wf.py` (`plateau_report`, `gate`, `gate_win_rate`), `scripts/backtest/permutation_test.py` (v122 `--arms` extension, Stage 3 only).

## Where to work

- **Branch and worktree:** `2026-10-02-v128-fvg-displacement-audit`, at `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-02-v128-fvg-displacement-audit`. Create it in V128-1 Step 0 with the `worktree-lifecycle` skill. Implementation and **all measurement** happen in that worktree. Name the worktree in every subagent dispatch. After each task run `git -C E:/Documents/Private/Projects/Discord-Bot status --short` and confirm the main tree is unchanged (`subagents-edit-main-tree-by-mistake`).
- **Backtest cache:** `data/` is gitignored, so the worktree has no cache of its own. Prefix every measurement command with `BACKTEST_CACHE_DIR=E:/Documents/Private/Projects/Discord-Bot/data/backtest_cache`. The main-tree cache is read-only here: never fetch into it from the worktree.
- **Skills:** `no-lookahead` before editing `fvg.py` (V128-1). `backtest-gate` before **every** measurement command (V128-8..V128-13). `worktree-lifecycle` before creating, merging into, or merging out of the branch.

## Global Constraints

- `FVG_LEVELS_MODE`: `all | displacement | off`, default `all` (production byte-identical), `search_class = searchable`.
- `FVG_DISPLACEMENT_ATR_K`: float, default `1.5`, read only when mode is `displacement`, `search_class = searchable`.
- Both are threaded through `ScanParams` as `fvg_levels_mode` / `fvg_displacement_atr_k`, the way `avwap_levels_enabled` is. The mode check sits **outside** the `try` in `levels.py`.
- Both are registered in `backtesting/arms/reachability.py` as reachable.
- A gap the mode filters out disappears from **both** roles: the confluence vote and the candidate price. Charts (`chart_geometry.py`, `/strategycharts`) keep drawing every unfilled gap whatever the mode.
- Displacement rule, with `m = bar_index − 1`: `|Close[m] − Open[m]| ≥ k × ATR14[m]` (`indicators.atr(df, 14)`). Bullish: `Close[m] ≥ Low[m] + (2/3)·(High[m] − Low[m])`. Bearish: `Close[m] ≤ Low[m] + (1/3)·(High[m] − Low[m])`. A non-finite or ≤ 0 `ATR14[m]` means not a displacement gap.
- Frozen grid: baseline `all`; candidates `off` and `displacement@k ∈ {1.0, 1.5, 2.0}`. No table from any stage may move it.
- A cell advances only if **both** gates pass at that stage. **At most one winner across all four candidates.** Pick the largest ΔExpR; on a tie, the smaller alert cut, then `displacement` over `off`.
- Stage 3 window is 2024-01-01..2025-12-31: **one shot, total**, for the single Stage-1 winner. A missing permutation p is a FAIL.
- Clause 6 (frozen amendment) is scored on the **baseline** arm. Removed = FVG vote from a filtered gap **or** entry/stop/target level from such a gap. Retained = every other baseline trade. PASS iff removed WR < retained WR **and** removed ExpR ≤ 0.
- If v122's `permutation_test.py` extension is not on `main` at Stage 3, **stop before VALIDATION** and leave a resume point, budget unspent.
- The pre-registration record is committed under `docs/superpowers/results/` **before** any arm is produced. Every run longer than ~2 minutes goes to `backtest-runner`, one arm per chunk.
- Every function written or changed has cyclomatic complexity < 15 (`python -m radon cc -s -n C <files>` prints nothing). `collect_candidate_levels` is already ≥ 15 and must not get worse.
- A PASS flips the default in its own commit. Any other outcome leaves `all` and merges the code inert. Whatever the outcome, add a closed-pre-registrations row.

## Review Focus

1. **An operator typo in `.env`** (`FVG_LEVELS_MODE=of`) must fall back to `all`, never to `off`. The existing `_MODE_VALUES` fallback is `"off"`, which would silently remove a production signal source. Pinned by `test_unknown_mode_falls_back_to_all_never_off` (V128-2).
2. **A short or degenerate frame**: fewer than 14 bars before the middle candle, or a NaN/zero ATR. It must return "not displacement" without raising. Pinned by `test_too_little_history_for_atr14_is_not_displacement` and `test_non_finite_or_non_positive_atr_is_not_displacement` (V128-1).
3. **`/strategycharts` under `FVG_LEVELS_MODE=off`** must still show the FVG chart (display, not signal). Without a pin, the chart silently disappears. Pinned by `test_strategy_charts_keep_every_gap_when_the_mode_is_off` (V128-3).
4. **Recorder and arms drift apart**: a code edit between producing arms and recording provenance, or a baseline confluence trade the recorder never saw. Either must refuse loudly rather than misclassify. Pinned by `test_report_refuses_a_code_mismatch` and `test_a_baseline_confluence_trade_without_provenance_raises` (V128-5).
5. **The four candidate arms carry different baselines** (code changed between chunked runs). Stage 1 must refuse instead of comparing ΔExpR across different books. Pinned by `test_select_refuses_baseline_drift` (V128-6).

## Spec assumptions that do not hold, and how this plan resolves them

Each resolution is written into the pre-registration record (V128-7) **before** any arm is produced. No threshold in the spec changes.

| # | Spec assumes | Verified fact (`git grep -n`) | Resolution (task) |
|---|---|---|---|
| A1 | `validate_component.py --gate harvest` scores every stage | `--gate` only changes `stage_mde`. `stage_walkforward` always calls `gate_win_rate`, and `_run_gate` always calls the v72 `evaluate` | V128-4 routes `--gate harvest` at walkforward to `backtest_wf.gate` and at validation to `acceptance_harvest.evaluate_harvest`. The `win_rate` path is byte-identical |
| A2 | "the harvest gate's walk-forward rule" | `acceptance_harvest.py` has no fold rule. v92's spec says its funnel stages are "reused as-is" | Frozen: the v92 walk-forward rule is the existing pre-registered expectancy fold gate, `backtest_wf.gate()`: ≥ 2 of 3 folds with ΔExpR > 0, no fold below −0.05R (`GATE_MAX_DEGRADATION_R`), per-fold N ≥ 30 (closed trades, min of the two arms). Existing constants, nothing new (V128-4, V128-7) |
| A3 | `plateau_report()` applies to the `k` grid; a chosen `k` "needs an eligible neighbour" | `backtest_wf.plateau_report(param, grid, expectancies, adopted)` checks only that each neighbour's expectancy is within `PLATEAU_TOLERANCE_R = 0.03`. It does not know eligibility. On a one-point grid (`off`) it returns `is_plateau: True` **vacuously** (empty `all([])`) | Frozen: a `k` passes when `plateau_report(...)["is_plateau"]` holds (on pooled fold-train ΔExpR) **and** at least one grid neighbour is eligible. `off` is never passed to `plateau_report`; it is eligible on its clauses alone (v35 precedent). A `None` ΔExpR on the chosen `k` or a neighbour fails the plateau (V128-6, V128-7) |
| A4 | `validate_component.py` scores Stage 1 | No `selection` stage on `main`. v122's planned `--stage selection` (V122-8) is v72-only, ranks on ΔWR, and has not landed | V128-6 adds `scripts/backtest/fvg_select.py`, a dual-gate Stage 1 judge implementing the spec's rule. It does not touch V122-8's files (V128-6, V128-7) |
| A5 | Clause 6 can be scored by the standard gate | `acceptance._clause_mechanism` reads only `population_split`; for a non-subset arm it returns `SKIPPED`. `ArmTrade` carries no confluence families or level provenance | V128-5 adds `scripts/backtest/fvg_attribution.py`, which replays the **baseline** confluence arm once per stage and records per-trade FVG provenance. It emits the frozen clause-6 `ClauseResult`, and V128-4's `--mechanism-json` swaps it into the v72 result (V128-4, V128-5, V128-7) |
| A6 | "entry/stop/target level came from such a gap" is observable for every trade | Confluence plans enter at the bar close (`Scenario.entry = current_price`), so entry is never a level. Strategy plans have no confluence vote, and their FVG exposure (TP2 level map, lifecycle stop) is not recorded anywhere | Frozen: confluence rows use the recorder (vote at the signal bar; stop = scenario stop level, target = plan TP1 cluster, both at the level-map bar the replay actually used). Strategy rows use a pairing proxy: "price changed" iff the key is absent from the candidate arm, or its outcome or `r_multiple` differs (V128-5, V128-7) |
| A7 | v122's permutation extension supplies the Stage 3 permutation p | V122-10's planned `arm_pair_permutation` returns a **ΔWR** p only. v92 clause 4 (`not_luck`) is on **ΔExpR** | V128-12 adds a `statistic="expectancy"` option to the same function and CLI (`--statistic expectancy`). It reuses the same null-arm construction and is not a second instrument; the default `win_rate` output is pinned byte-identical. It runs only after the V128-12 hard check confirms v122 is on `main` (V128-12, V128-7) |
| A8 | Stage −1 is "scored twice" | `stage_reachability` ignores `--gate` | Run under both flags for the record; the verdicts are identical by construction (V128-8) |
| A9 | `displacement` returns "a subset of `all`" | `find_fair_value_gaps_detailed` truncates to the freshest 3 per side **before** any filter | Frozen: the filter runs after truncation, so displacement keeps a subset of today's ≤ 3 gaps per side and never reaches back for an older displacement gap (V128-1) |
| A10 | `/strategycharts` keeps every gap "whatever the mode" | `trade_chart.generate_all_strategy_charts` calls `collect_candidate_levels(df, h, current_price)`, which would follow the mode | V128-3 pins that call to `fvg_levels_mode="all"` (display only) |
| A11 | Invalid mode is "rejected" | `config._cast` falls back to `"off"` for every `_MODE_VALUES` field | V128-2 adds a per-field fallback (`FVG_LEVELS_MODE` → `all`) and a positive-finite float check for `k` (bad value → field default; `parse_knob` refuses the arm) |
| A12 | The number given at planning (v126) was free | `d43c1994` had already claimed v126 on `main`, and that session later renumbered its own doc to v127 (`5ebbc21d`) | **Resolved before the first commit:** v126 is still claimed through commit subjects, so the counter's max was v127 and this audit is **v128**. The spec, all four plan files, the task ids and the `results/…-v128-*` paths were renamed together |

## Files

| File | Task | Responsibility |
|---|---|---|
| `swingbot/core/market/fvg.py` | V128-1 | `FVG_MODES`, `is_displacement_gap`, `filter_gaps`, `find_fair_value_gaps(..., mode, k)`. `find_fair_value_gaps_detailed` unchanged |
| `swingbot/config.py`, `swingbot/scan_params.py`, `swingbot/core/backtesting/arms/reachability.py`, `.env.example` | V128-2 | Two fields, validation, searchable, reachable through `CS` |
| `swingbot/core/market/levels.py`, `swingbot/core/charts/trade_chart.py` | V128-3 | `_fvg_candidates(df, params)` outside the `try`; `/strategycharts` pinned to `all` |
| `scripts/backtest/validate_component.py` | V128-4 | `--gate harvest` at walkforward/validation, `--mechanism-json`, `with_mechanism_clause` |
| `scripts/backtest/fvg_attribution.py` | V128-5 | Baseline provenance recorder, attribution table, frozen clause 6, context slice |
| `scripts/backtest/fvg_select.py` | V128-6 | Stage 0 effect printer and the dual-gate Stage 1 judge |
| `docs/superpowers/results/2026-10-02-v128-fvg-preregistration.md` | V128-7 | The frozen record, committed before Stage −1 |
| `docs/superpowers/results/2026-10-02-v128-fvg-stage{-neg1,0,1,2,3}.md` | V128-8..13 | One results file per stage |
| `scripts/backtest/permutation_test.py` | V128-12 | `--statistic expectancy` on v122's `--arms` mode |
| `docs/claude/backtest-methodology.md` | V128-14 | Closed-pre-registrations row |

Verified symbols (`git grep -n`, 2026-10-02 `main` at `d43c1994` (verified as v126; renumbered v128 before commit)): `fvg.find_fair_value_gaps_detailed`/`find_fair_value_gaps`/`LOOKBACK_BARS`/`MAX_GAPS_PER_SIDE`, `indicators.atr(df, period=14)` (Wilder EWM, `min_periods=period`, causal), `levels.collect_candidate_levels(df, h, current_price, trendline_candidates=None, params=None)`, `levels.count_confirming_strategies(df, h, current_price, target_price, tolerance_pct, candidates=None)`, `levels._cluster_levels`, `levels.CLUSTER_TOLERANCE_PCT`, `levels.build_level_map`, `levels.strategy_family`, `ScanParams.avwap_levels_enabled`/`from_config`, `config.Field`/`FIELDS`/`_SEARCH_CLASSES`/`_MODE_VALUES`/`_cast`/`_apply_env`/`searchable_attrs`, `reachability.REGISTRY`/`Reach`/`REACHABLE`/`CS`/`classify`, `knobs.parse_knob`/`apply_knobs`, `arms.engine.run_arm`, `ConfluenceEngine.run_ticker`, `backtest_scenarios.levels_asof`/`build_confluence_plan`/`LEVEL_REFRESH_BARS`/`replay_scenarios`, `measure_arms.main`/`load_frame`/`cached_universe`, `windows.STAGES`/`FUNNEL_TO_PRODUCER_STAGE`, `provenance.code_hash`/`build_stamp`/`check_stamp`, `validate_component.load_arms`/`load_folds`/`_run_gate`/`stage_walkforward`/`_write_skeleton`, `acceptance.ArmTrade`/`ClauseResult`/`AcceptanceResult`/`evaluate`/`win_rate`/`expectancy_r`/`delta_standardised_win_rate`/`delta_expectancy_r`/`CLOSED`/`DECIDED`/`VERSION`, `acceptance_harvest.evaluate_harvest`/`WIN_RATE_FLOOR_PP`/`HARVEST_VERSION`, `backtest_wf.plateau_report`/`gate`/`gate_win_rate`, `trade_chart.generate_all_strategy_charts`, `tests.backtesting.test_v74_fixture.load_v74_fixture`, `tests.backtesting.test_validate_component_cli.write_arms`/`write_folds`. **Created by this plan:** everything listed under "Files". **Created by v122 (not on `main` yet):** `permutation_test.arm_pair_permutation`/`_arms_main`/`_null_component`, checked in V128-12 Step 1.

## Parts

| Part | Tasks | Content |
|---|---|---|
| `2026-10-02-v128-fvg-displacement-audit_1-signal-code.md` | V128-1 .. V128-3 | Phase 1, TDD signal code: fvg filter, knobs, levels wiring (inert at default) |
| `2026-10-02-v128-fvg-displacement-audit_2-funnel-tooling.md` | V128-4 .. V128-6 | Phase 2, TDD script-layer tooling: judge routing, attribution and clause 6, Stage 1 judge |
| `2026-10-02-v128-fvg-displacement-audit_3-measurement.md` | V128-7 .. V128-15 | Phases 3–5: pre-registration, Stages −1/0/1/2/3, close-out, full suite and release |

## Parallelisation

- **Sequential chain V128-1 → V128-2 → V128-3:** V128-2's `ScanParams` test asserts `scan_params._FVG_MODES == fvg.FVG_MODES` (from V128-1). V128-3 reads `params.fvg_levels_mode` (from V128-2) and calls `find_fair_value_gaps(mode=, k=)` (from V128-1).
- **Group A (parallel, after V128-2):** V128-3, V128-4, V128-5. The files are disjoint (`levels.py`/`trade_chart.py`; `validate_component.py`; `fvg_attribution.py`). V128-4 depends on nothing in the chain. V128-5 consumes `fvg.filter_gaps` (V128-1) and the config fields (V128-2), but no symbol from V128-3 or V128-4. Its only shared contract with V128-4 is `acceptance.ClauseResult`'s existing field set (the `--mechanism-json` file is `dataclasses.asdict(ClauseResult)`).
- **V128-6 after V128-4 and V128-5:** it imports `validate_component.with_mechanism_clause` (V128-4) and `fvg_attribution.CANDIDATES` (V128-5).
- **V128-7 after V128-6:** the record quotes the exact CLI flags V128-4..V128-6 create. It may be *drafted* in parallel with code, but it is committed only after V128-6, and before V128-8.
- **V128-8 → V128-9 → V128-10 → V128-11 → V128-12 → V128-13, strictly sequential:** each stage's refusal stops the next. They are also all one worktree, all `logs/v128/`, and all `backtest-runner` dispatches that compete for the same CPU.
- **V128-12 waits on v122:** it consumes `arm_pair_permutation` from v122's V122-10. That is a cross-plan contract, so nothing in v128 may run it early.
- **V128-14 after the last stage that ran:** it consumes the stage results. **V128-15 last:** the one full-suite run, then the release bump (working-conventions: the bump goes after green).
- **Cross-plan edge:** v122's V122-8/V122-9 also edit `scripts/backtest/validate_component.py` (its `main()` argument line and `_run_gate`). If v122 is being implemented concurrently, V128-4 must not run at the same time as those tasks. Whichever merges second resolves the conflict in `main()`'s parser line and keeps both flags.

## Progress

Closed 2026-10-08. V128-1..V128-9, V128-14 and V128-15 done; V128-10..V128-13 deliberately not run: **REFUSED at Stage 0 under both gates, VALIDATION budget intact** (results: `docs/superpowers/results/2026-10-02-v128-fvg-stage0.md`). The code merged inert (`FVG_LEVELS_MODE` default `all`, bot 2.2.1), so this closes to `implemented/`, not `no-lift/`. `Bump: bot patch` was delivered. `Edge: expectancy` is the target class; the measured result is no lift.
