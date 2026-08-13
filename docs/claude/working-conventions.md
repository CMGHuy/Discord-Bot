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
- **Concurrent Claude sessions share this working tree.** Stage specific
  files, never `git add -A`; commit generated artifacts (especially the
  registry) immediately — uncommitted generated state has been silently wiped
  by another session's git operations before.
- Live git worktrees under `.claude/worktrees/` (currently `cockpit-v3` and an
  agent worktree) are full repo copies. Check `git worktree list` before
  assuming a stray path is dead. Never edit files there from a main-tree
  session — you will be editing a different branch.
