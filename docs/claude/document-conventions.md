# Document conventions — specs and plans

Referenced from the root `CLAUDE.md`. **Read before writing any spec or plan.**

This file is only about *authoring* the documents. Closing one out — the
`implemented/` and `no-lift/` moves, worktree naming and removal — is
`document-lifecycle.md`. Session hygiene (commits, concurrent sessions) and the
`VERSION.json` rules are `working-conventions.md`.

## Naming

**`docs/superpowers/{specs,plans}/YYYY-MM-DD-vN-<document-name>.md` — every
new spec and plan is numbered at creation, before the first commit that
creates it:**

```
2026-08-25-v58-partial-plan-reframe-design.md   (spec, live, numbered from creation)
2026-07-14-v6-gatekeeper_0-index.md             (one document split into parts, still numbered as one)
```

**History.** This repo briefly ran a *deferred*-numbering scheme
(2026-08-24 – 2026-08-25): specs and plans stayed numberless while live, and
got their `vN` only at close-out, to avoid a number claimed up front
colliding with reordered execution or sitting unused as a permanent gap.
That reasoning was sound on its own terms, but it broke on a case it didn't
account for: `v56`/`v57` were spent as informal hotfix labels in commit-
message subjects (`fix(v56): ...`, `perf(v56): ...`, `fix(v57): ...`) with
no matching doc file at all — a scheme that only ever counted doc filenames
had no way to see those numbers were already gone, and a document numbered
at its own close-out under that scheme would have reissued one of them.
Reverted back to numbering at creation for that reason, with the counter now
reading two sources instead of one (below) so an informal commit-message
`vN` can't be silently reissued again.

**`vN` is one repo-wide counter that only ever increments.** Not
per-feature, not per-document-type: specs and plans draw from the same
sequence. Next number, computed from **both** doc filenames and git log —
recomputed immediately before the commit that creates the document, not
trusted from an earlier read:

```bash
{ find docs/superpowers/specs docs/superpowers/plans -name '*.md' | grep -oE 'v[0-9]+'
  git log --oneline --all | grep -oE '\(v[0-9]+\)' | grep -oE '[0-9]+' | sed 's/^/v/'
} | sort -V | tail -1
```

Use `find`, not `ls`, on the two directories — closed documents live one
level down in `implemented/`/`no-lift/`, and an `ls` that misses them
returns a stale maximum. The `git log` half exists specifically for the
`v56`/`v57` case above: a hotfix committed straight to `main` with a `vN`
label in its subject line but no accompanying spec or plan file. Recompute
right before committing, not once at the start of a session — concurrent
sessions share this counter (`working-conventions.md`), and a number that
was free five minutes ago may not be now.

**Concurrent-session collision.** If two sessions each compute the same
"next" number and both commit, the first commit to land on `main` keeps it.
The second is caught on the next `git fetch`/`pull` — `git log --all` will
show the number already used — and that session recomputes and renames its
own file **before** its own commit, never after one has already landed.
Never reuse a number, and never renumber one already committed to `main` —
commit messages and cross-links reference it from the moment it lands.
Revising an existing document in place keeps its number; only a genuinely
new document takes the next one. A document split across files shares the
parent's number with a `_N` part suffix rather than consuming N numbers
(`v6-gatekeeper_1…_12` are parts of one document, not twelve numbers) —
assigned once, at whichever part is written first.

### A spec and its plan may share a number

**Duplication is allowed across `specs/` and `plans/`, specifically for a
spec and the plan built from it.** A plan written from an already-numbered
spec reuses that spec's number directly — it's already known, no fresh count
needed. `v15-jinja-cutover-design.md` (spec) paired with
`v15-jinja-cutover.md` (plan) is the shape this produces; sixteen existing
pairs do this (`v0`, `v2`, `v5`, `v7`, `v8`, `v10`, `v30`–`v36`, `v39`,
`v44`). Reusing the spec's number for its plan is the natural reading of
"the `vN` work" — a reader can find both halves of one feature under one
number without a cross-reference.

A shared number is ambiguous when a spec spawns more than one plan
(`v15-jinja-cutover` in fact fed `v16-angular-migration`, a *different*
number, because the cutover itself was left to a later plan) or a plan draws
on more than one spec — those cases take the next free number the usual way,
computed fresh at that document's own creation, same command as above.

Still link a plan to its spec via the plan's `**Spec:**` header line even
though both may already carry the same number — it stays unambiguous where a
shared number alone is not (a plan can name exactly which of a spec's
several children it is, and the header survives a spec later feeding a
second, differently-numbered plan).

