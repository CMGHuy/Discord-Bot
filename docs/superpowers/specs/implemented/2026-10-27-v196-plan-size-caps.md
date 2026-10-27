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

- `plan_lint.py` measures each task from its `### Task` line up to the next
  `### Task`, the next `# ` or `## ` heading (so `# Phase`, `## Handoff` and a
  closing `## Self-review` never count against the last task), or the end of
  **that file**. The count resets per file, so the last task of part N never
  runs into part N+1.
- **Counting rule:** `read_text().splitlines()` drops line terminators, so each
  line costs `len(line.encode("utf-8")) + 1` bytes.
- **Hard cap `MAX_TASK_BYTES = 20_000`** (decimal KB; about the p90 of v186–v194).
  A task over the cap fails lint with
  `<file>: Task <id> is <N> KB (cap 20 KB) -- split into two tasks, never compress`,
  where `N` is bytes / 1000 to one decimal.
- **Aim: 14 KB or less.** This lives in the writer's instructions only. Lint
  does not report it, because a warning nobody acts on is just more tokens.
- **The fix for an over-cap task is a split, never compression:** the task becomes
  two tasks (two ledger rows, e.g. `V197-4` and `V197-4b`). Each keeps real test
  code, real implementation code and exact paths. A task is never thinned to fit.
- **Who adds the split row:** the part writer that finds its task heading
  past the cap writes it as two tasks, `<id>` and `<id>b`, appended in order. It
  returns them as `SPLIT: <id> -> <id>b` in its report and never edits the index.
  Before running lint on the parts, the controller adds the `b` row to the
  index ledger, directly below `<id>`. This is the same seam as today's parts
  table: part writers own their file, the controller owns the index.
- **No per-append lint.** The cap is enforced by the writer's own sizing (aim
  14 KB) and by the `plan_lint` run that already happens after each part. Running
  lint after every task append would be exactly the extra tool calls v193 added.
- Applies to plans numbered **above v196**: `CAPS_FROM = 196`, next to the
  existing `> 145` gate for `needs_model`, and read the same way. A file name
  with no version (`plan_number` returns 0) is unchecked. Older plans are
  history and are never re-linted into failure.
- **Shape in `plan_lint.py`:** `scan_file` already carries about six branch
  points, so the byte tracking does not go inline. A per-file state dict holds
  the open task id and its byte total. Two helpers use it: `track_task_bytes(name, line, state)`,
  called once per line in the existing loop, adds the line and closes the open
  task on a boundary; `close_task(name, state)`, called after the loop, handles
  end of file. Every function stays under complexity 15.

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
- **The return contract:** `SCOPE` joins `DONE | PARTS | BLOCKED` in
  `plan-writer.md`'s Return shape (line ~107). The controller's plan-writing steps in
  `docs/claude/skills-tools.md` § Plan writing gain one line: on `SCOPE`, stop,
  ask the partner where to cut, and split the spec.
- **Numbering after a split:** the committed spec keeps its `vN` and is revised
  in place to hold the first half, with a `**Split:** second half in vM` line under
  `Status:`. The second half is a new spec, numbered through `/new-doc` (`vM`),
  with its own `Panel:` run. The first half's panel trail stands, and it is not
  re-panelled unless its scope changed beyond the cut. The index already
  written for vN is deleted (it was never committed) and rewritten from the
  revised spec.
- `plan_lint.py` also fails a plan above v196 that has more than 20 tasks, using
  `ledger: <N> tasks (cap 20) -- split the spec`. It counts the ledger ids,
  or the `### Task` headings when the plan has no ledger (a single-file plan),
  so the backstop is never silent. It is a backstop because the index check should
  already have stopped the plan.
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
  If the reworded sentence would wrap the paragraph onto an extra line, move
  "split into `_N` parts, never compress a task" out to `document-conventions.md`
  (it is already there) and keep the three caps plus the pointer. `wc -l CLAUDE.md`
  must read 200 or fewer.
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

- `tests/dev/test_plan_lint.py` gains cases for each of these (the fixtures use
  `-v900-`, so they fall under both caps):
  - a task of exactly 20 000 bytes passes, and 20 001 fails;
  - the failure message prints `N` to one decimal;
  - the size ends at `# Phase`, and at `## Handoff`;
  - the last task of part 1 does not absorb part 2 (per-file reset);
  - a task under the cap in characters but over it in UTF-8 bytes fails;
  - 21 ledger rows fail and 20 pass;
  - 21 `### Task` headings with no ledger fail;
  - `-v196-` is unchecked, `-v197-` is checked, and a file name with no version is unchecked.
