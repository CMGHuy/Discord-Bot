# v193 — Plan-writer pipeline: write as you go, split right first time, shorter tasks, stable contracts

**Bump:** none — `.claude/agents/plan-writer.md`, `plan-briefer.md`, `scripts/dev/plan_lint.py`, docs; nothing the bot or admin serves changes.
**Edge:** none (integrity) — faster, cheaper, visibly progressing plan writing; no signal, gate, stop, size or badge changes.
**Screen:** exempt (integrity)
**Panel:** staff-engineer, senior-engineer

**Status:** approved by the partner, 2026-10-25.

## Why

Evidence from v189, v191, v192 (2026-10-23..25):

- **Parts spill past 1500 lines after they are written.** v189 (3b, 4b, 7b), v191 (3b, 4b), v192 (1b, 2b, 3b) were all re-split post hoc, each costing an index edit, a ledger fix-up and an extra commit (`16086468`, `596c669b`, `0f3abca6`).
- **The size estimate is about 2× low.** `plan-writer.md` assumes 150–300 lines per task; v192's tasks measure 153–709, most above 300.
- **Plans are huge.** v192 ≈ 9,000 lines / 26 tasks, v189 ≈ 13,000. Opus wall time scales with what one context writes (skills-tools.md § Plan writing).
- **Contracts change after parts exist** (v192: strategy_pass replaces scan_run in V192-13, fixed in the index after part 2).
- **Files fill in task-sized jumps.** One append per task means a 700-line task is invisible on disk for minutes.

## Scope

All four workstreams, one spec:

- **A. Split accuracy** — measured size estimates, writers spill into `_Nb` themselves, lint regenerates the parts table.
- **B. Shorter tasks** — lift repeated boilerplate, cite brief line ranges, task-size ceiling (split, never compress).
- **C. Contract stability** — verify the ledger before parts are dispatched; part-to-part dependencies.
- **D. Write-as-you-go granularity** — see below.

## Design principle: fewest tokens (partner, 2026-10-25)

Every choice below is ranked by total tokens spent (writer output + context re-reads + every later reader of the plan) first, wall time second. Anything a script can check or generate is never done by a model.

## D. Write-as-you-go granularity (agreed 2026-10-25)

**Adaptive append unit:**

1. A task estimated **≤ ~200 lines** is appended in one call, as today.
2. A longer task is appended **per step**: heading + `**Model:**` + `**Files:**` first, then each step (failing test, run, implementation, run, commit) as its own append.
3. `mode=index`: sections are appended as each is decided; the ledger is appended in one call once complete (it is short, and rows depend on each other).

## B. Shorter tasks — dedupe + cite (agreed 2026-10-25)

- **Stays in full:** every new function, class and test body; exact commands where they differ from the standard.
- **Stated once, in the index's `## Global Constraints` → `### Standard task close`:** worktree check, narrow run (`testrun.py file <test>`), complexity gate, commit-message shape. A task ends with `Close: standard (test: tests/…)` and spells out only deviations.
- **Existing code is cited, not pasted:** `Modify: swingbot/x.py:120-180 (fn_name)` plus the exact old → new snippet of the edited lines only. Cite the **repo file**, never the brief (the brief is gitignored and absent from worktrees).
- **Task ceiling ~400 lines.** A larger task is split into two tasks (new ledger rows) — splitting, never compressing.
- `plan_lint.py` gains: missing `Close:` line, task over the ceiling, `Modify:` range beyond the file's length.

Expected: 30–45% fewer plan lines → fewer writer output tokens and fewer tokens in every `/task-brief` read later.

## A. Split right the first time (agreed 2026-10-25)

- `plan_lint.py --stats` reports median and p90 lines per task over the last ~5 plans in `plans/implemented/`. `mode=index` sizes parts at p90 (replacing the "150–300" constant in `plan-writer.md`).
- **Self-spill:** a part writer whose next task would take its file past ~1400 lines opens `_<N>b-<slug>.md` (header as any part) and continues there; it lists both files in `FILES:` and never edits the index.
- `plan_lint.py --fix-parts <index>` regenerates the index's parts table (file → task ids) from the files on disk; the controller runs it before committing parts. No hand-edited parts table, no extra index commit per spill.

## C. Stable contracts, slice-only context (agreed 2026-10-25)

- **Brief keyed by file:** `plan-briefer` writes signatures, excerpts and test patterns under one `## <repo path>` heading per file (plus a trailing `## Traps`).
- **Ledger gains `Spec §`:** the spec section(s) each task implements.
- **`scripts/dev/plan_slice.py <index> <part>`** prints, for that part's ledger rows: the index header + Global Constraints + full ledger, the cited spec sections, and the brief sections for the files those rows touch. The part writer reads this one slice instead of the whole spec, brief and index; it may still `sed -n` a range the slice lacks.
- **`plan_lint.py --ledger <index>`** runs after `mode=index`, before parts are dispatched: every consumed symbol exists (`git grep`) or is created by an earlier ledger row; no row consumes a symbol from a later row; every `Spec §` resolves to a heading. Failures go back to the index writer, not to the parts.

## Model tier for prose parts

A part whose ledger rows are all docs/runs/release tasks (every row's `Model:` is haiku/sonnet and no row creates code) is dispatched with `model: sonnet`.

## Testing

Unit tests for `plan_lint.py --stats/--fix-parts/--ledger`, the new lint checks (`Close:`, ceiling, `Modify:` range) and `plan_slice.py`, under `tests/dev/` (existing suite), with fixture plans: empty ledger, missing spec section, missing brief section, spill file `_Nb`, symbol consumed before creation. Codex mirror (`sync_codex.py`, `AGENTS.md`) ships in the same commit as the agent changes.

## Out of scope

Line-level streaming; contract-level (code-free) tasks; changing the 2-writer / 2-plan caps; rewriting existing plans.

## D rationale

Why not per step always: each append re-reads the writer's whole context (60–100k tokens); per-step on every task adds ~8–10M cached-input tokens to a 26-task plan. Adaptive keeps the long, previously invisible tasks moving at a fraction of that. Slice-only context (C/A below) makes each extra append cheaper still.

Resume rule follows the unit: a task cut off mid-step is detected by its missing closing commit step; the writer deletes only the trailing incomplete task and re-appends it (unchanged from today).
