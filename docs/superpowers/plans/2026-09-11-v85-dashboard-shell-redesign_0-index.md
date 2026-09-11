# v85 — Dashboard and shell redesign Implementation Plan (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Bump:** ui minor · bot patch — resolved at close-out from `VERSION.json`.
**Edge:** none (integrity)

**Goal:** Rebuild the admin SPA's shared chrome and its Dashboard to the
supplied mockup, and restyle the remaining seven workspaces so nothing ships
wearing the old design inside the new one.

**Architecture:** The shell's top bar becomes a single row that owns the
wordmark, the route's title/subtitle, the two ticker lanes, and the status
cluster; the left nav keeps its real routes and its MONITOR/REVIEW/SYSTEM
grouping and is restyled only. The Dashboard is recomposed from five new panel
components over the stores it already has, and its four stacked position
tables collapse into one lazily-fetched tabbed table. Two backend additions
serve it: a payoff-ratio metric and a bulk-close endpoint.

**Tech Stack:** Angular 21 (standalone, signals, OnPush), `@ngrx/signals`
stores, vitest + jsdom via `@angular/build:unit-test`, Flask API, pytest.

**Spec:** `docs/superpowers/specs/2026-09-11-v85-dashboard-shell-redesign-design.md`

---

## Global Constraints

Every task's requirements implicitly include this section.

- **Every colour comes from `frontend/src/styles/tokens.css`.** No hex literal
  in a component — `ui/primitives.spec.ts` fails the build on one. The palette
  already matches the mockup (`--bg: #0c0f16`, `--surface: #131722`,
  `--pos: #17c98e`, `--neg: #ff5470`, `--accent: #5593ff`); this plan adds
  tokens, it does not retune existing ones.
- **Zero third party in the frontend.** No icon font, no icon package, no CDN.
  New icons are hand-authored paths on the existing 16×16 grid at 1.5 stroke
  width in `ui/icon.ts`, matching the set already there.
- **Preferences persist through `PreferencesStore`, never `localStorage`.**
  A setting must follow the account, not the browser.
- **Components read signals; stores fetch.** No `subscribe()` and no refresh
  call in a workspace component. Each store's own effect owns both the first
  load and every refetch.
- **`null` is never `0`.** A metric that did not arrive renders as "no value",
  not as zero. This applies to the new payoff ratio exactly as it does to
  `profit_factor` today.
- **Every panel is independently async** through `sb-async`. One panel's failed
  fetch must never blank another's numbers, and a refetch failure keeps the
  previous figures on screen with a staleness marker.
- **Every manual state change appends to `data/manual_close_notify.json`**
  via `_queue_notify`. The bot is a separate process and that file is the only
  way it learns a human closed something.
- **Plans cannot be deleted.** `delete_trade` refuses plan-backed rows by
  design; this plan does not add `PlanStore.delete()`.
- **How the bot trades does not change.** No scan, strategy, sizing, or exit
  logic is touched anywhere in this plan.
- **Per-task verification is narrow:**
  - Frontend, one spec: `cd frontend && npx ng test --include <path>` — ~55s,
    prints `Test Files 1 passed`. Verified on `src/app/ui/clock.spec.ts`.
  - Backend, one file: `python scripts/dev/testrun.py file tests/<file>.py` (~7s).
  - **Never `testrun.py full` per task.** That is task R5-08 and nothing else.
  - `scripts/dev/testrun.py` is pytest only — it does not run frontend specs.
- **Never hard-code a version number.** `Bump:` states the level; the numbers
  resolve at close-out from the `VERSION.json` on disk at that moment.
- **Never edit files under `.claude/worktrees/`** from a main-tree session.

---

## Parts

Task ids are part-prefixed (`R1-01` … `R5-08`), so an id is unambiguous across
files and across the other live plans in this directory.

| Part | File | Content | Tasks |
|---|---|---|---|
| 1 | `_1-shell.md` | MCP fix, token and icon additions, route title/subtitle mechanism, merged top bar, ticker relocation, clock, zoom relocation, killswitch strip, nav restyle, responsive rules | 12 |
| 2 | `_2-backend.md` | payoff ratio in `metrics.py` and on the dashboard payload; `TradeLog` bulk close and its endpoint; client bindings | 6 |
| 3 | `_3-dashboard.md` | Portfolio Value, Trading Performance, Recent Activity derivation and panel, Watchlist, Market Movers, page assembly, explanatory copy behind affordances | 8 |
| 4 | `_4-positions.md` | the tabbed positions table, per-tab column sets including Cancelled, preference survival, row actions, close-all | 6 |
| 5 | `_5-workspaces.md` | the seven other workspace restyles, the `/ui` gallery, and the plan's single full-suite verification and release | 9 |

