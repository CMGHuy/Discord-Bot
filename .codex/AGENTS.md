# Codex instructions

This repository's shared operating knowledge is maintained in `CLAUDE.md` and
the focused documents under `docs/claude/`. Treat those documents as the
canonical project guidance. Read the relevant focused document before working
in an area it covers; do not load plan files, indexes, or historical plans in
full when a narrow extract will answer the question. `CLAUDE.md` is deliberately
kept below 200 lines so every session can load its durable rules cheaply;
focused guidance belongs in `docs/claude/` and is read on demand.

**Claude Code and Codex collaborate on this repository.** Claude's
`CLAUDE.md` and `docs/claude/` remain the canonical shared guidance; this file
is their concise Codex mirror. When either agent adopts new canonical guidance,
it synchronizes this mirror before relying on it in Codex. Never reverse that
flow: a Codex-specific instruction does not modify the canonical Claude docs.

## Project and production boundary

Swingbot is a Discord swing-trade alert bot. It scans stock and ETF watchlists,
generates multi-horizon support/resistance trade plans and charts, and tracks
**paper trades only**. It never places orders. The stack is Python 3.11+,
discord.py, pandas/numpy, yfinance, mplfinance, pytest, JSON persistence, and
an Angular SPA served by Flask's `/api/v1/*` API.

The only production environment is the Hetzner VM documented in
`docs/deploy/DEPLOY_HETZNER.md`; this checkout is development. Do not deploy,
SSH to production, or make live changes unless the user explicitly asks. If an
authorized live change is made, mirror its non-secret equivalent into this
repository before considering the task complete: configuration in `.env.example`
or docs, local mirrored data where appropriate, and a committed code fix if the
incident exposed a real defect. When a production configuration default changes,
update `.env.example` too. Never expose or read `.env` or `.env.bak` unless
the user expressly authorizes it.

The primary entry points are `python bot.py` and `python admin_ui.py`. The
Docker image builds the Angular frontend, and bot/admin run as separate
containers from that image. Configuration is schema-driven through
`swingbot/config.py` and hot-reloaded by SIGHUP.

## Decision standards

For strategy, trading, or plan prioritization, rank work by pooled expectancy
(`ExpR`) first and win rate second. State the tradeoff when selecting work over
a higher-impact alternative. Every new spec or plan needs an `Edge:` header:
`expectancy`, `harvest`, `volume`, or `none (integrity)`. Methodology and
pre-registration rules always override profit motives: never rerun a closed
pre-registration, shrink sample size to reach a gate, or present a backtest as
anything stronger than a hypothesis test.

Read before acting:

- `docs/claude/architecture.md` before changing `swingbot/core`, plan engine,
  or scan pipeline.
- `docs/claude/known-traps.md` before changing data caching, scan output, or
  embeds.
- `docs/claude/backtest-methodology.md` before running or interpreting a
  backtest, grid, or validation.
- `docs/claude/edge-priorities.md` before choosing strategy work.
- `docs/claude/document-conventions.md` before authoring a spec or plan.
- `docs/claude/document-lifecycle.md` before closing a plan.
- `docs/claude/working-conventions.md` before committing or changing
  `VERSION.json`.
- `docs/claude/git-safety.md` before deleting branches or force-pushing.
- `docs/claude/testing-cost.md` before optimizing, timing, or interpreting a
  changed test count.
- `docs/claude/skills-tools.md` before choosing repo-specific skills or
  automation.

## Efficient repository navigation

`.ignore` excludes `.claude/worktrees/`, `market_data/`, `data/`, and `logs/`.
Use `rg` or `git grep` for search; never use unrestricted recursive search from
the repository root. Scope file discovery narrowly (for example,
`swingbot/**/*.py`), and never edit `.claude/worktrees/` from the main checkout.
The README is an index, not the source of detailed behavior. Read the linked
topic document instead.

Large or historical plans are context hazards. Extract a single task with a
line-targeted search; use `rg -n "^### Task" <plan>` to orient. The live plan
and spec lists are the top-level files in `docs/superpowers/plans/` and
`docs/superpowers/specs/`; `implemented/` and `no-lift/` are not active work.
Verify a reported next task actually appears in the active plan.

Claude Code sessions also enforce the worst of these habits mechanically via
`.claude/hooks/guardrails.py`, a `PreToolUse` hook that denies unscoped
`Glob`, `grep -r` from the repo root, huge `implemented/` plan reads, and
worktree writes from the main tree. That hook does not run for Codex; follow
the prose rules above directly.

## Testing and long-running work

Use the test wrapper rather than the full raw suite:

- `python scripts/dev/testrun.py file tests/test_foo.py` while iterating.
- `python scripts/dev/testrun.py fast` for broader, non-render-heavy checks.
- `python scripts/dev/testrun.py full` once as final verification of an entire
  plan; do not rerun it after a clean merge unless conflicts were resolved.
- Same cadence for the frontend: `npm test -- --include <spec>` per task while
  iterating, a bare `cd frontend && npm test` only once as the plan's final
  verification if the plan touches `frontend/`. A full run triggered mid-plan
  to chase an already-observed failure (compile error, ordering bug) is
  debugging, not a second verification step.

Green means zero failures and zero xfails. A changed test count is not itself a
failure. Use `make check` for syntax validation when applicable. Backtests and
grids can run for hours; do not launch broad sweeps casually. Ensure long work
emits flushed progress per meaningful unit, and keep an observable progress
record for multi-step background work.

Use at most one subagent at a time by default: dispatch it, wait for its result,
and then decide whether another is needed. Parallel subagents require the human
partner's explicit request; a plan's parallelisation section only describes what
could safely run concurrently. The project Codex config enforces this one-agent
limit.

## Specs, plans, and versioning

Use `docs/superpowers/{specs,plans}/YYYY-MM-DD-vN-<name>.md`. Determine a new
`vN` from both existing document filenames and git history immediately before
creating or committing the document, as documented in
`docs/claude/document-conventions.md`. Do not reuse or renumber an already
committed number. A plan created from an existing spec reuses that spec's
number. Document numbers and `VERSION.json` release versions are independent.

No plan file may exceed 1500 lines. Split an over-long plan into more `_N`
parts — lettered `_2a`/`_2b` when one part needs several files — and never
compress a task or split one across files. After any split, list
`^### Task` ids across the resulting files and confirm the sequence has no gap.

Write new specs and plans directly on `main` and commit them there as soon as
they are finished: no feature branch, no worktree, no approval gate for the
commit. Branch or create a worktree only when implementing a plan. A plan on an
unmerged branch is invisible to the session-start tooling that reports the
active plan, and checking out another branch removes it from the working tree
entirely. Uniquely numbered markdown files do not conflict the way code does,
so the branch ceremony buys nothing here.

When work stops being live, move its plan and related spec as part of the
closing commit: use `implemented/` for completed, abandoned, or rolled-back
work; use `no-lift/` for deliberately unmerged work that showed no edge.
Deliverables and merge commits, not checklist boxes, establish completion.

## Git safety

Never delete, force-push, or prune a branch whose name contains `backup`; ask
the user. Give `stable-*` branches the same rollback-point protection. Before
any other branch deletion, run `git rev-list --count main..<branch>` and stop
if it is non-zero. Never use destructive git commands unless the user clearly
authorized the exact action.

## Completion standard

Make focused, isolated changes that preserve module seams and surrounding code
style. Run proportionate verification and report the actual command/result; do
not claim a change works without evidence. For edits, finish with the concise
file summary required by the repository's development instructions.
