# Working conventions

Referenced from the root `CLAUDE.md`.

- Conventional commits (`feat:`, `fix:`, `test:`, `docs:`, `refactor:`), one
  commit per task; full suite + `make check` green before each.
- Active plans live in `docs/superpowers/plans/*.md` with a Progress block at
  the top; the per-task execution ledger is `.superpowers/sdd/progress.md`
  (gitignored). Update both when completing plan tasks — both have drifted
  before (tasks marked done that weren't), so verify against `git log` and
  actual files before trusting either.
- **Every spec and plan filename ends in `-vN`, from one repo-wide counter that
  only ever increments.** Not per-feature, not per-document-type: specs and
  plans draw from the same sequence, so `-v11` is the eleventh design document
  written in this repo regardless of which feature it belongs to and whether it
  is a spec or a plan. Find the next number with
  `ls docs/superpowers/{specs,plans}/ | grep -o 'v[0-9]*' | sort -V | tail -1`.
  A number is never reused and never renumbered once committed — links and
  commit messages reference it. Revising a document in place keeps its number;
  only a genuinely new document takes the next one. (`gatekeeper-v6_1…_12` are
  parts of one document, not twelve numbers — a split like that reuses the
  parent's number with a `_N` part suffix.) Documents predating this convention
  (2026-08-08) keep their existing names; the specs written before it have no
  `-vN` and are not backfilled.
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
