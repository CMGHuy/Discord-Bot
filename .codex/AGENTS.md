# Codex instructions

This repository's shared operating knowledge is maintained in `CLAUDE.md` and
the focused documents under `docs/claude/`. Treat those documents as the
canonical project guidance. Read the relevant focused document before working
in an area it covers; do not load plan files, indexes, or historical plans in
full when a narrow extract will answer the question.

**Claude Code is this repo's primary operator; this file is a downstream
mirror of `CLAUDE.md`, maintained BY Claude sessions, not the other way
around.** Never edit `CLAUDE.md` or `docs/claude/*.md` from a Codex session,
including to "fix" a disagreement with this file — this file is the one that
gets corrected to match `CLAUDE.md`, not the reverse.

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
incident exposed a real defect. Never expose or read `.env` or `.env.bak` unless
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

## Testing and long-running work

Use the test wrapper rather than the full raw suite:

- `python scripts/dev/testrun.py file tests/test_foo.py` while iterating.
- `python scripts/dev/testrun.py fast` for broader, non-render-heavy checks.
- `python scripts/dev/testrun.py full` once as final verification of an entire
  plan; do not rerun it after a clean merge unless conflicts were resolved.

Green means zero failures and zero xfails. A changed test count is not itself a
failure. Use `make check` for syntax validation when applicable. Backtests and
grids can run for hours; do not launch broad sweeps casually. Ensure long work
emits flushed progress per meaningful unit, and keep an observable progress
record for multi-step background work.

## Specs, plans, and versioning

Use `docs/superpowers/{specs,plans}/YYYY-MM-DD-vN-<name>.md`. Determine a new
`vN` from both existing document filenames and git history immediately before
creating or committing the document, as documented in
`docs/claude/document-conventions.md`. Do not reuse or renumber an already
committed number. A plan created from an existing spec reuses that spec's
number. Document numbers and `VERSION.json` release versions are independent.

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
