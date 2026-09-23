# Standard Arm Producer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-09-23-v100-arm-producer.md`
**Bump:** none
**Edge:** none (integrity)

**Goal:** One stamped, keyed arm producer (`scripts/backtest/measure_arms.py`) behind a pluggable engine interface, plus funnel guards in `validate_component.py` — Stage −1 reachability, full-width rule, paired MDE, stamp enforcement — so no future pre-registration spends compute or a shot on an instrument that cannot see its component.

**Architecture:** New package `swingbot/core/backtesting/arms/` holds small single-purpose units (pairing, windows, reachability registry, knob overrides, engine protocol + two engines, provenance). The CLI wires them; `validate_component.py` gains a stamp gate in front of its existing stages. `run_backtest` and every existing `measure_*.py` script are untouched.

**Tech Stack:** Python 3.11+, numpy, pandas, pytest. numpy only — no scipy (absent from the Docker image, see `acceptance.py` docstring).

## Global Constraints

- **Reopens nothing.** No closed pre-registration is re-run past Stage −1 (`docs/claude/backtest-methodology.md` table; `.claude/hooks/guardrails.py:CLOSED_PREREGISTRATION_KNOBS`). A smaller paired MDE is not grounds to re-run v92 H1 or anything else.
- **No gate constant changes.** `ALPHA`, `MDE_POWER`, `NON_INFERIORITY_R`, `GEOMETRY_MAX_DROP_PCT`, `VOLUME_MAX_CUT_PCT`, `WIN_RATE_FLOOR_PP` are untouched.
- **`run_backtest`, `_trade_plan_at`, `--emit-registry` and all existing `scripts/backtest/measure_*.py` are not modified.**
- **NO-LOOKAHEAD:** every plan is built from `df.iloc[:i+1]`; exits may walk forward (the `run_scenario_backtest` / `run_backtest` convention). Load the `no-lookahead` skill before Task V100-5.
- **Never read `data/journal.json` from a measurement path** (it is local fixture data). Journal-reading knobs are classified `journal_dependent` and refused statically.
- **Tests:** iterate with `python scripts/dev/testrun.py file <path>`; the full suite runs once, in Task V100-11 only.
- **Green means `0 failed` and `0 xfailed`.** Never add an `xfail`.
- No `cd` in Bash commands (breaks the relative guardrails hook).

## Deviations from the spec, found while planning (record in the results doc, Task V100-10)

1. **No `keys.py` / `KeyedTrade`.** `acceptance.ArmTrade` already carries a pairing `key`; it gains optional `source` and `direction` fields (default `None`, so pre-v100 JSON rows load and pair exactly as before). `arms/pairing.py` holds the helpers.
2. **No `ScanParams` threading task.** The four "plumbing gap" knobs (`RSI_DIV_MIN_CONSECUTIVE_TURN`, `MA_RIBBON_CONFIRM_BARS`, `SR_MIN_LEVEL_TOUCHES`, `FIB_TARGET_1_0_EXTENSION`) are read from `config` globals at call time inside strategy entry filters / fib targets, and act only on the *strategy-source* population `replay_scenarios` never builds. The engines apply knob deltas to `config` **inside each worker process** (spawned workers never see a parent's mutation — the reason v92's in-process `config.X = ...` pattern cannot be pooled), and the strategy engine then observes them. The `plumbing_gap` class is therefore unnecessary.
3. **Reachability classes are `reachable` / `live_scan_only` / `journal_dependent` / `outside_replay`.** `exit_only` folds into `reachable` (outcomes, not plan fields, are compared). `journal_dependent` is new (`DATA_DRIVEN_STOPS_ENABLED`, `STALL_EXIT_ENABLED`) — the existing EXEMPT reasons already say replay must not read live journal state. `outside_replay` covers universe construction, sizing/portfolio, live switches and the dedicated-harness DCB knobs.
4. **Paired MDE is bootstrap-SE based, not closed-form.** `mde_paired` takes the ticker-cluster bootstrap SD of the delta statistic (pairing preserved by the shared ticker draw, clustering handled by construction) and scales it by `sqrt(observed_n / target_n)`. This one estimator covers subset (veto), exit-only and zero-overlap designs, where a McNemar formula covers only the second.
5. **Signal-window, not data, isolation.** Stamps restrict *signal* dates; exits walk forward past the window end, as every existing harness does. `refused:window-contact` tests the stamp's signal window.
6. **New token `refused:stage-mismatch`** — a stamp from the wrong producer stage (e.g. a pilot file handed to `--stage mde`).
7. **Validation stage requires `--preregistration <path>`** in the producer; the path is recorded in the stamp.

---

## Parts

| Part | Tasks |
|---|---|
| `2026-09-23-v100-arm-producer_1-foundations.md` | Phase A — V100-1 … V100-6 |
| `2026-09-23-v100-arm-producer_2-producer-funnel.md` | Phases B–C — V100-7 … V100-11 |

## Parallelisation

- **Phase A, Group 1 (parallel):** V100-2 (`acceptance.py` `mde_paired` region + `acceptance_harvest.py`) and V100-3 (`arms/windows.py`, `arms/reachability.py`) — disjoint files, no shared symbols. **But** V100-2 edits `acceptance.py`, which V100-1 also edits: V100-1 first.
- **Sequential:** V100-1 before V100-2 (same file) and before V100-4 (`arm_trade_from_plan` source/direction). V100-4 before V100-5 (`SKIPPED`, `engine.get_engine` imports `strategy_engine`). V100-3 before V100-6 (`windows` constants). V100-6 can run parallel to V100-4/V100-5 (disjoint files, consumes only V100-3). V100-7 after V100-1..6 (consumes all). V100-8 after V100-7 (imports `measure_arms.cached_universe`). V100-9 after V100-4/V100-5 (uses `run_arm` with both engines) and may flip entries V100-3 created. V100-10 after everything (proof runs the finished producer). V100-11 last.
- **Shared-tree warning:** concurrent sessions share this working tree — implement on a branch/worktree per `worktree-lifecycle`, never two agents on `acceptance.py` or `reachability.py` at once.
