# Document conventions — specs and plans

Referenced from the root `CLAUDE.md`. **Read before writing any spec or plan.**

Session hygiene (commits, concurrent sessions, worktree safety) and the
`VERSION.json` rules live in `working-conventions.md`; this file is only about
authoring the documents themselves.

## Naming

**`docs/superpowers/{specs,plans}/YYYY-MM-DD-vN-<document-name>.md`** — date,
then version, then name:

```
2026-08-08-v16-angular-migration.md          (plan)
2026-08-08-v15-jinja-cutover-design.md       (spec)
2026-07-14-v6-gatekeeper_0-index.md          (one document split into parts)
```

The version sits immediately after the date rather than at the end (its position
until 2026-08-13) so a directory listing sorts by date and then by version, and
so the number is visible without reading to the end of a long name.

**`vN` is one repo-wide counter that only ever increments.** Not per-feature,
not per-document-type: specs and plans draw from the same sequence, so `v11` is
the eleventh design document written in this repo regardless of which feature it
belongs to or whether it is a spec or a plan. Next number:

```bash
find docs/superpowers/specs docs/superpowers/plans -name '*.md' \
  | grep -oE 'v[0-9]+' | sort -V | tail -1
```

Use `find`, not `ls` on the two directories — closed documents live one level
down in `implemented/`, and an `ls` that misses them returns a stale maximum and
makes you reuse a number.

Never reuse a number, and never renumber a committed one — commit messages and
cross-links reference it. Revising a document in place keeps its number; only a
genuinely new document takes the next. A document split across files reuses the
parent's number with a `_N` part suffix rather than consuming N numbers
(`v6-gatekeeper_1…_12` are parts of one document, not twelve numbers).

### A spec and its plan may share a number

**Duplication is allowed across `specs/` and `plans/`, specifically for a
spec and the plan built from it.** `v15-jinja-cutover-design.md` (spec)
paired with a `v15-jinja-cutover.md` (plan) is fine — it is in fact the
common case historically: sixteen existing pairs already do this (`v0`,
`v2`, `v5`, `v7`, `v8`, `v10`, `v30`–`v36`, `v39`, `v44`). Reusing the spec's
number for its plan is the natural reading of "the `vN` work" — a reader can
find both halves of one feature under one number without a cross-reference.

**This is a deliberate reversal of a stricter same-day rule** (uniqueness
across both folders) that briefly lived in this section. That rule was
reasoned through — and its rationale is worth keeping in mind even though the
policy is reverted: a shared number is ambiguous when a spec spawns more than
one plan (`v15-jinja-cutover` in fact fed `v16-angular-migration`, a
*different* number, because the cutover itself was left to a later plan) or a
plan draws on more than one spec, and it can silently consume a number that a
concurrent session was about to claim for something unrelated. Those
failure modes are real; they are just judged a smaller cost than the
friction of forcing every spec/plan pair apart.

**What duplication covers, precisely:** ONE spec and the ONE plan built
directly from it may share a number. It does not relax "never reuse a
number" for two unrelated documents — a second, unrelated plan spawned from
the same spec, or a plan drawing on a second spec, still takes the next free
number the usual way:

```bash
find docs/superpowers/specs docs/superpowers/plans -name '*.md' \
  | grep -oE 'v[0-9]+' | sort -V | tail -1
```

Still link a plan to its spec via the plan's `**Spec:**` header line even
when the numbers match — it is unambiguous where a shared number is not (a
plan can name exactly which of a spec's several children it is, and the
header survives a spec later feeding a second, differently-numbered plan).

**Historical continuity:** the sixteen existing pairs were never an
exception to reconcile — they are the convention this section restores.

**Renaming a document is not renumbering it.** The 2026-08-13 sweep moved every
existing file to this layout and rewrote all 151 references across 57 files; the
numbers themselves were untouched. Two specs that had never had a number and no
sibling plan to inherit one from (`one-trade-per-ticker`, `admin-design-system`)
were retro-assigned `v19` and `v20` — the next free values — so no file is left
in the old format. Their numbers therefore say nothing about when they were
written, which is the one place the counter's chronology does not hold.

## The header block

Every new spec and plan carries three lines above its body.

**`Version:`** — `ui X.Y.Z · bot A.B.C`, copied from `VERSION.json` **as of the
commit that authors the document**. It records which release the document was
written against, so it is never refreshed afterwards; a doc from July keeps
July's numbers even while the plan is still active. Documents predating this
convention (2026-08-08) were left unstamped rather than backfilled with versions
that would have to be reconstructed from git.

