# v73 — Plan-view projection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-09-04-v73-plan-view-projection-design.md`
**Version:** ui 1.11.0 · bot 1.6.1
**Bump:** ui minor (1.11.0 → 1.12.0) · bot patch (1.6.1 → 1.6.2) — two components, separately graded.
**Edge:** none (integrity) — display correctness buys no trading edge.

**Goal:** Give pending and partial plans one derivation, shared by every surface, so a plan reads the same in Discord and in the admin SPA and neither shows a number that is no longer true.

**Architecture:** One pure module, `swingbot/core/presentation/plan_view.py`, turns a `TradePlanV2` plus an optional live price into a `PlanView` carrying the display facts *and their provenance*. The three existing renderers become thin formatters over it. Nothing is stored; nothing in the exit engine changes.

**Tech Stack:** Python 3.11, dataclasses, pytest; Angular 20 signals + Karma for the SPA half. No new dependencies.

## Parts

| File | Tasks | What it builds |
|---|---|---|
| `_0-index` (this file) | — | Header, constraints, parallelisation, task map |
| `_1-projection` | A1, A2, A3 | `PlanView`, and the PENDING / ACTIVE / PARTIAL branches |
| `_2-surfaces` | B1–B4, C1–C3 | The three Python renderers, the cross-surface guard, the SPA, the null sort, verification |

**Never read a part whole** — pull one task with `/task-brief B2` or
`grep -n "^### Task B2" -A 120 docs/superpowers/plans/2026-09-04-v73-*.md`.

## Global Constraints

Every task's requirements implicitly include this section.

- **Presentation only.** No task edits `plan_manager.py`, `exit_sim.py`, `lifecycle.py` or `config.py`. `_step_active`, `_step_partial` and `_step_extended` are untouched. If a task seems to need an exit-rule change, it is the wrong task.
- **No new stored fields on `plans.json`.** Everything is derived at read time. Storing it would create a second authority for plan state — the exact failure `docs/claude/known-traps.md` records for `PlanManager.check_bar()`.
- **`plan_view()` is pure.** Plan in, dataclass out. No store access, no file I/O, no network, no `datetime.now()` inside — the caller passes `now`. This is what makes it testable without fixtures and safe to call from three places.
- **`runner_floor(entry, tp1)` is the only legacy stop fallback.** Never `plan.stop_loss` for a PARTIAL plan. It is `entry + 2/3 × (tp1 − entry)` — a floor **in profit, above entry** — imported from `swingbot.core.planning.exit_sim`, never reimplemented.
- **Every branch is tested in both directions.** `runner_floor` is direction-agnostic by formula (`exit_sim.py:146-148`), so a bearish regression is invisible in a bullish-only suite.
- **Do not add embed fields with a raw `embed.add_field()`** — go through the `sections["headline"]` accumulator (`known-traps.md`). No task here should need to, but B3 touches embed-adjacent code.
- **Per-task tests are narrow:** `python scripts/dev/testrun.py file tests/presentation/test_plan_view.py` (~7s), or for the SPA `cd frontend && npm test -- --include <one spec>`. Both full suites run **once**, in Task C3.

## Parallelisation

- **Sequential:** A1 → A2 → A3. All three append to one file and each branch consumes the shapes A1 defines.
- **Group 1 (parallel), after A3:** B1 (`admin/api_v1/trades.py`), B2 (`commands/plans.py`), B3 (`core/scanning/plan_table.py`). Disjoint files, no shared symbol beyond the projection each imports.
- **Sequential:** B4 after all of Group 1 — the cross-surface guard drives all three and cannot pass until all three exist.
- **Sequential:** C1 after B1 (the SPA consumes the wire shape `trades.py` produces; writing it first means writing against a contract that does not exist). C2 after C1. C3 last.
- **One writer at a time on `plan_view.py`.** Concurrent sessions share this working tree — two agents on one file do not merge, the second silently overwrites the first.

---
