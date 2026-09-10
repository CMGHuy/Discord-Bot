# v78 — Exit-quality analytics Implementation Plan (index)

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Bump:** bot patch · ui minor — resolved at close-out from `VERSION.json`.
**Edge:** none (integrity)

**Goal:** Aggregate and render the exit-quality data the bot already writes to
every closed trade — MFE, MAE and exit efficiency — and stop every rate chart
on the page from quoting a percentage it does not have the sample to support.

**Architecture:** One new pure aggregation module (`core/analytics/exit_quality.py`)
that takes journal entries as a parameter and never loads them, served by one
new route (`GET /analytics/exit-quality`). Two new DIY SVG primitives
(`sb-donut`, `sb-scatter`) and two new child components under
`workspaces/analytics/sections/`, so the 1700-line `analytics.ts` is touched
only to mount them. A single shared `MIN_CELL_N` floor, seeded from the floor
the repo already uses, applied to every existing rate chart.

**Tech Stack:** Python 3.11, Flask, pytest · Angular 21.2.21 (signal inputs,
`OnPush`), hand-rolled SVG, `ng test`. **No new dependencies, either side.**

**Spec:** `docs/superpowers/specs/2026-09-10-v78-exit-quality-analytics-design.md`

---

## Global Constraints

Every task's requirements implicitly include this section.

- **No new dependency, either side.** No charting library — v53's non-goal
  stands. Both primitives are hand-rolled SVG in `frontend/src/app/ui/`,
  consistent with `histogram.ts` and `line-chart.ts`.
- **`exit_quality.py` never loads.** Every function takes `entries: list[dict]`
  as a parameter, matching `core/edge/stops.py`, whose
  `mae_informed_stop_mult` and `mfe_informed_tp2_r` both do. Loading is the
  caller's job, via `JournalStore().entries()` (`journal.py:51`).
- **`None` is never rendered as `0`.** `exit_reason_split` returns
  `avg_r`/`win_rate` as `None` for an empty bucket on purpose — its docstring
  says *"'no trades exited this way' and 'they all lost' must not look the
  same."* `hold_by_outcome` returns `ratio`/`severity` as `None` unless both
  sides independently clear `MIN_TRADES_FOR_RATIO = 5` (`metrics.py:328`).
  Every renderer draws absence, never a zero.
- **Aggregate MAE and efficiency are winners-only.** Doctrine, quoted from
  `core/edge/stops.py:19-29`: *"a LOSER's MAE is by definition at least the
  stop it hit, so feeding losers in would ratchet stops wider on exactly the
  trades that should have been cut."* The **scatter is the one exception** —
  plotting losers beside winners is its whole diagnostic, and it sets no stop.
- **`MIN_CELL_N = 20`, defined once**, in `aggregate.py`, seeded from the
  existing `DRIFT_LIVE_N_FLOOR = 20` (`calibration.py:79`). Served to the SPA
  as `min_cell_n`; **the SPA never hard-codes 20.**
- **Below the floor, withhold the claim, not the row.** A sub-floor cell keeps
  a muted bar and shows `n=7` in place of its rate. v63's contract requires
  every category rendered even at `n=0`; that still holds.
- **Coverage is stated wherever a field is partially populated.**
  `exit_efficiency` is null on ~12% of journal rows and `mae_r` on ~5.6%. Any
  chart fed by one carries a coverage caption.
- **`sb-async`'s `emptyReason` and `emptyTitle` are required inputs** and the
  distinction is load-bearing (`known-traps.md`: this repo has empty tables
  that are measured answers, not stubs). Use `'no-data-yet'` when the book has
  no closed trades, `'measured-zero'` when trades exist but the slice is
  genuinely empty.
- **New routes carry the strict unknown-parameter guard** the other analytics
  routes use — an unexpected query param is a `400`, not a silent ignore.
- **Per-task verification is narrow.** Python:
  `python scripts/dev/testrun.py file tests/<the one file>.py` (~7s).
  Frontend: `npm test -- --include <the one spec file>`. **Never
  `... full`, never a bare `npm test`, per task** — that is Task E1 only.
- **Nothing is re-measured.** No backtest, no grid, no registry regeneration,
  no default flipped, no pre-registration opened or re-run.

---

## Parts

| Part | File | Tasks | Content |
|---|---|---|---|
| 1 | `_1-backend.md` | A1–A4 | `MIN_CELL_N` + `StatRow.total_r`, `exit_quality.py`, the route |
| 2 | `_2-charts.md` | B1–B2, C1–C5 | `sb-donut`, `sb-scatter`, the two new sections and their six + one charts |
| 3 | `_3-floor-and-fixes.md` | D1–D4, E1 | floor rollout across existing charts, two bug fixes, full-suite gate |

**Read one task, not one part** — `/task-brief C3`, or
`grep -n "^### Task C3" -A 120 docs/superpowers/plans/2026-09-10-v78-*.md`.
A task id appears in exactly one file, so
`grep -rn "^### Task C3" docs/superpowers/plans/` finds it without knowing
which part it landed in.

## Parallelisation

The rule this repo enforces: two tasks may share a group only if they touch
**disjoint files** *and* neither consumes a symbol the other introduces.
Concurrent sessions share this working tree, so a wrong grouping silently
overwrites work rather than conflicting.

- **Sequential: A1 before everything.** It introduces `MIN_CELL_N` and
  `StatRow.total_r`, which the route, both sections and the whole floor
  rollout consume. Contract dependency, not preference.
- **Sequential: A2 → A3.** Same file (`exit_quality.py`); A3's `coverage`
  test fixtures reuse A2's.
- **Sequential: A4 after A3** — the route assembles every function in the
  module.
- **Group B (parallel): B1 and B2** — `ui/donut.ts` and `ui/scatter.ts`, one
  new file each, neither consumes the other.
- **Sequential: C1 after A4 and Group B.** It adds the API method, the store
  slice and the section shell that C2–C4 fill.
- **Sequential: C2 → C3 → C4.** All three edit the same new file
  (`sections/exit-quality.ts`). One writer at a time, whatever their logical
  independence.
- **C5 runs parallel with C2–C4** — a different new file
  (`sections/strategy-contribution.ts`); it consumes only `StatRow.total_r`
  from A1 and `analyticsStrategies()`, which already exists.
- **Sequential, alone: D1 → D2.** Both edit `analytics.store.ts` and
  `analytics.ts` — the files every Phase C task deliberately avoids. Do not
  run these beside anything.
- **Group D (parallel): D3 and D4** — disjoint files (`analytics.py` plus the
  SPA calibration reader, versus the group-by picker).
- **Last, alone: E1.** The single full-suite gate for both suites.

## Exit criteria

1. The Performance tab shows exit-reason mix, exit efficiency, MAE, MFE-vs-MAE,
   disposition and outcome mix; the Strategies tab shows total R per strategy.
2. No chart anywhere on the page renders a rate for a cell below `MIN_CELL_N` —
   each shows `n` instead — and the SPA nowhere hard-codes the number.
3. Every chart fed by a partially-populated field states its coverage.
4. An empty bucket renders as absent, never as zero, asserted by test.
5. The calibration level table shows the rows `level_calibration` produces; the
   group-by picker offers no dimension `stats_by` cannot resolve.
6. `analytics.ts` grew by mount points only — no chart logic was added to it.
7. `python scripts/dev/testrun.py full` and `cd frontend && npm test` are both
   green (`0 failed`, `0 xfailed`) in one final run, Task E1.
