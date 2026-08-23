Version: ui 1.8.1 · bot 1.3.3
Bump: ui patch (1.8.1 → 1.8.2) — a wholly new, additive workspace. Nothing an
existing user of the six current workspaces sees changes shape. `bot` none:
every endpoint is a read-only aggregation over data the bot already writes.
Edge: none (integrity) — an observability page. It surfaces day-of-week and
streak patterns a human can act on, but changes no gate, discriminator, exit
or sizing rule, so it claims no expectancy, harvest or volume effect.
**Spec:** `docs/superpowers/specs/2026-08-22-v53-pnl-calendar-design.md`

# P&L Calendar Implementation Plan — index

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `/calendar` admin workspace showing a month grid of daily
realized P&L — dollars by default, R-multiple on a toggle — filterable by
strategy and horizon, with a day-click drawer listing that day's closed
trades.

**Architecture:** A pure core module (`swingbot/core/analytics/pnl_calendar.py`)
joins `TradeLog`'s real `realized_pnl_amount` with `journal.json`'s
tags/MFE/MAE by trade id and aggregates by calendar day. Two read-only Flask
routes project it. An ngrx-signals store fetches them; one Angular component
renders the grid, the summary strip and the drawer. Layering follows
`docs/claude/architecture.md`: core computes, the route projects, the store
fetches, the component renders.

**Tech Stack:** Python 3.11, Flask, pytest · Angular 21.2, `@ngrx/signals`
21.1, vitest 4 (zoneless). No new dependency in either half — the drawer,
select, panel, metric-card and money/R formatters all already exist.

## The parts

This document is split because a single file carrying all 12 tasks came to
117 KB, against the 120 KB hard limit in
`docs/claude/document-conventions.md`. Per that rule the plan was **split,
not compressed** — every task keeps its full test and implementation code.

| Part | Phases | Tasks | Size | What it delivers |
|---|---|---|---|---|
| `_1-backend` | 1–2 | 1–5 | 46 KB | `pnl_calendar.py` aggregation + the two `/api/v1/calendar/*` routes |
| `_2-frontend` | 3–5 | 6–12 | 64 KB | models, `ApiClient`, `CalendarStore`, the `Calendar` workspace, route/nav/icon wiring |

**Read one part, never both.** `_1-backend` is self-contained and its
deliverable (the finalized JSON response shapes) is what `_2-frontend`
consumes. Pull a single task with `/task-brief` or
`grep -n "^### Task 7" -A 200 <part>`.

## Global Constraints

Every task in every part implicitly includes all of these.

1. **No api_v1 module may bake a `config.DATA_DIR`-derived path at import
   time.** Construct `TradeLog()` / `JournalStore()` *inside the view*, as
   `analytics.py` does. `tests/admin/conftest.py:34-47` documents why:
   `swingbot.admin.api_v1.*` is deliberately excluded from the reload list,
   so an import-time path would keep pointing at the real `data/` directory
   during tests.
2. **`swingbot/core/**` must never import from `swingbot/admin/**`.**
   `closed_r()` and `closed_pnl()` live in `swingbot/admin/dashboard.py` and
   are therefore **off limits** to the core module. Use
   `metrics.r_multiple(trade)` (`swingbot/core/analytics/metrics.py:96`) —
   the repo's single shared R computation.
3. **A trade's strategy label is `primary_strategy_label(t)`, never
   `t["strategy"]`.** `performance.py:162-184`: every trade from the live
   confluence engine carries the identical literal `"S/R Confluence"` in
   `t["strategy"]`, so filtering on that field groups everything into one
   bucket. `api_v1/analytics.py:260` already does
   `{**t, "strategy": primary_strategy_label(t)}`; match it.
4. **A day is `closed_at[:10]` — a string slice, not a timezone
   conversion.** This *amends* the spec's "Timezone and day boundaries"
   section. The established core convention is the slice
   (`metrics.calendar_returns` uses `closed_at[:7]`,
   `cumulative_pnl_by_strategy` uses `closed_at[:10]`), `closed_at` is always
   written as UTC ISO, and a Berlin-converted day here would disagree with
   the monthly `calendar` figures the Analytics page renders from the same
   records. Do not introduce `zoneinfo` into this module.
5. **Empty means `None`, never `0.0`.** `metrics.win_rate` returns `None`
   with zero win/loss trades precisely so "no data yet" and "0%" never look
   the same on a UI (`metrics.py:125-131`). Every aggregate in this plan
   follows it.
6. **A day with no closed trades is omitted from the grid payload, not
   emitted as zero.** `metrics.calendar_returns`' docstring is the precedent:
   "a flat month and a month you did not trade are different facts, and a
   calendar heatmap that paints them identically is lying about activity."
7. **Every new api_v1 endpoint gets a contract test using
   `assert_shape`** from `tests/admin/api_v1_contract.py`. It enforces the
   **exact** key set — an undeclared key fails as loudly as a missing one.
8. **Angular conventions:** no `standalone: true` (Angular 21 default);
   `changeDetection: ChangeDetectionStrategy.OnPush` on every component;
   new control flow only (`@if` / `@for (…; track …)` / `@switch`) — `*ngIf`
   and `*ngFor` have zero occurrences in `frontend/src`; signals-based
   `input()` / `input.required()` / `output()` / `model()`, never the
   `@Input()` decorator.
9. **Components never inject `HttpClient` and never inject `ApiClient`.**
   Stores call `ApiClient`; components read stores
   (`frontend/src/app/api/api-client.ts:51-62`). A workspace store is
   provided on the component (`providers: [CalendarStore]`), not in root.