**Renaming a document is not renumbering it.** The 2026-08-13 sweep moved every
existing file to this layout and rewrote all 151 references across 57 files; the
numbers themselves were untouched. Two specs that had never had a number and no
sibling plan to inherit one from (`one-trade-per-ticker`, `admin-design-system`)
were retro-assigned `v19` and `v20` — the next free values — so no file is left
in the old format. Every document numbered before a numbering-scheme change
(2026-08-24's move to deferred numbering, and 2026-08-25's move back) keeps
the number it already has — each change governs what a *new* document does
going forward, never a retroactive renumbering.

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
| Plan **file** | 1000–1500 lines | **1500 lines**, no exceptions |

Over the limit, **split — do not compress.**

### The 1500-line cap is per file, not per plan

**No plan file may exceed 1500 lines.** A plan of any size is legal; a *file*
over 1500 lines is not. The cap is a line count rather than a task count or a
byte count because lines are what a `grep -A 120` window, a `sed -n` range and
a reviewer's scroll are all measured in, and because a task-count budget stops
predicting anything once tasks carry real test and implementation code — v67's
Part 2 came in at 4186 lines across 22 tasks, roughly 190 lines each, and no
task in it was verbose.

Aim for 1000–1500. A trailing file under 1000 is fine and normal — the split
falls where the task boundaries fall, and **a task is never split across
files.** Better a 700-line last file than a task whose test code is in one file
and its implementation in another.

**Splitting a part that is already numbered:** append a letter, not a new
number. `_2-trading-state.md` becomes `_2a-trading-state-trades.md`,
`_2b-trading-state-plans.md`, and so on. The letter is a file boundary only —
the part keeps its identity, its Alembic revision prefix, its task-id prefix
and its exit criteria. Put the part's `## Parallelisation`, its revision-id
table and its exit criteria in the `a` file, and give every later file a short
header pointing back at it rather than repeating them.

Task ids do not change when a file splits, so `/task-brief P2-07` and
`grep -rn "^### Task P2-07" docs/superpowers/plans/` both keep working without
anyone knowing which letter a task landed in. That is the property that makes
lettering cheap: **splitting a file must never change a task's address.**

**When splitting an existing file, verify no task was dropped.** A line-range
split silently loses whatever falls in a gap between two ranges. The check is
one command, and it is not optional:

```bash
for f in docs/superpowers/plans/<base>_*.md; do
  echo "$(basename $f): $(grep -o '^### Task [A-Z0-9-]*' $f | tr '\n' ' ')"
done
```

Read the ids across the files as one sequence. A missing id is a task that no
longer exists anywhere — and if the pre-split file was untracked, it is not in
git either.

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
the phases in the numbered parts. The original 822 KB monolith `v6-gatekeeper`
was split from was deleted outright rather than kept alongside the parts —
recover it from git history if a session ever genuinely needs the pre-split
version.

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
This applies to **every** suite a plan's own files touch, not just the Python
one: a plan that only edits `frontend/` verifies itself once with
`cd frontend && npm test`; a plan that touches both gets one full run of each,
still only at the end. The per-task check is the narrow one — Python:
`python scripts/dev/testrun.py file tests/test_<the file that task touched>.py`
(~7s), or `... fast` (~27s) when the task's blast radius genuinely crosses
files; frontend: `npm test -- --include <the one spec file that task
touched>`. Neither `... full` nor a bare `npm test` (no `--include`) is a
per-task step, and a plan that writes "run the full suite" into every task's
verification block is writing a plan that costs an extra 40–260s (Python) or
several seconds of a full Angular rebuild (frontend) per task for information
the narrow run already gave.

So every plan ends with a verification task that runs each touched suite's
full run **once**, over everything the plan implemented:

```markdown
### Task A9: Full-suite verification

Run `python scripts/dev/testrun.py full` (or dispatch the `test-runner`
subagent) once, over all of Phase A. Expect `0 failed`, `0 xfailed`.
If the plan touched `frontend/`, also run `cd frontend && npm test` once.
**If either is not green, fix forward from those failures** — they are this
plan's regressions, and the task is not done until both runs are.
```

That final run is the gate, and it is a real one: it is where the plan's
regressions surface, so a red result is the start of the work, not a reason to
re-litigate earlier tasks. Fix from the failures the run names.

**A full run triggered mid-plan to chase a real, already-observed failure
(a compile error, a suspicious ordering bug) is debugging, not a second
verification task** — it doesn't need its own plan step and isn't the
violation this section forbids. What the section forbids is *routinely
scheduling* a full run after every task as if it were the per-task check.

**After merging the plan's branch to `main`, do not run either suite again.**
The branch was green when the merge started and a conflict-free merge does not
produce code nobody ran. The one exception is a merge that actually resolved
conflicts — that resolution is new, unrun code, and it gets the one run.

## When a plan stops being live

Everything about closing a document out — moving it to `implemented/`, the
`no-lift/` case for a plan whose code never reached `main`, and how worktrees
are named and removed — lives in `document-lifecycle.md`.