**`Bump:`** — the release level the work *implies*: `ui minor (1.2.x → 1.3.0)`,
`bot patch`, or `none`. A different statement from `Version:` above it —
`Version:` is what the repo was at, `Bump:` is a prediction about what the work
will earn when it ships. Take the level from "The three levels" in
`working-conventions.md`, and argue it from **observable difference, not the size
of the feature**: a 400-line spec whose whole effect is internal is a patch, and
a one-flag spec that hands every user a different product is a minor.

The bump used to be decided at release time, by whoever happened to be
committing, from a diff they were looking at rather than from the impact the work
was designed for. That is the worst moment to ask: the reasoning that answers it
was worked out during the brainstorm and has been out of context for days. So the
spec commits to a level up front and the release commit honours or overrides it
deliberately. Both are fine; a silent guess is not.

A spec that predicts a minor and lands as a patch is **not a failed prediction to
hide** — amend the line in the commit that closes the spec and say in one clause
why the impact came out smaller. That edit is the cheapest record of a thing this
repo gets wrong often: mistaking effort for impact. Release B is the standing
example — 20 templates and 10 test files deleted, correctly a patch, because
nobody was being served the thing that was removed.

Two cases the three levels do not spell out:

- **A spec that ships no running code bumps nothing.** Documentation, a
  measurement, a closed pre-registration, a plan concluding "do not build this" —
  all `Bump: none`. A negative result is a finished spec, not a release.
- **A spec spanning two components bumps both lines, separately graded.** `v23`
  is the live example: a data-model change plus an endpoint the Discord alert
  path also reads is a `bot` patch, while a chart the user looks at every day
  becoming a different chart is a `ui` minor. One document, two levels, two
  independent release commits.

**`Edge:`** — the profit mechanism the work buys, and its expected direction.
One of `expectancy`, `harvest`, `volume`, or `none (integrity)`; see
"Prioritise expectancy and win rate" in the root `CLAUDE.md` for what each
means and why expectancy is the objective while win rate is only a constraint.

Like `Bump:`, it is a **prediction made while the reasoning is still in
context**, not a label applied at release. And like `Bump:`, a wrong prediction
is amended in the closing commit with one clause saying why — a plan that
predicted `expectancy` and measured nothing is the most useful record this repo
can keep, because it is the exact shape of the mistake the one-shot budget
exists to make expensive.

`Edge: none (integrity)` is a first-class answer, not an admission. Repo
cleanup, a look-ahead test, a version-history fix and a closed pre-registration
all buy zero edge and are all worth doing. The line exists so that work
**states** it buys none, rather than borrowing the language of a profit
improvement it does not deliver. A spec that cannot name its mechanism has
usually not decided what it is for.

Note the two lines answer different questions and routinely disagree: a
negative result is `Bump: none` but often `Edge: expectancy` (removing a
negative-expectancy population is a profit improvement that ships no code),
while a UI refresh can be `Bump: ui minor` and `Edge: none (integrity)`.

**`## Parallelisation`** — its own section, below.

## How long a document may be

Every session that opens a plan pays for it in context. `CLAUDE.md`'s first
section exists because three documents here grew past the point where reading one
is affordable at all — `v3-cockpit` at 652 KB is roughly 170K tokens, more than a
whole context window for a single file.

| Document | Budget | Hard limit |
|---|---|---|
| Spec | ~350 lines / 20 KB | 500 lines — a spec is read **whole** |
| Plan | ~15 tasks / 60 KB | 30 tasks or 120 KB, whichever comes first |

Over the limit, **split — do not compress.**

### Why splitting, and not writing less

The measurement that decides it, across every plan the repo has:

| Plan | Size | Tasks | Per task |
|---|---|---|---|
| `v24-control-alignment` | 48 KB | 14 | 3.4 KB |
| `v21-spa-refresh` | 136 KB | 51 | 2.7 KB |
| `v2-unified-plan-engine` | 300 KB | 110 | 2.7 KB |
| `v3-cockpit` | 652 KB | 115 | 5.7 KB |

Cost per task is near-constant at 2.7–5.7 KB, in the tight plans and the
landmines alike. **The landmines are not verbose, they are long** — 652 KB is 115
tasks in one file. Trimming prose inside tasks buys almost nothing, and buys it at
the worst price: `superpowers:writing-plans` requires real test code, real
implementation code and exact file paths in every task, and a task thinned to hit
a byte target becomes the "add appropriate error handling" placeholder that skill
exists to forbid. A vague task costs the *executing* session far more than the
bytes saved.

