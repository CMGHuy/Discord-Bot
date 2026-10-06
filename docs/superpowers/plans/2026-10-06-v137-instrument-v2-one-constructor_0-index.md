# v137 Instrument v2, phase 1: one plan constructor. Implementation Plan, index

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this plan whole**: pull one task with `/task-brief IC3` or `grep -n "^### Task IC3" -A 200 docs/superpowers/plans/2026-10-06-v137-instrument-v2-one-constructor_*.md`.

**Spec:** `docs/superpowers/specs/2026-10-06-v136-backtest-instrument-v2-design.md` (phase 1 row of "Phases", section 3 "One constructor (phase 1)", cross-cutting rules 1 and 3)
**Bump:** bot minor
**Edge:** none (integrity)

**Goal:** Under a new `instrument` contract, the backtest builds every plan through `builders.build_strategy_plan`, exactly as the live scan does. The v1 instrument stays the default and stays byte-identical, and a pinned v1 golden proves it now and at every later phase.

**Architecture:** A new package, `swingbot/core/backtesting/instrument/`, gets `contract.py`. It holds `InstrumentSpec(version, fill_model, cost_model)` and `resolve("v1" | "v2")`, and it is the only place an instrument's rules are defined. `run_backtest` / `run_backtest_daterange` take the spec as a keyword argument (`instrument=`). The spec is passed in, never read from a global, and `None` means v1. When `spec.live_constructor` is true (v2), `run_backtest` hands off to a new replay loop, `_replay_live_constructor`. That loop builds each plan with `_live_plan_at`, which is the same `build_strategy_plan(df.iloc[:i+1], i, ...)` call that `scanning/strategy_pass.build_strategy_plan_at` makes. The v1 loop is untouched apart from two verbatim extractions (`_signal_masks`, `_summarize`). `_trade_plan_at` is deleted as a constructor, but v1 has to stay byte-identical, so its arithmetic survives as `_v1_plan_levels`, private to the frozen v1 path. A guard test confines it to `run_backtest`'s v1 loop and the two v1 parity reports. `measure_fib_diagnostic.py` moves to `build_strategy_plan`.

**Tech Stack:** Python 3.11, pandas/numpy, pytest (+xdist via `scripts/dev/testrun.py`), radon, the frozen OHLCV fixtures in `tests/fixtures/ohlcv/` (TSLA, DOCU, DELL; `tests/fixtures/ohlcv_parity.py`).

## Progress

Not started. Update this block when a phase closes.

## Where to work

- **Branch and worktree:** `2026-10-06-v137-instrument-v2-one-constructor`, at `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-06-v137-instrument-v2-one-constructor` (written `$WT` below; the main tree is `$R` = `E:/Documents/Private/Projects/Discord-Bot`). Create it in IC1 Step 0 with the `worktree-lifecycle` skill. Name the worktree in every subagent dispatch.
- **Never `cd`.** Use absolute paths and `git -C $WT`. `python $WT/scripts/dev/testrun.py file tests/...` resolves test paths against `$WT` (it runs pytest with `cwd` = its own repo root).
- **No backtest cache is needed.** Every test here reads the committed fixtures under `tests/fixtures/`. No measurement runs in this plan.
- **This plan file is committed on `main`.** Only the implementation is branched. Each task commits on the branch. After every task run `git -C $R status --short` and confirm the main tree is unchanged.
- **The bump (`bot` minor) is applied at close-out (`/close-out`)**, after IC7 is green. No task here edits `VERSION.json`.

## Global Constraints

