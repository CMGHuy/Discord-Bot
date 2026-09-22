# Analytics Workspace Redesign (v94) — Implementation Plan, Part 0: Index

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

Bump: ui minor · bot patch
Edge: none (integrity)

**Spec:** `docs/superpowers/specs/2026-09-17-v94-analytics-workspace-redesign-design.md` — read it whole (343 lines) before any task; every task below argues from a numbered decision (D1–D12) or honesty rule (H1–H5) in it.

**Goal:** Rebuild the admin Analytics workspace as six question-ordered tabs (Overview · Attribution · Execution · Edge · Pipeline · Tuning) driven by one control bar whose scope every panel obeys, with charts that state their N, blank thin cells, and never fail silently.

**Architecture:** Backend gains one `BookScope` value object (`swingbot/core/analytics/scope.py`) parsed once per request and applied by every analytics route; the page stops reading the all-time analytics snapshot. Frontend gains a shared chart hover layer and seven small SVG/CSS primitives, a scope-aware `AnalyticsStore` synced to the URL, and six tab components replacing the 2,233-line `analytics.ts`. Read side only: nothing in scan, planning, sizing or exit logic changes.

**Tech Stack:** Python 3.11 / Flask (`swingbot/admin/api_v1`), pandas-free pure-Python metrics; Angular 21 standalone components with signals and `@ngrx/signals` `signalStore`; vitest via `ng test`; hand-rolled inline SVG/CSS primitives in `frontend/src/app/ui/` (no charting library — spec D11).

## Prerequisite — v93 Phase 1b merged

**Do not start Phase 1 until `git log --oneline main | grep "feat(v93)"` shows Tasks 10, 11, 13 and 14 of `docs/superpowers/plans/2026-09-17-v93-strategy-path-live_2-read-side.md` merged.** They add `ledger` to `aggregate.DIMENSIONS`, a `ledger=` argument to `TradeLog.get_trades`, `weak` to `/analytics/performance`, `soak` to strategy rows, and a WEAK tile to `analytics.ts`. This plan absorbs all four; several tasks say "after v93" where a line number or symbol depends on them. **If a task's `Modify:` line range no longer matches, re-locate by the quoted symbol, never by the number.**

## Global Constraints

- **Branch/worktree:** `2026-09-17-v94-analytics-workspace-redesign` (superpowers:using-git-worktrees). Specs/plans commit on `main`; code commits on the branch.
- **Per-task verification is narrow:** `python scripts/dev/testrun.py file tests/<file>.py` or `python -m pytest <file>::<test> -v`; frontend `cd frontend && npm test -- --include <one spec>`. **The full suites run once, in Task V4.** Never `... full` or bare `npm test` inside a task.
- **Green = `0 failed`, `0 xfailed`.** A changed pass count is not a failure (`docs/claude/testing-cost.md`).
- **No new dependencies.** No charting library; `lightweight-charts` stays confined to the price chart.
- **Every new primitive:** standalone, `ChangeDetectionStrategy.OnPush`, plain data inputs, one spec file, one file under `frontend/src/app/ui/`, colours only via tokens (`--pos/--neg/--warn/--accent/--chart-1…6/--text-*`), text in text tokens never series colour (spec D11).
- **Thin-cell rule (H1):** any rate for `n < MIN_CELL_N` is `null` **from the server**; the client renders blank + N + dotted outline. Never compute a rate client-side to fill a null.
- **Scope echo (H2):** every scoped payload carries top-level `scope` and `n` from `scope.echo()`; all-time payloads carry `"scope": "all-time"`.
- **Failure ≠ emptiness (H4):** fetch failure → `sb-panel-error`; zero trades → `sb-empty-state`.
- **One axis per chart (H5).** SPY appears only in `%` unit, indexed to the range start.
- **Unit toggle (D3):** headline in `unit` (`r` default, `pct`, `money`); the currency figure is always rendered alongside, never only on toggle.
- **Never hard-code version numbers.** `VERSION.json` is read at close-out (Task V4).
- **Commit per task**, messages `feat(v94): …` / `test(v94): …` / `refactor(v94): …`; end with the attribution line in force for the session.
- **Do not read `analytics.ts` whole** (2,233 lines): `grep -n "<marker>" frontend/src/app/workspaces/analytics/analytics.ts` and `sed -n a,bp`.

## Parts

| Part | File | Phase | Tasks |
|---|---|---|---|
| 1 | `_1-backend-scope.md` | Phase 1 — Backend: scope, routes | B1–B9 |
| 2 | `_2-primitives.md` | Phase 2 — Frontend primitives, hover layer, palette | P1–P10 |
| 3 | `_3-shell-store.md` | Phase 3 — Models, API client, store, URL sync, shell | S1–S6 |
| 4 | `_4-tabs.md` | Phase 4 — Six tab components; retire the old page | T1–T7 |
| 5 | `_5-design-verify.md` | Phase 5 — Design pass, docs, release, full verification | V1–V4 |

Addressing: `grep -n "^### Task B4" -A 150 docs/superpowers/plans/2026-09-17-v94-analytics-workspace-redesign_1-backend-scope.md`, or `/task-brief B4`.

## File map (what is created / deleted)

**Backend — create:** `swingbot/core/analytics/scope.py`, `tests/analytics/test_scope.py`.
**Backend — modify:** `swingbot/core/analytics/metrics.py` (+`rolling_expectancy_r`, `avg_win_r`, `avg_loss_r`), `swingbot/core/analytics/aggregate.py` (+public `group_by`, `row_for`), `swingbot/admin/api_v1/analytics.py` (every route), `tests/admin/test_api_v1_analytics.py`, `tests/analytics/test_aggregate.py`, `tests/analytics/test_metrics_ratios.py`.

