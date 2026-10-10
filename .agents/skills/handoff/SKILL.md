---
name: handoff
description: "Write the in-progress plan's ## Handoff block -- every partner answer, BLOCKED resolution and spec deviation taken in this conversation, plus where to resume -- so another session or account carries on. Invoked explicitly as /handoff, never model-triggered."
---
<!-- GENERATED from .claude/skills/handoff/SKILL.md by scripts/dev/sync_codex.py -- edit the source, then re-run the script. Never edit this copy. -->

# Handoff

This runs in the main context on purpose: the decisions it records live in
this conversation, which a forked context cannot see. The convention is
`docs/claude/skills-tools.md` § Plan writing, the paragraph
"Handing a plan to another session or account"; read that paragraph first
(`grep -n "Handing a plan to another session" -A 16 docs/claude/skills-tools.md`),
never the whole file.

## Step 1 — Find the plan

The plan comes from the argument (`/handoff v154`, or a path). With no
argument, it is the plan this conversation has been writing or implementing.
If that is not exactly one plan, ask with `AskUserQuestion`, recommended
option first; never guess. A split plan takes the block in its `_0-index.md`,
a single-file plan in the plan itself. Never read a plan whole:
`grep -n "^## \|^### Task" <file>` gives you its sections and tasks.

## Step 2 — Collect what the next session needs

From this conversation only:

- every partner answer that settled something, with its date and the
  question it settled;
- every `BLOCKED:` resolution;
- every deviation from the spec, and why;
- where to resume: the first ledger id with no `### Task` on disk (plan
  writing), or the first task with no commit in the plan's worktree (plan
  implementing, from `git log --oneline`), with the worktree path if any.

Something not yet decided is not a handoff item. It is a question for the
partner now, through `AskUserQuestion`. If there is nothing to record, say so
and write nothing.

## Step 3 — Write the block

- If the file already has a `## Handoff` section, append numbered items after
  its last item, and never rewrite, renumber or delete an existing item: a
  later decision that changes an earlier one says which item it supersedes.
- If it has none, create `## Handoff` directly above `## Parallelisation`
  (directly above `## Task ledger` when there is no such section), opening
  with the line "Deviations from the spec and decisions taken while writing
  this plan. Each is final for every part."
- One item per decision: a bold lead clause stating it, then the reason and,
  for a partner answer, "*Partner confirmed <date>: ...*".
- The last item you add is the resume pointer: "**Resume at <id>.**" and the
  command that does it.

## Step 4 — Show it and commit it

Show the partner `git diff -- <file>`. Then, per the convention's "Commit as
you go", commit that file alone in the checkout it lives in: run
`git status --short` first (another session may share the tree), stage the
one path, and commit as `docs(vN): handoff -- <one clause>`.

## The gate

The block holds only decisions already taken in this conversation, each final
as written. Writing an item down never makes a new decision; an open question
goes to the partner, not into the plan.
