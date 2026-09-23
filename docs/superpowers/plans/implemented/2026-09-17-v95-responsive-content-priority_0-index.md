Bump: ui minor · bot none
Edge: none (integrity)

**Closed 2026-09-23, merged to `main`, ui 1.21.0.** All tasks (A1–E4) landed
as designed. Real findings along the way, fixed rather than exempted: E2's
breakpoint guard caught undeclared width queries D1/D3 left behind
(`risk.ts` 720px, `settings-tab.ts` 700px — both corrected to 639 and
verified live); E4's full-suite run caught a stale v85 D22 consistency test
that didn't know C1 had superseded `sb-control-bar` with `sb-toolbar` for
Trades. D3–D5's own test sketches contained errors (a non-interactive
element the D3 test wrongly targeted, D4's `SCAN_CONTROLS` test naming
tuning controls that don't exist in this codebase, D5's test asserting
zero occurrences of a literal value its own reference implementation
contains) — corrected against the running code rather than implemented
as written.

# v95 — Responsive content priority: implementation plan (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every column, control and panel in the admin UI one declared
viewport floor, and a named destination when it falls below it, so nothing is
hidden at any width — enforced by a test rather than by inspection.

**Architecture:** One pure resolver (`ui/priority.ts`) exposing
`inlineFrom: Viewport` and `isInline()`. Three consumers route demoted items to
three destinations: columns into `DataTable`'s existing `expansion` template,
controls into a toolbar sheet, panels into a collapsed digest. Workspaces
declare `inlineFrom` and delete their hand-rolled media queries.

**Tech Stack:** Angular 20 (signals, `input()`, `computed()`, zoneless),
TypeScript, Vitest + `@angular/core/testing`, plain CSS with custom properties.

**Spec:** `docs/superpowers/specs/2026-09-17-v95-responsive-content-priority-design.md`

---

## Global Constraints

Copied verbatim from the spec. Every task's requirements implicitly include
this section.

- **The four breakpoints are fixed** and are floors, not ceilings:
  `BREAKPOINTS = { sm: 640, md: 1024, lg: 1440, xl: 1920 }` in
  `frontend/src/app/ui/breakpoints.ts`. `Viewport = 'xs' | 'sm' | 'md' | 'lg' | 'xl'`.
  No task adds, removes or changes a breakpoint value.
- **`inlineFrom` means "the narrowest viewport at which this item appears
  inline"**. `'xs'` = always inline. Below its floor an item is **demoted, never
  removed**.
- **v80 D4 stands.** `sb-data-table` keeps its pinned identity column, its
  `.phone-sort` select, and the test
  `'keeps the table below the breakpoint -- no cards'`. No task reintroduces
  `.card`, `.card-head`, `.card-body`, `.card-value` or `.card-actions`.
- **Three honesty guards**, all testable:
  1. the toolbar sheet button shows a count of demoted controls that are
     **non-default**;
  2. a panel **force-expands** when its data is stale, errored or unrepresentative,
     regardless of `inlineFrom`;
  3. demotion never drops an accessible name.
- **AMENDMENT (recorded during execution, see SDD ledger):** the original text
  of this constraint read *"The Analytics workspace is out of scope. v94
  rebuilds it and adopts this model there (spec §11). No task in this plan
  edits `frontend/src/app/workspaces/analytics/`."* That was correct when
  the plan was written; **v94 has since merged and closed** (shipped as
  1.20.0/1.10.2) **without** adopting this responsive model — its 5 tab
  files still carry undeclared `800px` width queries. There is no longer a
  live v94 plan to hand the requirement to, and the human partner chose to
  fix Analytics' breakpoint drift directly inside v95 rather than open a
  separate follow-up plan. **Task A7** (new, added during execution) brings
  `workspaces/analytics/tabs/*.ts` onto the declared breakpoint set — the
  only file scope Analytics gets in this plan; no other Phase A–D task may
  edit `workspaces/analytics/`. **Task E3 is superseded** (see its own note)
  since the v94 hand-off it performed no longer has a target.
- **`Bump: bot none`.** No task edits Python, the bot, or the API.
- **Touch floor:** `tokens.css` already raises `--control-h`/`--row-h` to 44px
  and `--text-control` to 16px under `(pointer: coarse), (max-width: 639px)`.
  Components must not opt out with `min-height: 0`.
