# v196 — Plan size caps: a byte budget per task, a task cap per plan

**Version:** ui 1.36.1 · bot 2.15.4
**Bump:** none — `scripts/dev/plan_lint.py`, `.claude/agents/plan-writer.md`, docs; nothing the bot or admin serves changes.
**Edge:** none (integrity) — cheaper plan writing and cheaper plan reads; no signal, gate, stop, size or badge changes.
**Screen:** exempt (integrity)
**Panel:** staff-engineer, senior-engineer

**Status:** direction chosen by the partner, 2026-10-27 ("Size caps"), over three alternatives (tests in full with code as contract; boilerplate dedupe only; measure first).

## Why

v193 tried to cut plan cost by adding process: `plan_slice.py`, `plan_doc.py`,
`plan_lint --stats/--fix-parts/--ledger`, a briefer top-up and gaps flow. Each
added tool calls and context re-reads. Plans kept growing anyway, and the
partner reverted all of it on 2026-10-25 (`051b86c8`, `73cc820b`, `f31834de`).

The revert did not bring cost back down. v195's parts were all written after
it, and v195 is the largest plan yet. Bytes per task, measured from each
`### Task` heading to the next `### Task` or `# Phase`:

| Plan | Tasks | Median KB/task | p90 KB/task | Max | Tasks > 14 KB | Plan size |
|---|---|---|---|---|---|---|
| v186 | 12 | 11.9 | 17.9 | 20.4 | 5 | 179 KB |
| v187 | 13 | 11.1 | 14.9 | 21.2 | 3 | 193 KB |
| v190 | 25 | 10.6 | 20.9 | 32.2 | 7 | 351 KB |
| v192 | 26 | 17.9 | 26.7 | 34.8 | 17 | 552 KB |
| v194 | 28 | 12.8 | 18.4 | 23.9 | 11 | 407 KB |
| v195 | 37 | 27.2 | 38.4 | 45.7 | 34 | 1146 KB |

About half of every plan is fenced code (v190 53 %, v192 62 %, v195 53 %).
Opus writes that code once in the plan, and the Sonnet implementer types it
again in the worktree.

Two things drive the cost, and neither is the tooling v193 added:

1. **Tasks got fat.** The "Why splitting, and not writing less" table in
   `document-conventions.md` measured 2.7–5.7 KB per task and concluded that
   trimming tasks buys nothing. That premise no longer holds: tasks are now
   10–27 KB at the median, and a task that rewrites a whole component pastes the
   whole component.
2. **Plans got long.** Writer output, part-writer re-reads and the controller's
   bookkeeping all scale with the task count. The 1500-line file cap only moves
   tasks into more files (v195 has 22 parts); it never limits the plan.

The lesson from v193: **a limit that a script checks in one pass is cheaper than
a process that tries to steer the writer.** This spec adds two such limits and no
new tools, flags or agent steps.

## Scope

### A. Byte budget per task (plan_lint)

- `plan_lint.py` measures each task's bytes (UTF-8) from its `### Task` line to
  the next `### Task`, `# Phase` or end of file.
- **Hard cap 20 KB per task** (about the p90 of v186–v194). Over the cap is a
  lint failure: `<file>: Task <id> is <N> KB (cap 20 KB) -- split into two tasks, never compress`.
- **Aim: 14 KB or less.** This lives in the writer's instructions only. Lint
  does not report it, because a warning nobody acts on is just more tokens.
- **The fix for an over-cap task is a split, never compression:** the task becomes
  two tasks (two ledger rows, e.g. `V197-4` and `V197-4b`). Each keeps real test
  code, real implementation code and exact paths. A task is never thinned to fit.
- Applies to plans numbered **above v196** (the same gate as `needs_model` for
  v145). Older plans are history and are never re-linted into failure.

### B. Task cap per plan (plan_lint + plan-writer index mode)

