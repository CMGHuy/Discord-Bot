# v85 — Dashboard, shell and workspace redesign Implementation Plan (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Bump:** ui minor per wave (three) · bot patch in waves 2 and 3 — resolved at
each wave's close-out from `VERSION.json`.
**Edge:** none (integrity)

**Goal:** Rebuild the admin SPA — shared chrome, Dashboard, and all seven
remaining workspaces — against the supplied mockups, building the backend each
recomposed page needs rather than rendering a facade over data that does not
exist.

**Architecture:** The shell's top bar becomes a single row owning the wordmark,
the route's title/subtitle, a named-index tape with a Live dot and clock, and
the status cluster. Six shared primitives land next — a control bar, a stat
tile that carries its own sample size, a gauge, a correlation matrix, a
timeline and a freshness marker — and every workspace is then recomposed over
them, each with the endpoint it needs. Work ships in three waves, each ending
in its own full-suite run and release.

**Tech Stack:** Angular 21 (standalone, signals, OnPush), `@ngrx/signals`
stores, vitest + jsdom via `@angular/build:unit-test`, Flask API, pandas/numpy,
pytest.

**Spec:** `docs/superpowers/specs/2026-09-11-v85-dashboard-shell-redesign-design.md`

---

## Global Constraints

Every task's requirements implicitly include this section.

- **Every colour comes from `frontend/src/styles/tokens.css`.** No hex literal
  in a component — `ui/primitives.spec.ts` fails the build on one. The palette
  already matches the mockups (`--bg: #0c0f16`, `--surface: #131722`,
  `--pos: #17c98e`, `--neg: #ff5470`, `--accent: #5593ff`); this plan adds
  tokens, it does not retune existing ones.
- **Zero third party in the frontend.** No icon font, no icon package, no CDN,
  no charting library. New icons are hand-authored paths on the existing 16×16
  grid at 1.5 stroke width in `ui/icon.ts`; new charts are hand-authored SVG
  alongside `ui/sparkline.ts`, `ui/donut.ts`, `ui/line-chart.ts`.
- **Preferences persist through `PreferencesStore`, never `localStorage`.**
  A setting must follow the account, not the browser.
- **Components read signals; stores fetch.** No `subscribe()` and no refresh
  call in a workspace component. Each store's own effect owns both the first
  load and every refetch.
- **`null` is never `0`.** A metric that did not arrive renders as "no value",
  not as zero. This applies to the payoff ratio, every new risk metric, and
  every analytics figure exactly as it does to `profit_factor` today.
- **Every derived metric renders its N** (spec D23). Below the minimum sample
  it renders de-emphasised with how many more closed trades it needs. The
  minimum is the constant `MIN_SAMPLE_N = 30` until R11-04 makes it a setting.
- **Freshness is per panel, never global** (spec D30). The header's Live dot
  reports stream connectivity only; each panel carries its own "as of" from its
  own data's timestamp.
- **Every panel is independently async** through `sb-async`. One panel's failed
  fetch must never blank another's numbers, and a refetch failure keeps the
  previous figures on screen with a staleness marker.
- **State cues are never colour alone.** Every status signalled by colour
  carries a second cue: weight, a rail, or an icon.
- **Every page stays usable at 390px.** Dense instruments scroll inside their
  own `overflow-x` container; the page body never scrolls sideways. Nothing is
  hidden at narrow width.
- **Every manual state change appends to `data/manual_close_notify.json`**
  via `_queue_notify`. The bot is a separate process and that file is the only
  way it learns a human closed something.
- **No new top-level JSON file** (spec D26). New state rides in the existing
  `PreferencesStore` or the existing events path, so
  v67's JSON→Postgres migration inventory does not grow.
- **Plans cannot be deleted.** `delete_trade` refuses plan-backed rows by
  design; this plan does not add `PlanStore.delete()`.
- **How the bot trades does not change.** No scan, strategy, sizing or exit
  logic is touched anywhere in this plan. The one write into the bot process is
  R12-01's boot-time deploy marker, which is append-only and fail-degrading.
- **Per-task verification is narrow:**
  - Frontend, one spec: `cd frontend && npx ng test --include <path>` — ~55s,
    prints `Test Files 1 passed`. Verified on `src/app/ui/clock.spec.ts`.
  - Backend, one file: `python scripts/dev/testrun.py file tests/<file>.py` (~7s).
  - **Never `testrun.py full` per task.** That is R5-07, R8-07 and R12-08, and
    nothing else.
  - `scripts/dev/testrun.py` is pytest only — it does not run frontend specs.
- **Never hard-code a version number.** `Bump:` states the level; the numbers
  resolve at each wave's close-out from the `VERSION.json` on disk at that
  moment.
- **Never edit files under `.claude/worktrees/`** from a main-tree session.

---

## Waves

