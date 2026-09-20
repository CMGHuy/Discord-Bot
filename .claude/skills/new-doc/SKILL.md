---
name: new-doc
description: Ritual for creating a new spec or plan -- recompute the repo-wide vN counter immediately before the commit, write the header block, and keep the document addressable and splittable. Invoked explicitly as /new-doc, never model-triggered.
disable-model-invocation: true
---

# New spec or plan

## Step 1 — Read the authority

`docs/claude/document-conventions.md`. This skill is the checklist; the
reasoning behind every step below lives there, not here.

## Step 2 — Compute the number immediately before the commit

Not once at the start of the session -- concurrent sessions share this
counter, and a number that was free five minutes ago may not be now. Run
this verbatim, from the repo root:

```bash
{ find docs/superpowers/specs docs/superpowers/plans -name '*.md' | grep -oE 'v[0-9]+'
  git log --oneline --all | grep -oE '\(v[0-9]+\)' | grep -oE '[0-9]+' | sed 's/^/v/'
} | sort -V | tail -1
```

`find` recurses into `implemented/`/`no-lift/` on its own -- closed docs
live one level down, and an `ls` that misses them returns a stale max. The
`git log` half exists because an informal `vN` in a commit subject with no
matching doc file has burned a number before.

## Step 3 — Write the header block

`Version:` on a spec only (never a plan) -- `ui X.Y.Z · bot A.B.C` copied
from `VERSION.json` as of this commit, never refreshed afterwards. `Bump:`
as a level, with no numbers in it. `Edge:` as one of `expectancy` /
`harvest` / `volume` / `none (integrity)`. A plan built from an
already-numbered spec reuses that spec's number and links back with a
`**Spec:**` line.

## Step 4 — Keep it addressable

`### Task <id>:` one line, no prose before the colon. `# Phase N —` with
one hash, however wrong that looks beside the `##` sections around it.
`guardrails.py` denies a two-hash phase heading and a non-conforming
filename -- treat both denies as correct, never work around them.

## Step 5 — Respect the length cap

Over the cap, split into `_N` parts sharing the parent's number (a part
that itself splits becomes `_2a`/`_2b`). Split, never compress -- a
compressed task is a task that gets re-derived wrong later.

## Step 6 — Add `## Parallelisation`

Name the groups and, more importantly, the reason on every sequential
edge. Be honest about a group of one -- a chain that says so saves the
next session from re-deriving the dependency graph.

## Step 7 — Commit on `main`

Specs and plans are written and committed on `main`, never a branch --
branch only to implement one. If the number collided while you were
writing, rename before your own commit, never after one has landed.

## The gate

The file name matches the convention, the counter was recomputed in the
same minute as the commit, and the plan ends with a single full-suite
verification task.