- **jsdom lays nothing out.** No test asserts on a computed width or on a media
  query resolving. Viewport-dependent behaviour is driven through
  `ViewportService` or an explicit override input, the way `cardsAt` already is.
- **Per-task verification is narrow:**
  `cd frontend && npm test -- --include <the one spec file this task touched>`.
  A full `npm test` is the plan's final task only (E4).

---

## Parts

| Part | Phase | Tasks | Subject |
|---|---|---|---|
| `_1-foundations.md` | A | A1–A7 | breakpoint drift, `priority.ts`, touch floor, overflow fixes, Analytics breakpoint drift (A7, added during execution) |
| `_2-primitives.md` | B | B1–B8 | DataTable routing, toolbar sheet, panel collapse |
| `_3-workspaces-a.md` | C | C1–C7 | trades, dashboard, calendar, watchlist |
| `_4-workspaces-b.md` | D | D1–D6 | risk, system, versions, gallery |
| `_5-gate.md` | E | E1–E4 | parity gate, E3 superseded (v94 already closed), full verification |

Task ids are stable across file splits: `grep -rn "^### Task C3"
docs/superpowers/plans/` finds a task without knowing which file holds it.

## Parallelisation

**Phase A**
- **Sequential:** A1 before everything in the plan — it introduces
  `ui/priority.ts`, which every later phase consumes.
- **Group A-i (parallel):** A2, A3, A4 — `shell.css`, `button.ts` (+ its call
  sites), and `histogram.ts`/`recent-activity.ts` respectively. Disjoint files,
  no shared contract.
- **Sequential:** A5 after A2 (the tablet band assumes the drift is already
  corrected, or it encodes the wrong numbers). A6 after A5.
- **A7 (added during execution):** independent of A2–A6 — disjoint files
  (`workspaces/analytics/tabs/*.ts`). Can run any time in Phase A, but must
  land before E2 (the repo-wide breakpoint guard) or E2 fails on Analytics.

**Phase B**
- **Sequential throughout.** B1 defines `inlineFrom` on `ColumnDef<T>`; B2 and
  B3 consume it; B4–B5 build the toolbar on the resolver A1 introduced; B6–B8
  build panel collapse on B4's sheet conventions. Each task consumes the
  previous task's exported surface, and B2, B3 and B8 all edit
  `data-table.ts`/`panel-grid.ts` — the same files. Do not dispatch these
  concurrently; the second writer silently overwrites the first.

**Phase C**
- **Group C-i (parallel):** C1+C2 (trades), C3+C4 (dashboard), C5+C6 (calendar),
  C7 (watchlist) — four workspace directories, no shared file. Within each
  pair the tasks are sequential.
- **Sequential:** all of Phase C after all of Phase B.

**Phase D**
- **Group D-i (parallel):** D1+D2 (risk incl. `matrix.ts`), D3+D4 (system),
  D5 (versions), D6 (gallery). One workspace directory each.

**Phase E**
- **Sequential throughout.** E1 asserts against declarations every Phase C and D
  task produces; running it earlier fails for the right reason at the wrong
  time. E4 is last by definition.

## Verification cadence

- **Per task:** the narrow `npm test -- --include <one spec file>` named in that
  task's steps, plus — on every Phase C and D task — a screenshot pass at
  390 / 768 / 1024 via the connected Chrome DevTools MCP. The audit behind this
  spec found defects the suite does not catch; on a workspace task the visual
  pass is not optional.
- **Per part:** nothing extra. The narrow runs are the gate until E4.
- **Once, as E4:** `cd frontend && npm test` over everything. This plan edits no
  Python, so `python scripts/dev/testrun.py full` is **not** part of its gate.
  Green means `0 failed` and `0 xfailed`.

## Exit criteria

1. `ui/priority.ts` exists, is pure, and is covered at every boundary the way
   `breakpoints.spec.ts` covers `viewportFor`.
2. No file under `frontend/src/app/` contains a `@media` breakpoint value that
   is not one of 640 / 1024 / 1440 / 1920, except `tape.css` and
   `earnings-calendar.ts`, which are documented exceptions.
3. No component sets `min-height: 0` on an interactive host.
4. The parity gate (E1) passes: every registered column, control and panel is
   reachable at all five viewports.
5. `--cell-wrap` and `--sep-wrap` appear nowhere in `frontend/src/`.
6. v80 D4's three phone-mode guarantees still pass unmodified.
7. `cd frontend && npm test` is green once, at E4.
