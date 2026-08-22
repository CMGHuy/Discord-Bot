# v40 — Repo cleanup audit (design)

Bump: none (Phase 1 is read-only; no observable behavior change)

## Why

The user asked to brainstorm fixing all bugs, simplifying code, removing dead
code/spaghetti, and cleaning up the whole repo, contingent on plan v36
landing. The codebase is 72K lines across 134 files under `swingbot/core`
alone, plus `admin/`, `frontend/`, `scripts/`, `tests/` — too large for a
single implementation plan, and this repo has a documented history of things
that *look* dead but are deliberate (`docs/claude/known-traps.md`: measured
empty tables like `REGIME_ALLOW`, load-bearing "unused" re-exports — 4 of 29
flagged imports in a 2026-08-14 pass, edge-engine functions shipped ahead of
their wiring task per `docs/claude/architecture.md`). A blind sweep risks
re-opening a closed pre-registration or deleting load-bearing code.

## Approach: two phases, this spec covers only Phase 1

**Phase 1 — Audit (this spec).** Six parallel read-only agents, one per
subsystem grouping, each producing a findings report tiered
`confirmed` / `candidate` / `suspected`, consolidated into one audit
document. No code changes.

**Phase 2 — Cleanup plan(s) (separate, later cycle).** Once the audit doc is
committed and plan v36 has merged to `main`, a follow-on
brainstorming/`writing-plans` cycle turns `confirmed` bugs and
guardrail-cleared `candidate` items into one or more real implementation
plans, using this repo's normal plan conventions (`Bump:` header,
`## Parallelisation`, length budget). Not designed here — depends on what
Phase 1 finds. Likely split by risk profile (low-risk confirmed-bugs-and-
verified-dead-code plan vs. higher-judgment simplification/spaghetti plan)
but that split is a Phase 2 decision, not committed now.

## Phase 1 mechanics

**Timing:** starts as soon as this spec is committed, running concurrently
with plan v36's remaining tasks (user's explicit choice — accepting that
findings touching v36's own active area may go stale and need a re-check).

**Dispatch:** six agents, dispatched as forks (they inherit this session's
already-loaded repo context and share its prompt cache, rather than paying
fresh-context cost per agent). Each is read-only: grep/read/run-tests only,
explicitly forbidden from editing any file. Each writes its findings to a
fixed scratch path so the controlling session consolidates without reading
raw tool transcripts (per this repo's token-discipline rule).

**Subsystem breakdown:**

| # | Area | Paths |
|---|------|-------|
| 1 | Market data & infra | `core/marketdata/`, `core/infra/` |
| 2 | Market logic & edge math | `core/market/`, `core/edge/` |
| 3 | Planning, backtesting, tracking | `core/planning/`, `core/backtesting/`, `core/tracking/` |
| 4 | Scan pipeline, analytics, charts, Discord layer | `core/scanning/`, `core/analytics/`, `core/charts/`, `commands/` |
| 5 | Admin API & frontend | `admin/`, `frontend/` |
| 6 | Scripts & test suite health | `scripts/`, `tests/` |

Agent 3 overlaps plan v36's active area (`core/planning`/level-touch-strength
work). Its brief must note v36's current task state and mark anything inside
v36's active task range as `suspected` only — not ground truth mid-edit —
deferring confirmation to a re-check after v36 merges.

**What each agent looks for:** unused imports/functions, duplicated logic,
overly deep/tangled call chains, inconsistent error handling, TODO/FIXME,
dead branches, obviously-avoidable complexity.

**Mandatory guardrail before flagging anything as dead/removable:**
1. Grep both `from <module> import <name>` and `<module>.<name>` across
   `swingbot/`, `tests/`, `scripts/` (the re-export check from
   `known-traps.md`).
2. Grep `docs/superpowers/results/` for the symbol/table/flag name (the
   measured-answer-table check).
3. Check whether it's edge-engine code shipped ahead of its wiring task
   (`docs/claude/architecture.md`'s edge-engine note).

Anything that doesn't clear all three checks is dropped from the findings
entirely, not merely downgraded to `suspected`.

**Bug claims require a repro** — a failing test, a one-off script run, or a
precise input→wrong-output trace. No repro means the item is `suspected`,
not `confirmed`. Agents are allowed to run targeted pytest files or small
repro scripts to establish this (read-only w.r.t. source, execution is fine).

## Deliverable

`docs/superpowers/results/2026-08-21-repo-cleanup-audit.md` — a results doc
(not a spec/plan, so exempt from `Bump:`/`Parallelisation`/length-budget
rules), one section per subsystem, each with three subsections (Confirmed
bugs / Candidate dead-code & simplification / Suspected). Each item:
`file:line — one-line claim — evidence (repro command or grep result) — est.
size (trivial/small/medium)`. If a subsystem section runs long, split into
`_N` files under the same date+topic rather than compressing. No fabricated
summary numbers or padding — a clean area gets a one-line "nothing found."

## Non-goals for this spec

- No code changes of any kind (Phase 1 is entirely read-only).
- No `VERSION.json` bump (no observable behavior change).
- No Phase 2 task list — that's a separate design cycle after the audit
  exists and v36 has merged.
- No re-litigating anything already closed in
  `docs/claude/backtest-methodology.md`'s pre-registration table.
