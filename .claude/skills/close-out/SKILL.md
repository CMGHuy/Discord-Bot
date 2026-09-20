---
name: close-out
description: The plan close-out ritual -- resolve the version bump from VERSION.json, regenerate version_history.json, move the plan document to implemented/ or no-lift/, and remove its worktree. Invoked explicitly as /close-out, never model-triggered.
disable-model-invocation: true
---

# Plan close-out

## Step 1 — Read the authority

`docs/claude/document-lifecycle.md` and `docs/claude/working-conventions.md`.
This skill is the checklist; the reasoning behind every step below lives
there, not here.

## Step 2 — Resolve the bump from disk

Read `VERSION.json` — never a plan header, never memory, never an earlier
task's note. Increment only the line named by the plan's `Bump:`; leave the
other line untouched. `Bump: none` means no release commit at all — skip
straight to Step 5.

## Step 3 — Stamp, commit, then regenerate

Set that line's `*_updated` stamp to now, in the existing format, and commit
`VERSION.json` alone: `release(<line>): <version> -- <summary>`. Then run
`python scripts/dev/build_version_matrix.py` and commit the regenerated
`swingbot/admin/version_history.json` as its own next commit:
`chore(<line>): <version> -- <summary>` (the release commit's own summary,
not "regenerate version_history.json for X"). Two commits, bump then
regenerate, in that order — never combined, never reordered. The local gate
runs before the bump, so nothing else catches a missed regeneration.

## Step 4 — Amend a wrong prediction, do not hide it

If the plan predicted a level or an `Edge:` the work did not deliver, amend
the header in this commit and say why in one clause.

## Step 5 — Move the document

`git mv` the plan — and any spec it was built from, if nothing else live
still builds from it — into `implemented/` for work that reached `main`, or
`no-lift/` for a plan whose code deliberately did not.

## Step 6 — Remove the worktree

Per `document-lifecycle.md`'s naming. Never delete a branch containing
`backup` — `guardrails.py` denies it, and that deny is correct.

## The gate

`VERSION.json`, the regenerated history and the moved plan are all in the
log; the worktree is gone; no full-suite run happens after a clean merge.