**Read one task, not one part** — `/task-brief R3-04`, or
`grep -n "^### Task R3-04" -A 120 docs/superpowers/plans/2026-09-11-v85-*_3-*.md`.

---

## Parallelisation

Two tasks may share a group only if they touch **disjoint files** *and*
neither consumes a symbol the other introduces. Concurrent sessions share this
working tree, so a wrong grouping silently overwrites work rather than
conflicting.

- **Sequential, first: R1-01** (chrome-devtools MCP). No code depends on it,
  but every visual checkpoint after it does.
- **Sequential, second: R1-02 and R1-03** (tokens, icons). One file each, and
  almost every later task consumes what they add.
- **Sequential, third: R1-04 through R1-12** (the shell). The route
  title/subtitle mechanism from R1-04 is a contract every workspace consumes,
  and R1-05…R1-12 all edit `shell.html`/`shell.css`/`shell.ts`, so they are a
  chain among themselves, not a group.
- **Group A (parallel), after R1-03:** the two backend strands — R2-01…R2-03
  (payoff ratio: `core/analytics/metrics.py`, `admin/api_v1/dashboard.py`) and
  R2-04…R2-06 (bulk close: `core/tracking/performance.py`,
  `admin/api_v1/trade_commands.py`). Disjoint files, no shared symbol. Within
  each strand the tasks are sequential.
- **Group B (parallel), after the shell and after Group A:** R3-01, R3-02,
  R3-04, R3-05, R3-06 — the five new panel components, one new file each.
  R3-02 (Trading Performance) consumes the payoff-ratio field, which is why
  Group A precedes it. R3-03 (the activity derivation helper) precedes R3-04
  within the group's dependency order, so treat R3-03/R3-04 as one strand.
- **Sequential, after Group B: R3-07, R3-08** — page assembly and the copy
  affordances both edit `dashboard.ts`, which every Group B task would
  otherwise contend for.
- **Sequential: R4-01 … R4-06.** One chain: the table exists before its column
  sets, which exist before preference survival, which exists before the row
  menu and the bulk button. R4-06 also consumes R2-06's endpoint.
- **Sequential, before Group C: R5-01** — the consistency guard. It is
  committed deliberately failing, and it is the worklist every Group C task
  works against.
- **Group C (parallel): R5-02 … R5-08** — the seven workspace restyles and the
  `/ui` gallery, one workspace directory each, no shared file between them.
  R5-08 goes last within the group: it is where the guard from R5-01 finally
  turns green.
- **Sequential, final: R5-09** — full-suite verification and release, alone.

Group B and Group C are the only places more than one agent may work at once,
and only within a group.

---

## Exit criteria

The plan is done when all of these hold:

1. Every workspace renders inside the new chrome with no leftover in-page
   heading, no double title, and no old-style panel.
2. The Dashboard matches the mockup's structure: simplified Portfolio Value,
   the eight-metric Trading Performance panel, one tabbed positions table, and
   the Recent Activity / Market Movers / Watchlist bottom row.
3. No explanatory copy was lost — each piece named in D18 is reachable from
   the panel it explains.
4. `Close all open/partial` closes ACTIVE and PARTIAL positions, leaves
   PENDING alone, queues a notify record per position, and reports closed and
   failed counts separately.
5. Payoff ratio is on the dashboard payload and reads `null`, not `0`, when
   there are no losers.
6. Screenshots of every workspace at desktop and phone width are captured and
   reviewed (R5-09).
7. `python scripts/dev/testrun.py full` reports `0 failed` and `0 xfailed`,
   and the frontend suite passes.

---

## A note on what this plan must not quietly become

The mockup shows a search box, a notification bell, an intraday equity curve,
a "+ New Trade" button, Market Movers' "Most Active" tab, and a Settings nav
entry. Four of those have no backing data or endpoint, one has no route, and
one has no create path. The spec refuses each by name. **A task that finds
itself building a facade over absent data has misread the spec** — stop and
re-read D7, D8, D13, D17 and D1 before writing it.
