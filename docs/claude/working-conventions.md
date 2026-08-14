# Working conventions

Referenced from the root `CLAUDE.md`.

- Conventional commits (`feat:`, `fix:`, `test:`, `docs:`, `refactor:`), one
  commit per task; full suite + `make check` green before each.
- Active plans live in `docs/superpowers/plans/*.md` with a Progress block at
  the top; the per-task execution ledger is `.superpowers/sdd/progress.md`
  (gitignored). Update both when completing plan tasks — both have drifted
  before (tasks marked done that weren't), so verify against `git log` and
  actual files before trusting either.
- **Every spec and plan filename is `YYYY-MM-DD-vN-<name>.md`** — date first,
  then the version, then the descriptive name. For example
  `2026-08-08-v16-angular-migration.md` and
  `2026-08-08-v15-jinja-cutover-design.md`.

  The version sits immediately after the date rather than at the end (its
  position until 2026-08-13) so that a directory listing sorts by date and then
  by version, and so the number is visible without reading to the end of a long
  name.

- **`vN` comes from one repo-wide counter that only ever increments.** Not
  per-feature, not per-document-type: specs and plans draw from the same
  sequence, so `v11` is the eleventh design document written in this repo
  regardless of which feature it belongs to and whether it is a spec or a plan.
  Find the next number with
  `ls docs/superpowers/{specs,plans}/ | grep -oE 'v[0-9]+' | sort -V | tail -1`.
  A number is never reused. Revising a document in place keeps its number; only
  a genuinely new document takes the next one. (`v6-gatekeeper_1…_12` are parts
  of one document, not twelve numbers — a split reuses the parent's number with
  a `_N` part suffix.)

  **Renaming a document is not renumbering it.** The 2026-08-13 sweep moved
  every existing file to this layout and rewrote all 151 references across 57
  files; the numbers themselves were untouched. Two specs that had never had a
  number and had no sibling plan to inherit one from
  (`one-trade-per-ticker`, `admin-design-system`) were retro-assigned `v19` and
  `v20` — the next free values — so no file is left in the old format. Their
  numbers therefore say nothing about when they were written, which is the one
  place the counter's chronology does not hold.
- New specs and plans carry a `**Version:**` line in their header block —
  `ui X.Y.Z · bot A.B.C`, copied from `VERSION.json` **as of the commit that
  authors the document**. It records which release the document was written
  against, so it is never refreshed afterwards; a doc from July keeps July's
  numbers even while the plan is still active. Documents predating this
  convention (2026-08-08) were left unstamped rather than backfilled with
  versions that would have to be reconstructed from git.
- **Every spec also declares the bump it *implies***, on a `**Bump:**` line in
  the same header block — `ui minor (1.2.x → 1.3.0)`, `bot patch`, or `none`.
  That is a different statement from `**Version:**` above it: `Version:` records
  what the repo was at when the document was written and is never refreshed,
  while `Bump:` is a prediction about what the work will earn when it ships.
  Derive the level from "The three levels" below, and argue it from **observable
  difference, not from the size of the feature** — a 400-line spec whose whole
  effect is internal is a patch, and a one-flag spec that hands every user a
  different product is a minor. See "What a spec's `Bump:` line is for".
- **Every spec states which of its tasks can run in parallel**, in a
  `## Parallelisation` section. See "Saying what is parallelisable".
## Versioning: when to bump `VERSION.json`

`VERSION.json` carries **two independent version lines**, `ui` and `bot`, and
the admin sidebar renders both. They move separately — `bot` sat at `1.1.2`
through five consecutive `ui` releases. **Bump only the line you changed**;
bump both only when the change genuinely lands in both.

The test is **not how large the diff is**. It is whether the thing the number
names became different *for whoever uses it*. This repo already contains the
pair that makes the distinction concrete:

| Release | What it did | Bump |
|---|---|---|
| **A** (`8ad637c`) | Flipped the default so the SPA became the admin UI | ui 1.0.9 → **1.1.0** (minor) |
| **B** (`8bfd050`) | Deleted the whole Jinja UI — 20 templates, `pages.py`, 10 test files | ui 1.2.1 → **1.2.2** (patch) |

Release B is by far the bigger diff and by far the smaller bump. It removed a
UI nobody was being served any more, so nobody's experience changed. Release A
changed one flag and every user got a different product. **Observable
difference is the question; size of change is not.**

### The three levels

**Patch — `x.y.Z`.** The default, and what nearly every release has been.
Anything that ships and that someone might notice: a new control, a bug fix, a
tuning change, a visual adjustment. Also the correct bump for a large internal
refactor or deletion with no outward effect.

**Minor — `x.Y.0`.** The component is materially different to the person using
it. Three in this repo's life, and they are the entire set:

- `ui 1.1.0` — Release A, the SPA becomes the admin UI.
- `ui 1.2.0` — the SPA refresh (plan v21): every workspace rebuilt.
- `bot 1.1.0` (`9b979be`) — Plan Engine v2: how trade plans are produced changed.

The shape of a minor is that someone who used this yesterday has to look at it
anew. An Angular migration is the canonical example.

**Major — `X.0.0`.** Never used. Reserved for a release that *breaks an
existing install* rather than improving it: `data/*.json` needing migration
before the bot will start, `.env` keys removed rather than added, or paper-trade
history becoming incomparable to what came before. If a deploy needs a manual
step on the server, or a one-way migration, it is major. Do not spend it on
"this is a big feature" — that is what minor is for.

### Each part is an integer, not a digit

`1.0.9` is followed by `1.0.10`, not by `1.1.0`. There is no carry and no
ceiling — `1.1.1000` is a perfectly legal version. A part rolls over **only**
when the rule above says the bump is a minor or a major, never because the
number next to it "ran out".

This is not hypothetical: `bot` ran `1.0.9 → 1.0.10 → … → 1.0.15` before
Plan Engine v2 took it to `1.1.0`, and that minor was earned by the engine
change, not by the counter. Reading `1.0.9` as "nearly 1.1" would have bumped
a minor for eleven patches in a row.

### When NOT to bump

Most commits. There have been roughly 20 bumps across the repo's whole life
against hundreds of commits. Do not bump for documentation, tests, CI or deploy
plumbing, comments, plans and specs, or anything that cannot change what a
running container does. `0379574` (a 600-line cleanup) and `ab7fe4c` (the deploy
path fix) correctly bumped nothing: neither alters what the bot or the admin
*does*.

### What a spec's `Bump:` line is for

The bump used to be decided at release time, by whoever happened to be
committing, from a diff they were looking at rather than from the impact the
work was designed for. That is the worst moment to ask the question: the
reasoning that would answer it — who sees a difference, and what kind — was
worked out during the brainstorm and has been out of context for days.

So the spec commits to a level up front, and the release commit either honours
it or overrides it deliberately. Both outcomes are fine; a silent guess is not.

A spec that predicts a minor and lands as a patch is **not a failed
prediction to hide** — amend the `Bump:` line in the same commit that closes
the spec and say in one clause why the impact came out smaller. That edit is
the cheapest possible record of a thing this repo gets wrong often: mistaking
effort for impact. Release B is the standing example — 20 templates and 10
test files deleted, and correctly a patch, because nobody was being served
the thing that was removed.

Two spec-specific cases the levels above do not spell out:

- **A spec that ships no running code bumps nothing.** Documentation, a
  measurement, a closed pre-registration, a plan that concludes "do not build
  this" — all `Bump: none`. A negative result is a finished spec, not a
  release.
- **A spec split across two components bumps both lines, separately graded.**
  The chart work is the live example: a data-model change plus a new endpoint
  that the Discord alert path also reads is a `bot` patch, while a chart the
  user looks at every day becoming a different chart is a `ui` minor. One
  document, two levels, and the two release commits stay independent.

### How

A bump is **its own commit**, touching only `VERSION.json`, in the established
format — and it goes **last**, after the work it names is committed and green,
so the version commit is a release marker rather than a guess about what will
land:

```
release(ui): 1.2.0 -- the SPA refresh
release(bot): 1.1.0 -- plan engine v2
```

Set the matching `ui_updated` / `bot_updated` stamp alongside it
(`YYYY-MM-DD HH-MM-SS`, UTC).

### What `last_updated` in the sidebar actually is

`get_versions()` also returns `last_updated` — `VERSION.json`'s own mtime — and
the sidebar shows it beside the numbers. It is **not** "when the version last
changed". Under the image-based deploy the file is copied into the image from a
fresh CI checkout, so its mtime is effectively *when the image was built*. That
is the useful reading and the one the UI wants, but do not mistake it for a
release date: it moves on every deploy, including deploys that bump nothing.

- **Concurrent Claude sessions share this working tree.** Stage specific
  files, never `git add -A`; commit generated artifacts (especially the
  registry) immediately — uncommitted generated state has been silently wiped
  by another session's git operations before.
- Live git worktrees under `.claude/worktrees/` (currently `cockpit-v3` and an
  agent worktree) are full repo copies. Check `git worktree list` before
  assuming a stray path is dead. Never edit files there from a main-tree
  session — you will be editing a different branch.

## Saying what is parallelisable

**Every spec carries a `## Parallelisation` section**, and every plan built from
it repeats the grouping per phase. It names the groups whose tasks can be worked
at the same time, and — the half that actually matters — what forces everything
else to be sequential.

Without it the default is serial execution, because a session that cannot prove
two tasks are independent is right to assume they are not. The cost of that
default is real: a phase of eight independent frontend tasks executed one at a
time is eight round trips for work that could have been three.

The dangerous failure is the other one. **Concurrent sessions share this working
tree** (see above), so two agents dispatched onto tasks that touch the same file
do not merge — the second overwrites the first, silently, and the loss shows up
later as a change that "did not take". Naming the groups is what makes
`superpowers:dispatching-parallel-agents` and `subagent-driven-development` safe
to use here rather than a gamble.

The test for putting two tasks in one group is **both** of:

1. **Disjoint files.** Not "different features" — different *files*. Two tasks
   that both edit `tokens.css` are sequential however unrelated they sound.
2. **No contract dependency.** Neither task consumes a symbol, token, endpoint
   or type the other one introduces. A task that adds `--control-h` and a task
   that consumes it are sequential even though they touch different files.

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
