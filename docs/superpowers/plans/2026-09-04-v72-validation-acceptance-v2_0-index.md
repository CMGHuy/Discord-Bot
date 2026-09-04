# v72 — Validation acceptance v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-09-04-v72-validation-acceptance-v2-design.md`
**Version:** ui 1.11.0 · bot 1.6.1
**Bump:** bot patch (1.6.1 → 1.6.2) — new module and CLI, no observable difference to any alert, chart or screen.
**Edge:** none (integrity) — buys no edge; stops edge that is not there from being adopted.

**Goal:** Build a single acceptance module that decides whether a feature ships, replacing nine dialects of per-plan gate logic with one discrimination-first gate that win rate must pass and target geometry cannot fake.

**Architecture:** One numpy-only module, `swingbot/core/backtesting/acceptance.py`, owns a neutral `ArmTrade` record, the statistics (mix-standardised win rate, ticker-cluster bootstrap, MDE), and the six-clause gate. One CLI, `scripts/backtest/validate_component.py`, runs the four-stage funnel over it. Measurement scripts produce two arms of `ArmTrade` and hand them to `evaluate()`; they no longer define what passing means.

**Tech Stack:** Python 3.11, numpy 2.4.6, pandas, pytest. No new dependencies.

## Parts

This plan is one document across four files. **Never read a part whole** —
pull one task with `/task-brief A3` or
`grep -n "^### Task A3" -A 120 docs/superpowers/plans/2026-09-04-v72-*.md`.

| File | Tasks | What it builds |
|---|---|---|
| `_0-index` (this file) | — | Header, global constraints, parallelisation, the task map |
| `_1a-acceptance-core` | A1, A2, A3 | `ArmTrade`, mix-standardised win rate, the ticker-cluster bootstrap |
| `_1b-acceptance-gate` | A4, A5, A6 | MDE precheck, the six-clause `evaluate()`, results-doc rendering |
| `_2-fixture-and-funnel` | B1, B2, C1, C2, C3, D1, D2, D3 | v68 regression fixture, fold-gate re-metric, funnel CLI, docs, verification |

Task ids do not change when a file splits, so `/task-brief C2` works without
anyone knowing which part it landed in.

## Global Constraints

Every task's requirements implicitly include this section.

- **numpy only — never import scipy in `swingbot/`.** scipy is installed on this dev machine but is **not in `requirements.txt`**, so it is absent from the Docker image. `acceptance.py` ships in that image. Normal quantiles are hardcoded constants with a comment; everything else is numpy.
- **No ML in the live path** (`docs/claude/backtest-methodology.md`). This module is statistics, not a model, and `swingbot/` still imports no sklearn/torch.
- **Frozen constants stay frozen:** `MIN_RISK_REWARD_RATIO = 1.5`, `MAX_RISK_REWARD_RATIO = 2.5`, `BREAKEVEN_TRIGGER_FRACTION = 0.5`, `tp1_fraction = 0.50`. This plan reads them; it never sets them.
- **Win rate is over win+loss only; expectancy is over all closed trades** (excluding `not_triggered`, including scratches and timeouts). This matches `measure_dcb_veto._aggregate` and the methodology doc. Every statistic in this plan obeys it.
- **v68's verdict is untouchable.** This plan regenerates a v68 population to test an *instrument*. `DEAD_CAT_BOUNCE_VETO`'s default stays `false` no matter what the new gate says about it, and `swingbot/config.py` is not edited by any task here.
- **New pre-registrations only.** No task re-runs, re-scores or changes the default of `RS_GATE`, `AVWAP_LEVELS_ENABLED` or the level-lifecycle stops.
- **Per-task tests are narrow.** `python scripts/dev/testrun.py file tests/backtesting/test_<file>.py` (~7s). The full suite runs **once**, in Task D3.
- New pre-registered gate constants, set here and not to be tuned afterwards: `NON_INFERIORITY_R = -0.01`, `GEOMETRY_MAX_DROP_PCT = 2.0`, `VOLUME_MAX_CUT_PCT = 25.0`, `ALPHA = 0.05`, `BOOTSTRAP_RESAMPLES = 10_000`, `MDE_POWER = 0.80`.

## Parallelisation

- **Sequential spine:** A1 → A2 → A3 → A5. Each consumes the previous task's public symbols (`ArmTrade` → `standardised_win_rate` → `bootstrap_delta` → `evaluate`).
- **Group 1 (parallel), after A1:** A4 (`mde_win_rate`) and C1 (`ANCHORED_FOLDS` date fix) — different files, no shared symbol. A4 needs only `ArmTrade` and `win_rate`; C1 touches only `backtest_wf.py` constants.
- **Group 2 (parallel), after A5:** A6 (results-doc rendering) and B1 (fixture generator) — `acceptance.py`'s renderer vs a new standalone script, disjoint files, and B1 consumes only `arm_trade_from_plan` from A1.
- **Sequential:** B2 after both A5 and B1 (the regression test needs the gate *and* the fixture). C2 after A3 (the re-metric'd fold gate is documented against `delta_standardised_win_rate`). C3 after A6 and C2 (the CLI wires every stage). D1 after C3 (the docs describe the finished CLI's stage names). D2 after D1. D3 last.
- **One writer at a time on `acceptance.py`.** A1–A6 all append to it and are sequential for that reason alone, whatever their logical dependencies. C2 and C3 import from it and must not modify it. Concurrent sessions share this working tree — two agents on `acceptance.py` do not merge, the second silently overwrites the first.

---
