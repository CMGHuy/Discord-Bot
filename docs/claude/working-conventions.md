# Working conventions

Referenced from the root `CLAUDE.md`.

- Conventional commits (`feat:`, `fix:`, `test:`, `docs:`, `refactor:`), one
  commit per task; full suite + `make check` green before each.
- Active plans live in `docs/superpowers/plans/*.md` with a Progress block at
  the top; the per-task execution ledger is `.superpowers/sdd/progress.md`
  (gitignored). Update both when completing plan tasks — both have drifted
  before (tasks marked done that weren't), so verify against `git log` and
  actual files before trusting either.
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
