Bump: bot minor · ui minor
Edge: expectancy (Phase 1) · volume (Phase 3, conditional on Phase 1) · none (integrity) for Phase 2

# Strategy path goes live — Implementation Plan (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put the strategy signal path into the live scan behind a three-mode flag with a shadow soak and a pre-registered trust rule, split P&L into frozen `main`/`weak` ledgers shown in Discord and the admin UI, record a no-lookahead entry-context snapshot on every live, backtested and replayed trade, and re-derive the seven bullish-only strategy masks on TRAIN under current arithmetic.

**Architecture:** A new `scanning/strategy_pass.py` runs after the confluence pass on completed daily bars and reuses `entry_filters.entries_for` + `builders.build_strategy_plan`, so live signals are the backtest's signals by construction. `tracking/ledger.py` owns the `main`/`weak` rule; the trade record and `TradePlanV2` carry a frozen `ledger` field through the existing JSONB `doc`. `edge/context.py` is the single feature function stamped at three sites. `backtesting/arm_rule.py` holds the pre-registered bearish-arm decision clauses; `scripts/backtest/measure_bearish_arms.py` drives them.

**Tech Stack:** Python 3.11, pandas/numpy, discord.py, Flask (`swingbot/admin/api_v1`), Angular signals (`frontend/`), pytest, the existing `backtest.run_backtest` / `backtest_scenarios.replay_scenarios` simulators.

**Spec:** `docs/superpowers/specs/2026-09-17-v93-strategy-path-live-design.md`

## Global Constraints

- Mode `off` (the default) must leave the scan byte-identical to today; asserted by Task 8's snapshot test.
- `main` is computed as `ledger != "weak"` everywhere, so every pre-existing trade (no field) stays `main`. The two ledgers are never summed.
- NO-LOOKAHEAD (`docs/claude/architecture.md`): every `entry_context` input is the entry bar or earlier; a feature that cannot be computed yet is `None`.
- TRAIN window `2020-01-01..2023-12-31`. **No VALIDATION shot is spent anywhere in this plan.** `acceptance.py` and `backtest_wf.py` gate constants are not touched.
- Bearish-arm arithmetic: `--exit-model v2 --scale-out --tp2 levels --frictions on`, liquidity-filtered cached universe, RS laggard rule applied through the snapshot's `rs_combined`.
- Backtest cost cap for the snapshot: ≤ 20 % slowdown on one strategy over TRAIN (Task 21 measures it).
- Per task: `python scripts/dev/testrun.py file tests/<path>.py` (~7 s) or `npm test -- --include <spec>` for frontend. **One** `python scripts/dev/testrun.py full` and **one** `cd frontend && npm test` at the very end (Task 27). Never per task.
- Any backtest run over ~2 minutes is dispatched to the `backtest-runner` subagent with flushed per-symbol progress.
- Every new config key is added to `.env.example` in the same task (tests/test_env_example_sync.py enforces it).
- Numbers for the release come from `VERSION.json` at close-out (Task 27), never from this document.

## Parts

| File | Phase | Tasks |
|---|---|---|
| `_1-alert-path.md` | Phase 1a — config, ledger, strategy pass, soak rule | 1–9 |
| `_2-read-side.md` | Phase 1b — snapshot/dashboard/Discord/admin/frontend read side, docs | 10–15 |
| `_3-context-snapshot.md` | Phase 2 — `entry_context` and its three stamp sites | 16–21 |
| `_4-bearish-arms.md` | Phase 3 — gate schema, arm rule, measurement, decision, final verification | 22–27 |

## Parallelisation

- **Sequential first:** Task 1 (config fields) and Task 2 (`ledger` rule + plan field) — every later Phase 1 task consumes them. Task 3 (trade record + stats) after Task 2.
- **Phase 1a, Group A (parallel after Task 3):** Task 4+5 (`strategy_pass.py` helpers — same file, so one worker), Task 9 (`edge/strategy_soak.py` + `first_seen_price` in `plan_manager.py`). Tasks 6→7→8 are sequential (6 produces the stamp/embed helpers 7 consumes; 8 wires 7 into `scan_run.py`).
- **Phase 1b, Group B (parallel after Task 8):** Task 10 (analytics core), Task 12 (Discord commands), Task 13 (admin API) — three disjoint trees. Task 11 (dashboard API) after Task 10 (consumes `ledger.split_by_ledger`). Task 14 (frontend) after 11 and 13 (consumes their JSON shapes). Task 15 (docs) last in the phase.
- **Phase 2:** Task 16 (`edge/context.py`) first. Then **Group C (parallel):** Task 18 (`backtest.py` + `asof_context.py`), Task 19 (`backtest_scenarios.py`), Task 17+20 (`params.py`, `plan_types.py`, `performance.py`, `analyze.py`, `strategy_pass.py` — one worker). Task 21 (range script export + cost measurement) after 18. **Phase 2 must not run beside Phase 1a Group A** — Task 20 and Task 8 both edit `analyze.py`/`scan_run.py`/`strategy_pass.py`.
- **Phase 3:** sequential throughout (22 → 23 → 24 → 25 → 26); depends on Phase 2 (Task 24 reads `rs_combined` from Task 18's as-of builder).
- **Task 27** last, after everything.

## Orientation

- Pull one task: `grep -n "^### Task 7" -A 160 docs/superpowers/plans/2026-09-17-v93-strategy-path-live_1-alert-path.md`
- Phase boundaries: `grep -n "^# Phase" docs/superpowers/plans/2026-09-17-v93-strategy-path-live_*.md`
- Verify that no task was dropped across parts:
  ```bash
  for f in docs/superpowers/plans/2026-09-17-v93-strategy-path-live_*.md; do
    echo "$(basename $f): $(grep -o '^### Task [0-9]*' $f | tr '\n' ' ')"
  done
  ```
