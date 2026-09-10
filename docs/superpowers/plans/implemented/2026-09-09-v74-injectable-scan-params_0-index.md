# v74 — Injectable scan parameters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/implemented/2026-09-09-v74-injectable-scan-params-design.md`
**Bump:** bot patch — pure refactor; `ScanParams.from_config()` reproduces today's behaviour exactly and no alert, chart or screen moves. Numbers resolved at close-out from VERSION.json.
**Edge:** none (integrity) — the enabling half. Buys no edge itself; makes the decision surface addressable so v75 (search engine) and v76 (selection statistics) can find edge in it.

**Closeout:** Complete. C2 records 33 replay blind spots; B4 preserved the documented live/replay gate divergence.\n\n**Goal:** Make every knob governing a trade-plan decision settable per evaluation, observable by the backtest harness, and safe to vary inside a process pool — so a knob the harness cannot see fails a test instead of silently wasting a pre-registered shot.

**Architecture:** One frozen, picklable `ScanParams` dataclass in `swingbot/scan_params.py`, built by `from_config()` at the boundary and varied with `dataclasses.replace()`. It is threaded through the *shared* plan layer (`builders.py`, `levels.py`) that both the live scan and `replay_scenarios` already call, and the *duplicated* gating layer is collapsed into one pure `passes_gates(...)` both paths call, so parity holds structurally rather than by test.

**Tech Stack:** Python 3.11, dataclasses, pytest. No new dependencies.

## Parts

This plan is one document across three files. **Never read a part whole** — pull one task with `/task-brief A1` or `grep -n "^### Task A1" -A 140 docs/superpowers/plans/2026-09-09-v74-*.md`.

| File | Tasks | What it builds |
|---|---|---|
| `_0-index` (this file) | — | Header, global constraints, parallelisation, task map |
| `_1-params-and-seam` | A1, A2, B1, B2, B3, B4 | `ScanParams`, the field classification, and the threading through shared + gating layers |
| `_2-verification-and-closeout` | C1, C2, C3, D1, D2, D3 | Fixture, observability test, parity gate, dead-gate fix, docs, version bump, full suite |

Task ids do not change when a file splits, so `/task-brief C2` works without anyone knowing which part it landed in.

## Global Constraints

Every task's requirements implicitly include this section.

- **Zero observable difference to the bot.** `ScanParams.from_config()` must reproduce today's behaviour exactly. Task C3 is the gate on this; a task that changes a produced plan has a bug, not a feature.
- **No knob's default changes.** This plan tunes nothing, runs no grid, and does not touch `CONFLUENCE_GATES`' values, only their home.
- **Frozen constants stay frozen:** `MIN_RISK_REWARD_RATIO = 1.5`, `MAX_RISK_REWARD_RATIO = 2.5`, `BREAKEVEN_TRIGGER_FRACTION = 0.5`, `tp1_fraction = 0.50`. This plan makes them *injectable*; it never sets them to anything but their config value.
- **No re-run of the July 2026 confluence grid** (spec finding 9) and no resolution of the `BASE_GATES` divergence (spec finding 8). Both are recorded for the human partner; neither is this plan's to decide.
- **`ScanParams` must stay frozen and picklable.** This is the property v75's max-statistic permutation depends on. Any task that adds a mutable field (`list`, `dict`, `set`) breaks it — use tuples.
- **The module is `swingbot/scan_params.py`, not `swingbot/params.py`.** `swingbot/core/planning/params.py` already exists (exit-v2 constants); two modules named `params` would be a permanent reading hazard. This is a deliberate deviation from the spec's proposed path.
- **Per-task tests are narrow:** `python scripts/dev/testrun.py file tests/<path>.py` (~7s). The full suite runs **once**, in Task D3.
- **NO-LOOKAHEAD is unchanged.** No task may make a backtest path read live state (journal, plans.json, registry) it does not already read.

## Deliberate deviations from the spec

Recorded so a reviewer can tell a decision from an omission.

- **`simulate_exit` is not threaded.** The spec names it alongside
  `build_confluence_plan` as shared-layer work. Verified: `exit_sim.py` has
  **zero** `config.` reads, and `scale_out` is already an explicit keyword
  argument. There is nothing to un-globalise, so threading `params` through it
  would be churn with no behaviour or searchability gain. Same for
  `targets.py` (zero reads).
- **`passes_gates(plan, params)` became two functions.** The spec's single
  predicate cannot represent what `replay_scenarios` actually does: two of the
  three gate uses are *inputs* to `levels.build_scenarios` (an effective
  min-reward and an effective max-stop, each the larger of a global and a
  per-horizon bound), not a test over a finished plan. B3 ships
  `scenario_gate_inputs(params, horizon)` and `passes_confluence(n, params)`.
- **The searchable class is 35 fields, not the spec's estimated ~45.** A2
  enumerates them exactly; the spec's figure was an estimate made before the
  live-only reclassification of `NEAR_CLOSE_*` and `REVERSAL_*`.
- **`BREAKEVEN_TRIGGER_FRACTION` and `TP1_FRACTION` are out of `ScanParams`.**
  They are module constants, not `config.FIELDS` entries; see Task A1.

## Parallelisation

- **Sequential spine:** A1 → A2 → B3 → B4. Each consumes the previous task's public symbols (`ScanParams` → `Field.search_class` → `passes_gates` → its second caller).
- **Group 1 (parallel), after A1:** B1 (`builders.py`) and B2 (`levels.py`) — different files, no shared symbol, each consuming only `ScanParams`.
- **Group 2 (parallel), after B4:** C1 (fixture) and D1 (dead-gate fix) — D1 touches only `scripts/backtest/*.py` and is independent of the seam entirely.
- **Sequential:** C2 after C1 and A2 (needs both the fixture and the classification). C3 after C1. D2 after D1 and C2 (docs describe the finished exempt list). D3 last.
- **One writer at a time on `swingbot/scan_params.py`.** A1 and A2 both write it and are sequential for that reason alone. Concurrent sessions share this working tree — two agents on one file do not merge, the second silently overwrites the first.

## Task map

| Task | Deliverable |
|---|---|
| A1 | `ScanParams` frozen dataclass + `from_config()`; frozen/pickle tests |
| A2 | `search_class` on `config.Field`, all 121 fields classified, coverage test |
| B1 | `builders.py` takes `params`; the RR band stops being a global read |
| B2 | `levels.py` takes `params`; AVWAP + volume-profile flags stop being global reads |
| B3 | `passes_gates()` extracted; `replay_scenarios` uses it; gate dicts collapse |
| B4 | `scan_run` uses `passes_gates()`; the duplicated gating is gone |
| C1 | Committed two-ticker fixture for the seam tests |
| C2 | Per-knob observability test + the exempt list with reasons |
| C3 | Zero-observable-difference parity gate |
| D1 | The dead gate made loud in all five scripts |
| D2 | `backtest-methodology.md` + `known-traps.md` + `.codex/AGENTS.md` |
| D3 | `VERSION.json` bump, `version_history.json` regeneration, full suite |
