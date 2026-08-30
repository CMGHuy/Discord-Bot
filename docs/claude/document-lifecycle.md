# Document lifecycle — where documents live, and closing plans out

Referenced from the root `CLAUDE.md` and from `document-conventions.md`, which
covers *authoring* a spec or plan. This file covers where a document lives
while it is being written, and what happens when it stops being live work:
where it moves, and what happens to its worktree.

## Specs and plans are written and committed on `main`

**Write a new spec or plan directly on `main`, and commit it there as soon as
it is finished.** No feature branch, no worktree, no waiting for approval to
commit. Branch or create a worktree only when you start *implementing* a plan.

Three reasons, and the second is the one that actually bit:

- **A document nobody can see is worse than one that needs editing.** Specs and
  plans exist to be read and argued with. A perfect plan on an unmerged branch
  has less value than a rough one on `main`, because only one of them is in
  front of the person who would correct it.
- **A plan stranded on a branch is invisible to the tooling.** The
  `SessionStart` hook (`.claude/hooks/session-cursor.ps1`) reports the active
  plan by reading the top level of `docs/superpowers/plans/` **in the current
  working tree**. A plan on another branch is not there, so every new session
  starts believing different work is active. Worse, checking out any other
  branch removes those files from disk — which reads as "my plans are gone"
  and is the specific failure this rule exists to prevent (2026-08-30, v67).
- **Documents cannot conflict the way code does.** A new `vN`-numbered file is
  a new path. The branch-then-merge ceremony buys isolation that a uniquely
  named markdown file does not need, and costs the visibility above.

**This does not weaken the numbering rule.** `vN` is still computed immediately
before the commit that creates the document, from both doc filenames and git
log — committing straight to `main` makes the concurrent-session race
*more* likely to be caught early, not less, because the number lands where
every other session can see it.

**It does not apply to the code a plan describes.** Implementation still
branches, and still uses a worktree when the plan says so — see "Worktrees are
named after the plan" below. The rule is about the document, not the work.

## Plans that are no longer live move to `implemented/`

**When a plan stops being live work, `git mv` it — and every spec it was built
from — into `docs/superpowers/plans/implemented/` and
`docs/superpowers/specs/implemented/` as part of the closing commit.** The top
level of those two directories then holds exactly the live work: what is in
flight, and what is designed but still to be built.

**The document already carries its permanent `vN` by the time this happens**
— `document-conventions.md`'s "Naming" section numbers every spec and plan at
creation, not at close-out, so this `git mv` is a pure move, never a rename:
`2026-08-25-v58-partial-plan-reframe-design.md` stays exactly that filename
when it relocates into `implemented/`. (A brief 2026-08-24 – 2026-08-25
deferred-numbering scheme would have assigned the number at this step
instead; it was reverted before any document reached this move under it, so
there is no lingering case to handle differently.)

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
never need to agree, since `main` never received the branch). Same as the
`implemented/` move above, this `git mv` is a pure move — the plan already
carries the `vN` it was given at creation, whether its code landed on `main`
or not.

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
branch, the directory and the document always name the same thing. Since a
plan is numbered at creation (`document-conventions.md`), that stem already
carries its `vN` from before execution starts, and never changes:

```
docs/superpowers/plans/2026-08-25-v58-partial-plan-reframe.md
  → .claude/worktrees/2026-08-25-v58-partial-plan-reframe/   (branch: same name)

# at close-out, the plan file only moves directory, never renames:
docs/superpowers/plans/2026-08-25-v58-partial-plan-reframe.md
  → docs/superpowers/plans/implemented/2026-08-25-v58-partial-plan-reframe.md
```

There is no point during or after execution where the worktree's name and
the plan's filename disagree.

Never invent a fresh topic name — a worktree called `trade-history-filter` takes
a second lookup to tie back to its plan. For work that is not executing a plan, a
short topic name is fine; the rule binds only when a plan exists.

**Worktree execution is the default, not an opt-in.** Told to implement a
spec or plan with no instruction about where — no "inline", "in this session",
"in the current tree" — create the worktree under the naming convention above
before starting Task 1, without asking first. Asked to implement it directly
in the main tree, do that instead; that is an explicit override, not a
violation of this rule. The point of asking first would be to catch the case
where a worktree is wrong for the task, and a plan document is precisely the
case where it almost never is — plan execution is long-running, multi-commit,
and wants the review-and-merge boundary a worktree gives it for free.

**And once a plan closes and the worktree merges, the worktree and its
branch are removed** as part of that same closing commit's work, before the
`git mv` into `implemented/`/`no-lift/` — simpler now than it was under
deferred numbering, since that move never has to rename anything the
worktree's own name would need to catch up to.
