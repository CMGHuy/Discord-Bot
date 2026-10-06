# v138 Instrument v2, phase 4: Statistics. Implementation Plan, index

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this plan whole**: pull one task with `/task-brief IS5` or `grep -n "^### Task IS5" -A 200 docs/superpowers/plans/2026-10-06-v138-instrument-v2-statistics_*.md`.

**Spec:** `docs/superpowers/specs/2026-10-06-v136-backtest-instrument-v2-design.md` (§4 Statistics, and the phase-4 row of its Phases table)
**Bump:** bot minor
**Edge:** none (integrity)

**Goal:** Ship `swingbot/core/backtesting/instrument/stats.py`: a seeded week-clustered bootstrap (ISO week of entry date, across all tickers, whole weeks resampled, 10,000 replicates) selectable by every verdict path through a plain `cluster="ticker" | "week"` parameter whose default keeps instrument v1 byte-identical; and a committed pre-registration ledger with Benjamini–Hochberg q-values, backfilled, plus a helper that appends a row and prints its q-value. Reported, never gating.

**Architecture:** `stats.py` is numpy-only and imports nothing from `acceptance`, so `acceptance.cluster_bootstrap` can import it lazily when `cluster="week"` without an import cycle. The ticker path keeps its exact body: the selector is a guard plus an early branch, so the default draws the same RNG stream as today. A characterization test (IS4) pins sha256 digests of every ticker-cluster verdict path on `main` before the selector exists. The `cluster` parameter is threaded through `acceptance`, `acceptance_harvest`, `arms/selection.evaluate_cell`, `scripts/backtest/funnel.py` and `scripts/backtest/harvest_select.py`. Nothing maps an instrument version to a unit yet: phase 6 (cutover) wires `--instrument v2` to `cluster="week"`. The ledger is a git-tracked JSONL file, not a runtime store: no Postgres, no Alembic.

**Tech Stack:** Python 3.11, numpy (no scipy; it is not in `requirements.txt`), pytest, `scripts/dev/testrun.py`.

## Progress

Not started. Update this block when a phase closes and at close-out (IS11).

## Where to work

- **Branch and worktree:** `2026-10-06-v138-instrument-v2-statistics`, at `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-06-v138-instrument-v2-statistics`. IS1 Step 0 creates it with the `worktree-lifecycle` skill. All paths below are relative to that worktree, and every command runs inside it. Name the worktree in every subagent dispatch. After each task run `git -C E:/Documents/Private/Projects/Discord-Bot status --short` and confirm the main tree is unchanged.
- **Phase 1 runs in parallel.** Plan v137 (phase 1, one plan constructor) also creates the package `swingbot/core/backtesting/instrument/` with `contract.py`. This plan **never imports `contract.py`** and never needs `InstrumentSpec`/`resolve()`. The package `__init__.py` this plan creates is a docstring only; IS1 creates it only if absent, and IS11 says how to resolve the add/add merge conflict if v137 lands first.
- **No backtest runs.** Nothing in this plan runs `measure_arms.py`, `run_backtest_range.py` or any grid, so the `backtest-gate` skill does not apply and no `BACKTEST_CACHE_DIR` is needed.
- **This plan file is committed on `main`** by the controller. Only the implementation branches.

## Global Constraints