The plan ships three times. Each wave ends with its own full-suite run, its own
`VERSION.json` bump and its own close-out, so a regression is bisectable to a
handful of files rather than to forty.

| Wave | Parts | Ships |
|---|---|---|
| 1 | 1–5 | The shell, the shared primitives, and the Dashboard |
| 2 | 6–8 | Trades, Watchlist and Risk, with their endpoints |
| 3 | 9–12 | Analytics, Calendar, System, Versions, and the two stubs |

## Parts

Task ids are part-prefixed (`R1-01` … `R12-08`), so an id is unambiguous across
files and across the other live plans in this directory.

| Part | File | Content | Tasks |
|---|---|---|---|
| 1 | `_1-shell.md` | MCP fix, token and icon additions, route title/subtitle mechanism, merged top bar, named-index tape with Live dot and clock, zoom relocation, killswitch strip, brand mark and tagline, nav restyle, responsive rules | 14 |
| 2 | `_2-primitives.md` | the six shared primitives — control bar, stat tile with sample size, gauge, correlation matrix, timeline, freshness marker — and the consistency guard they are checked by | 7 |
| 3 | `_3-backend.md` | payoff ratio in `metrics.py` and on the dashboard payload; `TradeLog` bulk close and its endpoint; client bindings | 6 |
| 4 | `_4-dashboard.md` | Portfolio Value, Trading Performance, Recent Activity derivation and panel, Watchlist, Market Movers, page assembly, explanatory copy behind affordances, sheet-1 reconciliation | 9 |
| 5 | `_5-positions.md` | the tabbed positions table, per-tab column sets, preference survival, row actions, close-all, and wave 1's verification and release | 7 |
| 6 | `_6-trades.md` | `from`/`to` query parameters, the promoted chip lane, the date-range picker, the count footer | 5 |
| 7 | `_7-watchlist.md` | the batched quote/change/sparkline endpoint, the live scan verdict, view-only tags, the recomposed row | 6 |
| 8 | `_8-risk.md` | the institutional metric set, the correlation matrix endpoint, gauge and risk budget, page assembly, and wave 2's verification and release | 7 |
| 9 | `_9-analytics.md` | the equity-curve and drawdown series, strategy and horizon aggregates with the ExpR/total-R toggle, the recomposed Performance tab, the Breakdowns band | 6 |
| 10 | `_10-calendar.md` | day-detail contributors and detractors, the two-pane layout, the cell-metric selector, the month summary strip | 5 |
| 11 | `_11-system.md` | the settings category sub-nav, settings search, the unsaved-changes footer over the existing preview endpoint, the minimum-N setting | 5 |
| 12 | `_12-versions.md` | the boot-time deploy marker, release-window telemetry, provenance, the timeline page, the Research and Reports stubs, the `/ui` gallery, and wave 3's verification and release | 8 |

**Read one task, not one part** — `/task-brief R7-03`, or
`grep -n "^### Task R7-03" -A 120 docs/superpowers/plans/2026-09-11-v85-*_7-*.md`.

---

## Parallelisation

Two tasks may share a group only if they touch **disjoint files** *and*
neither consumes a symbol the other introduces. Concurrent sessions share this
working tree, so a wrong grouping silently overwrites work rather than
conflicting.

### Wave 1

- **Sequential, first: R1-01** (chrome-devtools MCP). No code depends on it,
  but every visual checkpoint after it does.
- **Sequential, second: R1-02 and R1-03** (tokens, icons). One file each, and
  almost every later task consumes what they add.
- **Sequential, third: R1-04 through R1-14** (the shell). The route
  title/subtitle mechanism from R1-04 is a contract every workspace consumes,
  and the rest all edit `shell.html`/`shell.css`/`shell.ts`, so they are a
  chain among themselves, not a group.
- **Group P (parallel), after R1-03: R2-01 … R2-06** — the six primitives, one
  new file each, no shared file. **R2-07** (the consistency guard) runs after
  them, alone, and is committed deliberately failing.
- **Group A (parallel), after R1-03:** the two backend strands — R3-01…R3-03
  (payoff ratio: `core/analytics/metrics.py`, `admin/api_v1/dashboard.py`) and
  R3-04…R3-06 (bulk close: `core/tracking/performance.py`,
  `admin/api_v1/trade_commands.py`). Disjoint files, no shared symbol. Within
  each strand the tasks are sequential. Group A and Group P may run at once.
- **Group B (parallel), after the shell, Group P and Group A:** R4-01, R4-02,
  R4-04, R4-05, R4-06 — the five new panel components, one new file each.
  R4-02 (Trading Performance) consumes the payoff-ratio field, which is why
  Group A precedes it. R4-03 (the activity derivation helper) precedes R4-04
  within the group's dependency order, so treat R4-03/R4-04 as one strand.
- **Sequential, after Group B: R4-07, R4-08, R4-09** — page assembly, the copy
  affordances and the sheet-1 reconciliation all edit `dashboard.ts`, which
  every Group B task would otherwise contend for.