- **At most 20 tasks per plan** (ledger rows, `b`-suffixed split rows included).
  v190, v192 and v194 (25–28 tasks) would each have been two plans, and v195
  (37 tasks) two or three.
- **Checked when the index is written, before any part exists:** `plan-writer`
  `mode=index` counts its ledger. Over 20 rows, it writes nothing further and returns
  `SCOPE: <N> tasks > 20 -- split the spec`. The controller then splits the
  spec into two numbered specs (the "A spec over budget usually is not one spec"
  rule in `document-conventions.md`) and asks the partner where to cut via `AskUserQuestion`.
  Catching it at the index costs one small file. Catching it after the parts
  are written costs the whole plan.
- `plan_lint.py` also fails a plan above v196 whose ledger has more than 20 ids:
  `ledger: <N> tasks (cap 20) -- split the spec`. It is a backstop, since the index
  check should already have stopped it.
- A task split under A that pushes the ledger past 20 means the plan is
  over-scoped too. The same `SCOPE` rule applies, and the cap is never raised.

### C. Docs and mirrors

- `docs/claude/document-conventions.md` § "How long a document may be": add a
  per-task row (20 KB hard, 14 KB aim) and a per-plan row (20 tasks) to the
  budget table. Replace the "Why splitting, and not writing less" table and
  conclusion with this spec's measurement: the premise "cost per task is
  near-constant at 2.7–5.7 KB" is false from at least v186 on. Splitting tasks is
  the lever, and compression stays forbidden.
- `.claude/agents/plan-writer.md`: line 25 keeps "real test code, real
  implementation code"; replace "Full code stays — speed comes from the phases
  below, not from thinner tasks" with the two caps and the split rule. In layout
  step 2, replace "recent tasks run 150–300" lines with "a task is ≤ 20 KB, aim 14 KB".
  Add the `SCOPE` return to `mode=index`.
- `CLAUDE.md` § Naming specs and plans: extend the existing "No plan file over
  1500 lines" sentence in place (the file is at 199 of 200 lines, so no new line
  is added) to "no file over 1500 lines, no task over 20 KB, no plan over 20 tasks".
- Codex mirror in the same commit: `AGENTS.md` (the condensed plan-writing
  paragraph near line 486) and `python scripts/dev/sync_codex.py` for the
  agent file. `tests/hooks/test_codex_mirror.py` must stay green.

## Non-goals

- **No new scripts, flags, agent phases, briefer changes or slice/stat tooling.**
  That is what v193 added and the partner reverted (memory
  `plan-pipeline-token-fixes-2026-10-25`).
- **No change to what a task contains.** Full test and implementation code
  stays. "Tests in full, implementation as contract" was offered and not chosen.
- **No boilerplate dedupe pass** (repeated `WT=` lines, per-part headers). It
  is small (about 5–10 %) and was not chosen; a later spec may take it.
- **No retroactive change** to v195 or any plan at or below v196.
- **No spec-size change.** The spec budget (~350 lines / 20 KB) already exists and holds.

## Acceptance

- `tests/dev/test_plan_lint.py` gains cases for each of these:
  - a 21 KB task fails;
  - a 19 KB task passes;
  - a task's size ends at `# Phase`;
  - 21 ledger rows fail;
  - 20 rows pass;
  - a v196 plan is not checked for either cap;
  - the multi-byte UTF-8 count is in bytes, not characters.
- `plan_lint.py` on every existing plan at or below v196 gives the same verdict as before (no new failures).
- `plan_lint.py` stays a single pass: the per-task size comes from the same line
  loop in `scan_file`, with no second read and no new module. Every function stays
  under complexity 15.
- The Codex mirror test is green.

## Expected effect

On v195's numbers, the caps would have produced two or three plans of at most 20
tasks each, with every task at or under 20 KB. That is roughly 400 KB per plan or
less (20 × 20 KB), against 1146 KB in one plan. The real saving shows up as
fewer bytes per plan written and read. It is not measured here; the next two
plans' sizes are the check, recorded in their close-out.