- Week-clustered bootstrap, verbatim from the spec: "trades grouped by the ISO week of their entry date across all tickers; whole weeks resampled, 10,000 replicates, seeded. Replaces ticker clustering for every v2 verdict. The acceptance thresholds in `backtest-methodology.md` are unchanged; only the resampling unit changes."
- `WEEK_BOOTSTRAP_RESAMPLES = 10_000`, `WEEK_BOOTSTRAP_SEED = 42` (the seed every existing verdict uses: `funnel.BOOTSTRAP_SEED`, `acceptance.evaluate`'s default).
- ISO week key format `"YYYY-Www"` from `date.isocalendar()` (so 2021-01-03 is `2020-W53`, 2024-12-30 is `2025-W01`). A trade with no entry date raises `ValueError`; it is never silently dropped or put in a catch-all week.
- **v1 is byte-identical.** `cluster` defaults to `"ticker"` everywhere. With the default, every function returns exactly what it returned at `6485b8bb`, `render_json` emits no new key and `render_markdown` prints no new text. IS4's digests are the proof; they are never re-pinned to make a failure pass.
- `CLUSTER_UNITS = ("ticker", "week")`. Any other value raises `ValueError` naming `cluster`.
- This phase does **not** depend on phase 1's `contract.py`. The unit is a plain string parameter; phase 6 maps `InstrumentSpec` to it.
- Pre-registration ledger, verbatim from the spec: "committed file `docs/superpowers/results/preregistration-ledger.jsonl`, one row per pre-registration: id, hypothesis, instrument version, N, ExpR, p-value, verdict. A git-tracked record, not a runtime store (no Postgres). Existing pre-registrations are backfilled from their results docs; those without a recorded p-value carry `p: null`. Every new verdict prints its BH q-value across the ledger — **reported, not gating**."
- Ledger row fields, in this order: `id, date, hypothesis, instrument, n, exp_r, p, verdict, record`. `date` and `record` are provenance (when, and the repo-relative path of the results doc the row was read from). `instrument` is `"v1"` or `"v2"`. `verdict` is one of `PASS, FAIL, NO-LIFT, UNMEASURABLE, WITHDRAWN, OPEN`. `n` is a non-negative int or null, `exp_r` a finite number or null, `p` a number in [0, 1] or null.
- BH q-values: step-up, `q_(k) = min_{j >= k} (m * p_(j) / j)`, capped at 1, aligned with input order. Null p-values pass through as null and do not count toward `m`.
- Out of scope (spec "Out of scope" and phase boundaries): gating on a q-value; changing any acceptance threshold; re-running any closed pre-registration; wiring `--instrument`/`cluster="week"` into `validate_component.py`, `measure_arms.py` or any CLI (phase 6); the clause-5 permutation tests (`permutation_test.py`, `acceptance_harvest.permutation_p_expectancy`), which stay ticker-clustered because §4 changes the bootstrap only; the unpaired MDE formulas `intracluster_correlation`/`design_effect`/`mde_win_rate`/`mde_expectancy_r` (not a bootstrap); editing the methodology's clause table text "ticker-cluster bootstrap" (spec §5.4, at cutover).
- Every function written or changed ends at cyclomatic complexity < 15 (`python -m radon cc -s -n C <files>` prints nothing for new code). No legacy function touched here is at or above C today; none may reach it.
- Every task runs its own narrow test files (`python scripts/dev/testrun.py file <test>`). The full suite runs **once**, in IS11. Green means `0 failed` and `0 xfailed`.
- Commits are small and scoped as each task's last step states. Never bundle two tasks into one commit. The version bump is its own commit, last, on `main` (IS11).

## File map and interfaces

| File | Responsibility |
|---|---|
| `swingbot/core/backtesting/instrument/__init__.py` | Package marker, docstring only (IS1; created only if absent). |
| `swingbot/core/backtesting/instrument/stats.py` | `WEEK_BOOTSTRAP_RESAMPLES`, `WEEK_BOOTSTRAP_SEED`, `iso_week_key`, `group_by_week`, `week_cluster_bootstrap` (IS1); `bh_qvalues` (IS2); `LEDGER_PATH`, `LEDGER_FIELDS`, `VERDICTS`, `INSTRUMENTS`, `validate_ledger_row`, `load_ledger`, `append_ledger_row`, `ledger_qvalues` (IS3). |
| `swingbot/core/backtesting/acceptance.py` | `CLUSTER_UNITS`, `_check_cluster`, `_CLUSTER_NOTES`; `cluster` on `cluster_bootstrap`, `bootstrap_delta`, `mde_paired`, `_clause_win_rate`, `_clause_profit_floor`, `evaluate`; `AcceptanceResult.cluster`; conditional `cluster` in `render_json` / `render_markdown` (IS5). |
| `swingbot/core/backtesting/acceptance_harvest.py` | `cluster` on `_clause_expectancy_gain`, `_clause_win_rate_floor`, `evaluate_harvest` (IS6). |
| `swingbot/core/backtesting/arms/selection.py` | `cluster` on `evaluate_cell` (IS7). |
| `scripts/backtest/funnel.py` | `cluster` on `expr_lower_bound`, `score_cell`, `stage1` (IS7). |
| `scripts/backtest/harvest_select.py` | `cluster` on `_row`, `select` (IS7). |
| `scripts/reports/preregistration_ledger.py` | The append-and-print helper (IS8). |
| `docs/superpowers/results/preregistration-ledger.jsonl` | The ledger, backfilled with 53 rows (IS9). |
| `docs/claude/backtest-methodology.md`, `AGENTS.md` | One ledger paragraph and its condensed Codex mirror (IS9). |
| `tests/backtesting/_cluster_fixture.py` | Shared pinned arms (IS4). |
| `tests/backtesting/test_instrument_stats_bootstrap.py`, `test_instrument_stats_bh.py`, `test_instrument_stats_ledger.py`, `test_ticker_cluster_pin.py`, `test_acceptance_cluster_unit.py`, `test_acceptance_harvest_cluster_unit.py`, `test_verdict_helpers_cluster_unit.py`, `test_preregistration_ledger_file.py` | New tests. They live flat in `tests/backtesting/` on purpose, so this plan never creates `tests/backtesting/instrument/__init__.py`, which v137 may also create. |
| `tests/scripts/test_preregistration_ledger_cli.py` | CLI tests (IS8). |

Verified on 2026-10-06 at `6485b8bb` with `git grep -n` (re-check before use): `acceptance.cluster_bootstrap` / `bootstrap_delta` / `mde_paired` / `_clause_win_rate` / `_clause_profit_floor` / `evaluate` / `AcceptanceResult` / `render_json` / `render_markdown` / `BootstrapResult` / `BOOTSTRAP_RESAMPLES` / `ALPHA` / `ArmTrade` / `expectancy_r` / `delta_expectancy_r` / `delta_standardised_win_rate` / `_group_by_ticker`, `acceptance_harvest._clause_expectancy_gain` / `_clause_win_rate_floor` / `evaluate_harvest` / `HARVEST_VERSION`, `arms/selection.evaluate_cell` / `CellEval`, `funnel.expr_lower_bound` / `score_cell` / `stage1` / `cell_key` / `dir_rows` / `MIN_N_TRAIN` / `BOOTSTRAP_SEED`, `harvest_select._row` / `select`, `scripts/dev/build_version_matrix.py`, `tests/scripts/test_build_version_matrix.py`. Callers of the threaded functions that keep the default (and so stay v1): `scripts/backtest/validate_component.py:80,114,117,137`, `scripts/backtest/measure_fib_v103.py:184`, `scripts/backtest/measure_v104.py:161,280`, `scripts/backtest/measure_v113.py:154,174,245`, `scripts/backtest/measure_adaptive_trail.py:113`, `scripts/backtest/measure_stall_exit.py:108`, `swingbot/core/backtesting/acceptance_harvest.py:85,133`.

Created by this plan (do not `git grep` for them before their task): everything in the `stats.py` row (IS1–IS3), `acceptance.CLUSTER_UNITS` / `_check_cluster` / `_CLUSTER_NOTES` / `AcceptanceResult.cluster` (IS5), `tests/backtesting/_cluster_fixture.pinned_arms` / `FAST` (IS4), `scripts/reports/preregistration_ledger.py` (`build_parser`, `row_from_args`, `format_report`, `main`) (IS8), the ledger file (IS9).

## Review focus

1. **The ticker path must not move by one bit.** `cluster_bootstrap`'s ticker body is untouched; the selector only adds a guard and an early `return` for `"week"`. IS4's digests (bootstrap draws, `evaluate`, `evaluate_harvest`, `mde_paired`, `score_cell`, `evaluate_cell`, harvest `_row`) are checked after IS5, IS6 and IS7.
2. **Pairing survives the week draw.** Both arms are resampled with the same week draw, exactly as the ticker bootstrap shares its ticker draw. IS1's identical-arms test (every draw exactly 0) pins it.
3. **The week unit is market-wide.** Weeks pool every ticker; a test where every ticker shares its week's outcome shows a zero-width ticker interval and a wide week interval (IS1).
4. **No silent drops.** A trade with no entry date raises; an undefined statistic drops the draw (as today), never zero-fills.
5. **The ledger is honest about missing data.** `n`, `exp_r` and `p` are `null` wherever the record names no figure; no value is estimated or re-derived. The only recorded p in the backfill is v92 Hypothesis 2's degenerate `p=1.0000`, recorded as written.

## Parallelisation

- **IS1 first.** It creates the worktree and the package, and IS2, IS3 and IS5 consume `stats.py`.
- **Group A (parallel, after IS1):** IS2 + IS3 as one sequential lane (both edit `stats.py`: same file), and IS4 (two new test files only). Disjoint files; IS4 consumes nothing from IS2/IS3.
- **IS5 after IS1 and IS4.** Sequential edge: IS5 consumes `stats.week_cluster_bootstrap` (IS1) and must not start until IS4's pin is committed against unmodified code, or the pin would no longer prove anything.
- **Group B (parallel, after IS5):** IS6 (`acceptance_harvest.py` + its test) and IS7 (`arms/selection.py`, `funnel.py`, `harvest_select.py` + its test). Disjoint files; both consume IS5's `cluster` keyword on `bootstrap_delta`/`cluster_bootstrap`/`evaluate` (contract dependency on IS5, not on each other). Both only *read* `test_ticker_cluster_pin.py`.
- **IS8 after IS3.** Sequential edge: the CLI consumes `append_ledger_row`, `ledger_qvalues`, `INSTRUMENTS`, `VERDICTS`, `LEDGER_PATH`. It may run in parallel with Group B (disjoint files).
- **IS9 after IS8.** Sequential edge: the ledger file is validated by IS3's `load_ledger`, and the methodology paragraph names IS8's command.
- **IS10 after IS1–IS9** (complexity sweep over every touched file).
- **IS11 last** (full suite, merge, release). It is the only full-suite run.

## Parts

| File | Tasks |
|---|---|
| `2026-10-06-v138-instrument-v2-statistics_0-index.md` | header, constraints, file map, review focus, parallelisation (this file) |
| `2026-10-06-v138-instrument-v2-statistics_1-stats-module.md` | Phase A: IS1, IS2, IS3 |
| `2026-10-06-v138-instrument-v2-statistics_2-cluster-selector.md` | Phase B: IS4, IS5, IS6, IS7 |
| `2026-10-06-v138-instrument-v2-statistics_3-ledger-and-release.md` | Phases C and D: IS8, IS9, IS10, IS11 |