- A regression test runs `lint()` on the committed v195 plan (37 tasks, tasks up
  to 45 KB) and asserts that neither cap's message appears. This pins the
  version gate on real data. "No new failures on existing plans" is this test,
  not a manual check.
- `plan_lint.py` stays a single pass: the per-task size comes from the existing
  line loop in `scan_file` through the two helpers above, with no second read
  and no new module. Every function stays under complexity 15
  (`complexity_gate.py`).
- The Codex mirror test is green.

## Expected effect

On v195's numbers, the caps would have produced two or three plans of at most 20
tasks each, with every task at or under 20 KB. That is roughly 400 KB per plan or
less (20 × 20 KB), against 1146 KB in one plan. The real saving shows up as
fewer bytes per plan written and read. It is not measured here; the next two
plans' sizes are the check, recorded in their close-out.

## Panel review

2026-10-27, staff-engineer (opus) and senior-engineer (sonnet), run serially.

- senior-engineer [BLOCKING]: inline byte tracking would push `scan_file` toward complexity 15 -- applied: `track_task_bytes` / `close_task` helpers and a per-file state dict named in § A.
- senior-engineer [BLOCKING]: `splitlines()` drops terminators, so the byte rule was unpinned -- applied: `len(line.encode("utf-8")) + 1` per line, with a bytes-over/characters-under test.
- senior-engineer: "20 KB" was ambiguous and the rounding was unstated -- applied: `MAX_TASK_BYTES = 20_000`, `N` to one decimal, a 20 000 / 20 001 boundary test.
- senior-engineer: trailing `##` sections counted against the last task -- applied: a span also ends at the next `# ` or `## ` heading.
- senior-engineer: the ledger cap was silent when a plan has no ledger -- applied: it counts the `### Task` headings instead.
- senior-engineer: the gate constant was unnamed and its edges untested -- applied: `CAPS_FROM = 196`, tests for v196, v197 and a file name with no version.
- senior-engineer: "same verdict on existing plans" was not testable -- applied: a regression test lints the committed v195 plan.
- staff-engineer: no owner for the split ledger row across the index/part seam -- applied: the part writer returns `SPLIT:` and the controller adds the row.
- staff-engineer: `SCOPE` was missing from the return enum and the controller steps -- applied: added to Return shape and to skills-tools.md § Plan writing.
- staff-engineer: numbering and panel after a `SCOPE` split were unstated -- applied: vN keeps the first half; the second half gets a new number and its own panel.
- staff-engineer: a single-file plan is only caught at the final lint -- rejected: linting after every task append is the per-write overhead v193 added; the writer's 14 KB aim and the existing post-part lint stay the checkpoints.
- staff-engineer: CLAUDE.md may pass 200 lines -- applied: the fallback is named and `wc -l` checked.
- staff-engineer: no per-file reset test -- applied: an acceptance case.

## Close-out panel (diff 8f091f62^1...8f091f62)

staff-engineer and senior-engineer: no BLOCKING.

- staff: skill said `make up` (starts bot and tunnel) and called `swing-db-test` a stray -- applied (38201c46: `docker start swing-db`, `swing-db-test` named as the one exception).
- staff: skill rewrite has no spec of its own -- accepted: done at the partner's request mid-run (2026-10-27), recorded here.
- staff: AGENTS.md 10 bytes under the 32768 cap, CLAUDE.md 1 line under 200 -- carried: the next setup change must move content to docs/claude first.
- senior: `update_fence` branches untested (`~~~`, short closer, trailing text, mixed chars) and an unclosed fence swallows later headings with no hint in the message -- carried, no test yet.
- senior: byte count assumes LF endings (CRLF plans undercount ~1 byte per line) -- carried, error is small and in the permissive direction.
- senior: the v195 regression test depends on that committed plan and shells out to git via `tracked_paths()` -- carried; the synthetic `test_caps_apply_only_above_v196` already pins the gate.
- senior: uncited p90 comment on `MAX_TASK_BYTES`, untyped state dict -- carried, style only.