The lever is the number of tasks in one file, never the completeness of one task.

### Splitting

Reuse the parent's number with a `_N` part suffix — `v6-gatekeeper_0-index` …
`_11` is the worked example: one document, one number, twelve files, each 25–30
tasks. Write a `_0-index` part carrying the header block, the goal, the global
constraints, the parallelisation map and a table of what lives in each part; put
the phases in the numbered parts.

A spec over budget usually is not one spec. Check whether it is really two
subjects sharing a document — `v22` and `v23` were separated during their own
brainstorm for exactly this reason. Decompose first; split only what genuinely
cannot be decomposed.

### Being greppable is the other half

A plan is **never read whole** — `/task-brief E53` and
`grep -n "^### Task E53" -A 120` pull one task. That only works if the document is
mechanically addressable, so both forms are mandatory regardless of length:

- `### Task N: <name>` — one line, no variations, no prose before the colon.
- `# Phase N — <name>` for phase boundaries. **One hash, not two**, however wrong
  that looks beside the `##` sections around it. `CLAUDE.md` documents
  `grep -n "^# Phase"` as the way to orient in a plan, and every plan from
  `v2-unified-plan-engine` onward matches it. A plan using `## Phase` returns
  **zero** for that command and is invisible to the tool that exists to keep it
  out of context — the whole point of this section. (`v24` and `v25` were written
  with `##` and corrected; that is how this was found.)

## Saying what is parallelisable

**Every spec carries a `## Parallelisation` section**, and every plan built from
it repeats the grouping per phase. It names the groups whose tasks can be worked
at the same time, and — the half that actually matters — what forces everything
else to be sequential.

Without it the default is serial execution, because a session that cannot prove
two tasks are independent is right to assume they are not. The cost is real: a
phase of eight independent frontend tasks executed one at a time is eight round
trips for work that could have been three.

The dangerous failure is the other one. **Concurrent sessions share this working
tree** (see `working-conventions.md`), so two agents dispatched onto tasks that
touch the same file do not merge — the second overwrites the first, silently, and
the loss shows up later as a change that "did not take". Naming the groups is what
makes `superpowers:dispatching-parallel-agents` and `subagent-driven-development`
safe here rather than a gamble.

The test for putting two tasks in one group is **both** of:

1. **Disjoint files.** Not "different features" — different *files*. Two tasks
   that both edit `tokens.css` are sequential however unrelated they sound.
2. **No contract dependency.** Neither task consumes a symbol, token, endpoint or
   type the other introduces. A task that adds `--control-h` and a task that
   consumes it are sequential even though they touch different files.

Write it as groups, with the reason on the sequential edges:

```markdown
## Parallelisation

- **Group 1 (parallel):** A2, A3, A4 — one workspace file each, no shared file.
- **Sequential:** A1 before everything (introduces `--control-h`, which every
  other task consumes). A5 after Group 1 (the guard test asserts against rows
  those tasks convert; running it earlier fails for the right reason at the
  wrong time).
```

Be honest about a group of one. A phase that is genuinely a chain says so —
`Sequential throughout: each task consumes the previous task's payload field` —
and that sentence is worth as much as a wide group, because it stops the next
session re-deriving the dependency graph to find out.

## One full suite run, at the end of the plan

**A plan verifies itself once, as its own final task — not after every step.**
The per-task check is the narrow one: `python scripts/dev/testrun.py file
tests/test_<the file that task touched>.py` (~7s), or `... fast` (~27s) when the
task's blast radius genuinely crosses files. `... full` is **not** a per-task
step, and a plan that writes "run the full suite" into every task's verification
block is writing a plan that costs an extra 40–260s per task for information the
narrow run already gave.

So every plan ends with a verification task that runs the full suite **once**,
over everything the plan implemented:

```markdown
### Task A9: Full-suite verification

Run `python scripts/dev/testrun.py full` (or dispatch the `test-runner`
subagent) once, over all of Phase A. Expect `0 failed`, `0 xfailed`.
**If it is not green, fix forward from those failures** — they are this plan's
regressions, and the task is not done until the run is.
```

That final run is the gate, and it is a real one: it is where the plan's
regressions surface, so a red result is the start of the work, not a reason to
re-litigate earlier tasks. Fix from the failures the run names.

**After merging the plan's branch to `main`, do not run the suite again.**
The branch was green when the merge started and a conflict-free merge does not
produce code nobody ran. The one exception is a merge that actually resolved
conflicts — that resolution is new, unrun code, and it gets the one run.

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
