# Document lifecycle — closing plans out

Referenced from the root `CLAUDE.md` and from `document-conventions.md`, which
covers *authoring* a spec or plan. This file covers what happens when one stops
being live work: where it moves, and what happens to its worktree.

## Plans that are no longer live move to `implemented/`

**When a plan stops being live work, `git mv` it — and every spec it was built
from — into `docs/superpowers/plans/implemented/` and
`docs/superpowers/specs/implemented/` as part of the closing commit.** The top
level of those two directories then holds exactly the live work: what is in
flight, and what is designed but still to be built.

- **`implemented/` means "off the live list", not "every box is ticked".** It
  holds three kinds of document, deliberately: plans that finished; plans
  abandoned part-way (`v3-cockpit` at 15/467, `v4-edge-engine` at 133/399); and
  plans whose code was later deleted by a rollback (`v6-gatekeeper`, undone by
  `c84924a`). Read a moved plan's Progress block before assuming its code ships
  today — the folder does not promise that.
- **A plan is done when its own work is done**, not when the checkboxes agree. A
  plan closing with tasks deliberately cut, deferred to a successor, or left open
  for manual QA is finished — say so in its Progress block, then move it. `[x]`
  boxes lie in both directions; derive the verdict from deliverables and merge
  commits, never from the boxes.
- **A spec moves only when nothing live still builds from it.** A spec feeding
  several plans stays put until the last of them closes — `v15-jinja-cutover` is
  the example: its plan (`v16-angular-migration`) is closed and moved, but the
  cutover itself was handed to a future plan, so the spec stayed.
- **Not every spec has a plan.** A multi-component design doc can be executed
  component-by-component with no plan file at all; it is closed when every
  component is resolved — and **"resolved" includes a negative result or a
  component correctly not built because its own gate never opened.**
  `v17-market-context` is the example: P0/P1 shipped, P2a closed on measured
  evidence with an *empty* `REGIME_ALLOW`, P2b was gated off by P2a's failure,
  P3's script shipped. It carries a status table in its header; write one before
  moving a spec like that, or the next session will read the empty table as
  unfinished work and re-run a closed pre-registration.
- **Fix the references in the same commit.** Plans, specs, source docstrings
  (`swingbot/core/analytics/*.py`, `swingbot/admin/**`), tests and
  `.claude/skills/task-brief/SKILL.md` all cite these paths; after moving,
  re-point every reference and confirm none dangle.
- **The `SessionStart` hook only globs `plans/*.md`**, so a moved plan drops out
  of the cursor's "active plan" line by design. To resume one, move it back up
  first.

## A plan whose code never reached `main` moves to `no-lift/`, not `implemented/`

`implemented/` (above) is for plans whose work is done, however that turned
out — and it assumes `main` has at least some of that history, even a rolled-
back one. **A plan built and measured entirely on its own worktree branch,
found to buy no edge, and deliberately never merged is a different case**: `git
mv` it and its spec into `docs/superpowers/plans/no-lift/` and
`docs/superpowers/specs/no-lift/` instead, on `main`, as its own commit (the
worktree branch keeps its own closing commit separately — the two histories
never need to agree, since `main` never received the branch).

- **This is not a softer version of `implemented/`.** A plan there may still
  have shipped inert, default-off code on `main` (`AVWAP_LEVELS_ENABLED`
  before it flipped on, or `LEVEL_TOUCH_STRENGTH` if it had landed that way).
  `no-lift/` means `main`'s tree has *none* of the plan's code — only its
  docs, moved over deliberately so the live-plan list stays accurate.
- **State this explicitly in the plan's own closing note**, not just in the
  commit message: which branch the code lives on, and that it was a
  considered decision not to merge, not an oversight. `v36` is the example —
  see `docs/superpowers/plans/no-lift/2026-08-16-v36-level-touch-strength.md`.
- **The branch and worktree are not deleted as part of this.** "Never delete a
  branch whose name contains 'backup'" in the root `CLAUDE.md` is about a
  different case, but the caution generalizes: an unmerged branch with real,
  tested work is the only copy of that work, and deleting it is a decision for
  the human partner, not a default step of closing the plan.
- **`docs/claude/backtest-methodology.md`'s closed pre-registration table still
  gets a row** — the TRAIN/VALIDATION result is exactly what that table
  exists to record, whether or not the code shipped.

## Worktrees are named after the plan

**A worktree created to execute a plan takes the plan's file stem**, so the
branch, the directory and the document always name the same thing:

```
docs/superpowers/plans/2026-08-13-v21-spa-refresh.md
  → .claude/worktrees/2026-08-13-v21-spa-refresh/   (branch: same name)
```

Never invent a fresh topic name — a worktree called `trade-history-filter` takes
a second lookup to tie back to plan v9. For work that is not executing a plan, a
short topic name is fine; the rule binds only when a plan exists.

**Worktree execution is the default, not an opt-in.** Told to implement a `vN`
spec or plan with no instruction about where — no "inline", "in this session",
"in the current tree" — create the worktree under the naming convention above
before starting Task 1, without asking first. Asked to implement it directly in
the main tree, do that instead; that is an explicit override, not a violation
of this rule. The point of asking first would be to catch the case where a
worktree is wrong for the task, and a plan document is precisely the case where
it almost never is — plan execution is long-running, multi-commit, and wants
the review-and-merge boundary a worktree gives it for free.