**Frontend — create (primitives):** `ui/chart-tooltip.ts`, `ui/panel-header.ts`, `ui/panel-error.ts`, `ui/share-bar.ts`, `ui/waterfall.ts`, `ui/dot-plot.ts`, `ui/strip-plot.ts`, `ui/small-multiples.ts`, `ui/heat-grid.ts`, `ui/unit-format.ts` — each with `.spec.ts`.
**Frontend — create (workspace):** `workspaces/analytics/scope-url.ts`, `scope-bar.ts`, `tabs/overview.ts`, `tabs/attribution.ts`, `tabs/execution.ts`, `tabs/edge.ts`, `tabs/pipeline.ts`, `tabs/tuning.ts` — each with `.spec.ts`.
**Frontend — modify:** `api/models.ts`, `api/api-client.ts`, `stores/analytics.store.ts` (rewritten in place, same export names where kept), `workspaces/analytics/analytics.ts` (becomes a ~120-line shell), `analytics.routes.ts`, `analytics.columns.ts`, `ui/histogram.ts`, `ui/bar-list.ts`, `styles/tokens.css` (only if the palette validator fails a step).
**Frontend — delete (Task T7):** `workspaces/analytics/sections/exit-quality.ts`, `sections/strategy-contribution.ts` and their specs; the old tab templates inside `analytics.ts`.

## Parallelisation (whole plan)

- **Sequential first:** B1 (every route consumes `parse_scope`/`select`/`echo`); P1 + P2 + P3 (every tab consumes the tooltip, panel header and error surface); S1 → S2 → S3 (models → client → store; every tab consumes the store's scope signals).
- **Group A (parallel, backend, after B1):** B2 performance, B3 equity-curve, B4 by-dimension, B5 heat-grid, B6 exit-quality, B7 journal, B8 strategies. Disjoint route functions in `analytics.py`; all append tests to `tests/admin/test_api_v1_analytics.py`, so **one agent per task and commit each before the next starts** (concurrent edits to one test file do not merge).
- **Group B (parallel, primitives, after P1):** P4 share-bar, P5 waterfall, P6 dot-plot, P7 strip-plot, P8 small-multiples, P9 heat-grid — one file + one spec each, no shared file.
- **Group C (parallel, tabs, after Phase 3 and Group B):** T1–T6 — one component file + spec each. T7 (retire old page) after all six.
- **Sequential last:** P10 palette (edits `tokens.css`), V1 design pass (touches every tab file), V2 screenshots, V3 docs, V4 verification + release.

## Task list

| ID | Title | Part |
|---|---|---|
| B1 | `scope.py`: `BookScope`, `parse_scope`, `select`, `echo`, `closed_only` | 1 |
| B2 | `/analytics/performance` scoped; `rolling_wr`, `rolling_exp_r` | 1 |
| B3 | `/analytics/equity-curve` scoped; `cum_pnl`, `cum_pct`, indexed SPY | 1 |
| B4 | `/analytics/by-dimension`: every dimension, floor-nulled rates, `avg_win_r`/`avg_loss_r` | 1 |
| B5 | `/analytics/heat-grid` (new): fat strategies × horizons, folded `Other` | 1 |
| B6 | `/analytics/exit-quality` scoped via journal `trade_id` join | 1 |
| B7 | `/analytics/journal` scoped | 1 |
| B8 | `/analytics/strategies`: scoped contribution + cumulative R; registry all-time; drop `heatmap` | 1 |
| B9 | `scope: "all-time"` on calibration and plans; scope-consistency test | 1 |
| P1 | `sb-chart-tooltip` + `hoverRows` helper | 2 |
| P2 | `sb-panel-header` (title · N · all-time · hint · Table) | 2 |
| P3 | `sb-panel-error` | 2 |
| P4 | `sb-share-bar` (part-to-whole) | 2 |
| P5 | `sb-waterfall` | 2 |
| P6 | `sb-dot-plot` (measure vs N, floor line) | 2 |
| P7 | `sb-strip-plot` (two groups, medians) | 2 |
| P8 | `sb-small-multiples` (shared y over `sb-line-chart`) | 2 |
| P9 | `sb-heat-grid` (floor-aware cells) + per-mark hover on histogram and bar-list | 2 |
| P10 | Palette validation of `--chart-1…6` in both themes | 2 |
| S1 | `models.ts`: scope types, payload updates, `analyticsUnit` preference | 3 |
| S2 | `api-client.ts`: `scopeParams`, every analytics method takes a scope; `analyticsHeatGrid` | 3 |
| S3 | `unit-format.ts`: `inUnit`, `unitLabel` | 3 |
| S4 | `analytics.store.ts`: scope/unit/measure state, per-tab loaders, N and freshness | 3 |
| S5 | `scope-url.ts` + `analytics.routes.ts`: URL ⇄ scope, old-tab redirects | 3 |
| S6 | `scope-bar.ts` + thin `analytics.ts` shell | 3 |
| T1 | Overview tab | 4 |
| T2 | Attribution tab | 4 |
| T3 | Execution tab | 4 |
| T4 | Edge tab | 4 |
| T5 | Pipeline tab | 4 |
| T6 | Tuning tab (moved, restyled) | 4 |
| T7 | Retire old templates, sections and dead store code | 4 |
| V1 | Design pass (frontend-design skill), light + dark | 5 |
| V2 | Screenshot pass, six tabs × two themes | 5 |
| V3 | Docs: `docs/features/features-admin.md`, `docs/commands.md` if touched | 5 |
| V4 | Full-suite verification, `VERSION.json` bump, close-out | 5 |