10. **Querystring filter names are `strategy` and `horizon`**, matching
    `api_v1/trades.py:58`. The horizon vocabulary is `2w 4w 2m 3m 4m 5m 6m
    7m 8m 9m` (`swingbot/core/market/strategy_types.py:HORIZONS`).
11. **Test commands.** Backend one file:
    `python scripts/dev/testrun.py file tests/analytics/test_pnl_calendar.py`.
    Frontend: `cd frontend && npm test`. Pre-commit gate:
    `python scripts/dev/testrun.py full`. Green means `0 failed` **and**
    `0 xfailed`; reference baseline `1686 passed, 66 skipped, 0 failed`.

## Parallelisation

- **Group 1 (parallel with Group 2):** Tasks 1, 2, 3 all create and extend
  the single new file `swingbot/core/analytics/pnl_calendar.py` and its
  single test file — so they are **sequential with each other**, but the
  whole group is independent of everything frontend.
- **Group 2 (parallel with Group 1):** Task 8 alone
  (`calendar.helpers.ts` — pure date math, no store and no HTTP). Disjoint
  files from Group 1, no contract dependency, so it is the one task that can
  genuinely be worked at the same time as the backend.
- **Sequential, and why:** Task 4 after Task 3 (the route consumes every
  function Tasks 1–3 produce). Task 5 after Task 4 (same file,
  `calendar.py`). Task 6 after Task 5 (the TypeScript interfaces must match
  the finalized response shape). Task 7 after Task 6 (the store consumes
  `ApiClient`'s new methods and the new models). Tasks 9, 10, 11 after Task 7
  and strictly in order — **all three edit `calendar.ts`**, and this working
  tree is shared, so two agents on that file overwrite rather than merge.
- **Task 12 last.** It touches four files (`app.routes.ts`,
  `app.routes.spec.ts`, `ui/icon.ts`, `shell/shell.ts`) and its route spec
  asserts the component from Task 9 exists.

## Close-out

Per `docs/claude/document-lifecycle.md`, when this plan stops being live
work: tick the boxes, write the Progress block below, then `git mv` **all
three parts of this plan and the spec** into `implemented/` in the closing
commit. The `ui` patch bump (`1.8.1 → 1.8.2`) is its **own** commit, goes
**last**, and must be followed by
`python scripts/dev/build_version_matrix.py` plus a commit of
`swingbot/admin/version_history.json` — omitting that regeneration is a red
suite (`test_the_committed_file_matches_the_current_generator`).

## Progress

**Complete.** All 12 tasks implemented on branch
`worktree-2026-08-22-v53-pnl-calendar`, one commit per task, TDD throughout
(every step's test was run red before its implementation).

Gates at close: backend `2210 passed, 136 skipped, 0 failed` (0 xfailed);
frontend `912 passed` across 58 files; `npx tsc --noEmit -p tsconfig.app.json`
clean.

**Bump taken: `ui` 1.8.3 -> 1.8.4**, not the 1.8.1 -> 1.8.2 this header
predicted. VERSION.json had moved on twice (v51, v52) between authoring and
execution; the *level* the header predicted -- a `ui` patch, `bot` none -- is
what was applied.

### Corrections made to the plan while executing it

Seven, each recorded in the commit that made it. They are listed here because
a plan read later is evidence, and a plan whose text disagrees with the code
it produced is misleading evidence.

1. **`CalendarStore`'s refetch effect double-fired.** As written, `onInit`
   called `store.load()` inside an `effect`, and `load()` reads `month`,
   `strategy` and `horizon` -- so those reads became effect dependencies and
   every `setStrategy`/`setMonth`/`stepMonth` issued TWO requests. Three
   specs caught it ("found 2 requests"). Fixed with `untracked()`.
2. **`Button`'s selector is `button[sb-button]`, not `<sb-button>`.** The
   element form the plan wrote (Task 9) would have rendered an unknown
   element.
3. **`MetricCard`'s tone vocabulary is `plain|pnl|caution`**, not the
   `pos|neg` Task 10 wrote. `pnl` is the only tone allowed to go green or
   red and takes its sign from the value itself.
4. **Money units come from `ConnectionStore.currency()`, never the literal
   `'$'`** the plan used in Tasks 9, 10 and 11. `format.ts:38` and
   `metric-card.ts:77` both say so, and analytics/dashboard/trades all obey
   it -- a euro account must not read its own figures labelled in dollars.
5. **The drawer specs need `installDialogPolyfill()`.** `Drawer` is a real
   `<dialog>` and jsdom implements neither `showModal()` nor `close()`; all
   five of Task 11's specs threw until the repo's existing polyfill was
   installed in `seed()`.
6. **`spa.WORKSPACES` needs `"calendar"`.** Task 12 added the Angular route
   but not the Flask rule, so `/calendar` would have worked when clicked and
   404ed on reload or a pasted link. `test_every_angular_route_is_served_on_reload`
   was the single red test in the first full-gate run.
7. **The controls block had to use `sb-control-row`.** `tokens.spec.ts`'s
   "no workspace hand-rolls a control row" failed on the hand-rolled flex
   row. The month stepper stays hand-rolled and is now declared in
   `NOT_CONTROL_ROWS` with its reason.

Also worth carrying forward: **the plan's frontend verification commands do
not work in this repo.** `npx tsc --noEmit -p tsconfig.json` is a no-op (the
root config is solution-style -- `"files": []` plus references -- and exits 0
on a file with an undefined type name); use `-p tsconfig.app.json`. And
`npx vitest run <file>` fails at `document is not defined`, because the runner
is Angular's `@angular/build:unit-test`, which supplies the jsdom environment;
use `npx ng test --include=<file>`.
