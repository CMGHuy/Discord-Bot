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