- **Rule 1, verbatim from the spec:** "v1 is byte-identical until cutover. `resolve("v1")` reproduces today's behaviour exactly, and a pinned golden run proves it at every phase." The golden is captured in IC1, on unmodified code, before any other task touches `swingbot/`.
- **Rule 3, verbatim:** "One plan constructor. Every replay builds plans through `build_strategy_plan`; `_trade_plan_at` is deleted." How this plan applies it: under the v2 instrument, `backtest.py` builds plans only through `build_strategy_plan`. The name `_trade_plan_at` is gone from `swingbot/` and `scripts/`. The v1 instrument keeps the identical arithmetic as `_v1_plan_levels` because rule 1 requires it. The live builder differs from it by design: it resolves a journal-backed `stop_mult`/TP2, applies opex widening, takes a `level_map`, and computes its own series per call. Routing v1 through the builder would therefore change v1 output whenever any of those flags is on.
- **v2 refuses live-state flags (a lookahead guard).** Under the v2 instrument, `run_backtest` raises `ValueError` if `config.DATA_DRIVEN_STOPS_ENABLED`, `config.STALL_EXIT_ENABLED` or `config.OPEX_CAUTION_ENABLED` is on. With any of them on, the builder would read the live journal (stop_mult, TP2 R, time stop, stall-exit day) or today's opex tier from the wall clock. The simulated journal in spec phase 5 lifts the guard. v1 never reaches the builder, so it is unaffected.
- **The contract is passed in, never read from a global.** `run_backtest(..., instrument=None)`, where `None` means v1. Nothing reads a module-level "current instrument".
- **Phase-1 contract scope:** `InstrumentSpec` carries `version`, `fill_model` and `cost_model` and nothing else. There are no span, universe or fold fields (phase 3 adds them). In phase 1, `resolve("v2")` carries v1's fill and cost values; phase 2 sets the values from spec section 2. The only v2 behaviour this phase delivers is the plan constructor.
- **The parity target is the live constructor call:** `strategy_pass.build_strategy_plan_at(df_completed, ...)` calls `build_strategy_plan(df_completed, len(df_completed) - 1, ticker=..., strategy=..., horizon_key=..., direction=...)` with no `level_map`. The v2 replay makes exactly that call. That is why v2 refuses `tp2_mode != "none"`: the live path has no such knob.
- **Out of scope here:** fills, gap-through and costs (phase 2); spans, `--instrument` on scripts and the date-literal guard (phase 3); the scan replay, gates, the 2% cap and the simulated journal (phase 5). `arms/strategy_engine.py` is not touched.
- **Complexity:** every new or changed function must be < 15 (`python -m radon cc -s -n C <files>`). Legacy functions must never get worse. Measured on `main` at `6485b8bb`: `run_backtest` 58, `run_backtest_daterange` 25, `_trade_plan_at` 13, `measure_fib_diagnostic.collect` 11, `parity_exits.main` 21, `parity_sizing.main` 18.
- **Config determinism in tests:** every test that runs a backtest or builds a plan first calls `pin_code_defaults(monkeypatch)` from `tests/backtesting/test_pullback_dryup_witness.py`. That pins every `config.FIELDS` entry to its code default, so a developer's `.env` cannot move the golden.
- **Green means `0 failed` and `0 xfailed`.**

## Parallelisation

| Task | Files (disjoint?) | Depends on | Why sequential |
|---|---|---|---|
| IC1 golden | `tests/backtesting/instrument/{__init__,golden,test_v1_golden}.py`, `tests/fixtures/instrument/v1_golden.jsonl` | — | Must be captured before any task edits `swingbot/core/backtesting/backtest.py` |
| IC2 contract | `swingbot/core/backtesting/instrument/{__init__,contract}.py`, `tests/backtesting/instrument/{__init__,test_contract}.py` | — | Can run **in parallel with IC1**. The only shared file is the empty `tests/backtesting/instrument/__init__.py`; both tasks create it identically ("create if absent") |
| IC3 v2 replay | `swingbot/core/backtesting/backtest.py`, `tests/backtesting/instrument/test_live_constructor_replay.py` | IC1, IC2 | Needs the golden (its v1 proof) and imports `resolve` (contract) |
| IC4 parity test | `tests/backtesting/instrument/test_constructor_parity.py` | IC3 | Calls `bt._live_plan_at` and `bt._signal_masks`, both created by IC3 |
| IC5 diagnostic migration | `scripts/backtest/measure_fib_diagnostic.py`, `tests/scripts/test_measure_fib_diagnostic.py` | — | Can run **in parallel with IC2–IC4**: disjoint files, and it uses only `bt._trade_plan_at` / `_plan_series`, which exist until IC6 |
| IC6 retire `_trade_plan_at` | `backtest.py` + every remaining reference (listed in the task) + guard test | IC3, IC4, IC5 | Edits `backtest.py` after IC3. Renames symbols inside IC3's and IC5's test files. The guard asserts on `_live_plan_at` (IC3) and on the diagnostic no longer importing the old name (IC5) |
| IC7 full suite | — | IC1–IC6 | Final gate |

## Parts

| Part | Tasks |
|---|---|
| `2026-10-06-v137-instrument-v2-one-constructor_1-golden-contract-replay.md` | Phase A: IC1 (v1 golden), IC2 (contract skeleton); Phase B: IC3 (v2 replay through `build_strategy_plan`) |
| `2026-10-06-v137-instrument-v2-one-constructor_2-parity-diagnostic-retire.md` | Phase B: IC4 (constructor parity), IC5 (`measure_fib_diagnostic` migration), IC6 (retire `_trade_plan_at`); Phase C: IC7 (full suite) |