- **Sequential: R5-01 … R5-06.** One chain: the table exists before its column
  sets, which exist before preference survival, which exists before the row
  menu and the bulk button. R5-06 also consumes R3-06's endpoint.
- **Sequential, final: R5-07** — wave 1 verification and release, alone.

### Wave 2

- **Group W2-BE (parallel), first:** R6-01 (trades `from`/`to` in
  `admin/api_v1/trades.py`), R7-01…R7-03 (the watchlist quote batch, the scan
  verdict, and tags — `admin/api_v1/watchlist.py` plus a new service module)
  and R8-01…R8-03 (risk metrics and correlation —
  `core/analytics/risk_metrics.py`, `admin/api_v1/risk.py`). Three separate API
  modules, no shared file. Within each strand the tasks are sequential.
- **Group W2-UI (parallel), after Group W2-BE:** R6-02…R6-05 (Trades),
  R7-04…R7-06 (Watchlist), R8-04…R8-06 (Risk) — one workspace directory each,
  no shared file between them. Within each workspace the tasks are sequential.
- **Sequential, final: R8-07** — wave 2 verification and release, alone.

### Wave 3

- **Group W3-BE (parallel), first:** R9-01…R9-02 (analytics equity curve and
  aggregates in `admin/api_v1/analytics.py`), R10-01 (calendar day detail in
  `admin/api_v1/calendar.py`), and R12-01…R12-03 (the deploy marker, the
  release-window derivation and provenance). Separate modules, no shared file.
- **Group W3-UI (parallel), after Group W3-BE:** R9-03…R9-06 (Analytics),
  R10-02…R10-05 (Calendar), R11-01…R11-05 (System), R12-04…R12-05 (Versions)
  and R12-06 (the two stubs) — one workspace directory each.
- **Sequential, after Group W3-UI: R12-07** — the `/ui` gallery additions,
  which edit one file every primitive contributes to.
- **Sequential, final: R12-08** — wave 3 verification and release, alone.

Groups P, A, B, W2-BE, W2-UI, W3-BE and W3-UI are the only places more than one
agent may work at once, and only within a group.

---

## Exit criteria

The plan is done when all of these hold:

1. Every workspace renders inside the new chrome with no leftover in-page
   heading, no double title, and no old-style panel. `workspace-consistency.spec.ts`
   (R2-07) is green and names no file.
2. The Dashboard matches sheet 1's structure: simplified Portfolio Value, the
   eight-metric Trading Performance panel, one tabbed positions table, and the
   Recent Activity / Market Movers / Watchlist bottom row.
3. No explanatory copy was lost — each piece named in D18 is reachable from
   the panel it explains.
4. `Close all open/partial` closes ACTIVE and PARTIAL positions, leaves
   PENDING alone, queues a notify record per position, and reports closed and
   failed counts separately.
5. Payoff ratio is on the dashboard payload and reads `null`, not `0`, when
   there are no losers.
6. Watchlist rows carry price, 1D/1W/1M change, a 30-day sparkline and the
   scanner's own verdict, each row showing the date of the bar it came from,
   served in one batch from cache with no per-row provider call.
7. Risk shows the six institutional metrics, each with its N and each
   de-emphasised below the minimum sample, plus the correlation matrix with the
   bot's clusters outlined on it and the cluster list still present.
8. Analytics' Performance tab is the sheet-2 composition with a working
   ExpR ⇄ total-R toggle, and every displaced panel is reachable in the
   Breakdowns band.
9. Versions shows both provenance and telemetry per release, with existing
   releases backfilled, and a missing marker degrades to "window unknown"
   rather than an error.
10. Research and Reports render an honest stub naming what is planned and
    linking to the surface that serves the need today.
11. Every workspace was screenshotted at 1440px and 390px and reviewed
    (R5-07, R8-07, R12-08).
12. `python scripts/dev/testrun.py full` reports `0 failed` and `0 xfailed` at
    each wave's close, and the frontend suite passes.

---

## A note on what this plan must not quietly become

The mockups show a search box in the top bar, a notification bell, an intraday
equity curve, a "+ New Trade" button, Market Movers' "Most Active" tab, a cash
balance, an allocation donut across asset classes, and Equities / Options /
Futures / FX tabs. None has backing data, an endpoint or a create path in this
bot. The spec refuses each by name.

**A task that finds itself building a facade over absent data has misread the
spec** — stop and re-read D7, D8, D13, D17, D31, D32 and the "What the mockups
are not" section before writing it.

The inverse failure is just as real. Where the spec says *build* the backend —
watchlist quotes and the scan verdict (D33, D34), the institutional risk set
(D37), release telemetry (D29) — a task that renders a placeholder instead has
also misread it. The rule is not "build less"; it is "render nothing you have
not measured".
