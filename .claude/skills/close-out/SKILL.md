---
name: close-out
description: The plan close-out ritual -- resolve the version bump from VERSION.json, regenerate version_history.json, move the plan document to implemented/ or no-lift/, and remove its worktree. Run as /close-out, or by Claude itself once a plan's final task (the full-suite run) is green and its results are recorded.
---

# Plan close-out

## Step 1 — Read the authority

`docs/claude/document-lifecycle.md` and `docs/claude/working-conventions.md`.
This skill is the checklist; the reasoning behind every step below lives
there, not here.

## Step 2 — Clear the panel

If the plan's spec carries a `**Panel:**` line, run `/panel` with those
roles over the plan's full diff (`main...<branch>`, or `<merge>^1...<branch>`
once merged) and its recorded results. An unresolved `BLOCKING` finding stops
the close-out here. A spec with no `**Panel:**` line (v145 and earlier) skips
this step.

## Step 3 — Resolve the bump from disk

Read `VERSION.json` — never a plan header, never memory, never an earlier
task's note. Increment only the line named by the plan's `Bump:`; leave the
other line untouched. `Bump: none` means no release commit at all — Step 4
(the version-bump mechanics) does not apply, but proceed to Step 5 anyway:
`Bump: none` is itself a prediction that Step 5 must check, not a reason to
skip it.

## Step 4 — Stamp, commit, then regenerate

Set that line's `*_updated` stamp to now, in the existing format, and commit
`VERSION.json` alone: `release(<line>): <version> -- <summary>`. Then run
`python scripts/dev/build_version_matrix.py` and commit the regenerated
`swingbot/admin/version_history.json` as its own next commit:
`chore(<line>): <version> -- <summary>` (the release commit's own summary,
not "regenerate version_history.json for X"). Two commits, bump then
regenerate, in that order — never combined, never reordered. The local gate
runs before the bump, so nothing else catches a missed regeneration.

## Step 5 — Amend a wrong prediction, do not hide it

If the plan predicted a level or an `Edge:` the work did not deliver, amend
the header and say why in one clause — fold it into Step 4's commit if that
ran, otherwise into Step 6's move commit.

## Step 6 — Move the document

`git mv` the plan — and any spec it was built from, if nothing else live
still builds from it — into `implemented/` for work that reached `main`, or
`no-lift/` for a plan whose code deliberately did not.

## Step 7 — Remove the worktree, unless this closed to `no-lift/`

For an `implemented/` close: remove the worktree and its branch, per
`document-lifecycle.md`'s naming. Never delete a branch containing `backup`
— `guardrails.py` denies it, and that deny is correct.

For a `no-lift/` close: leave the worktree and branch in place. They are the
only copy of that unmerged work; deleting them is the human partner's call,
not a default step here.

## The gate

No unresolved `BLOCKING` panel finding; `VERSION.json`, the regenerated
history and the moved plan are all in the log; the worktree is gone for an
`implemented/` close, or deliberately kept for a `no-lift/` one; no full-suite
run happens after a clean merge.
