# Working conventions

Referenced from the root `CLAUDE.md`.

- Conventional commits (`feat:`, `fix:`, `test:`, `docs:`, `refactor:`), one
  commit per task; full suite + `make check` green before each.
- Active plans live in `docs/superpowers/plans/*.md` with a Progress block at
  the top; the per-task execution ledger is `.superpowers/sdd/progress.md`
  (gitignored). Update both when completing plan tasks — both have drifted
  before (tasks marked done that weren't), so verify against `git log` and
  actual files before trusting either.
- **Concurrent Claude sessions share this working tree.** Stage specific
  files, never `git add -A`; commit generated artifacts (especially the
  registry) immediately — uncommitted generated state has been silently wiped
  by another session's git operations before.
- Live git worktrees under `.claude/worktrees/` (currently `cockpit-v3` and an
  agent worktree) are full repo copies. Check `git worktree list` before
  assuming a stray path is dead. Never edit files there from a main-tree
  session — you will be editing a different branch.
- **Verification debt: waive it, never fabricate it.** Established by
  gatekeeper-v7 G217, made a standing rule by plan v8 Task V42. Some gates
  cannot be re-run after the fact — a shadow-mode parity window nobody logged,
  a live smoke on a bot that has since been reconfigured, a forward test whose
  window has passed. When you hit one:
  1. Restate in one sentence what the gate was meant to verify.
  2. Say whether production history can answer it retroactively — and if it
     cannot **in principle** (the data was never generated), say that plainly
     rather than approximating it with something adjacent.
  3. Write an explicit waiver naming the weaker substitute evidence, and naming
     it *as* weaker. "Has run N weeks in production with zero related
     incidents" is a real, useful sentence; it is not the gate, and the waiver
     must not read as though it were.
  4. **Leave the checkbox unticked.** A ticked box is a claim that the stated
     evidence exists. If it doesn't, the box is a lie that outlives everyone who
     knew the context — and the next reader has no way to tell it from a real
     pass. Plan v8 V41 left G219 Step 6 open for exactly this reason: its
     precondition names a carry-over doc that does not exist.

  The failure this prevents is specific and has happened here: a plan-level
  claim ("44 of 90 implemented", "the gate is live") that no longer matches the
  code, believed by later sessions because nothing distinguishes a mirrored
  claim from a verified one.
