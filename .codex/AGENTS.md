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

**Admin SPA spacing (v89):** sibling panels are gapped by one token,
`--section-gap` (`.sb-stack`/host grids); panels never own outer margins.

## Decision standards

Ask as many questions as you need — there is no question budget. One per
message. When a request is ambiguous, a premise looks wrong, or a call is the
human partner's, ask instead of assuming. This does not license asking which
option to take after a finding is established; record the finding instead.
This is about ambiguity and decisions, not check-ins: once a plan task's scope
is clear, run it straight through — edits, tests, commits per the plan —
without pausing to ask permission to continue to the next step or task.

For strategy, trading, or plan prioritization, rank work by pooled expectancy
(`ExpR`) first and win rate second. State the tradeoff when selecting work over
a higher-impact alternative. Every new spec or plan needs an `Edge:` header:
`expectancy`, `harvest`, `volume`, or `none (integrity)`. Methodology and
pre-registration rules always override profit motives: never rerun a closed
pre-registration, shrink sample size to reach a gate, or present a backtest as
anything stronger than a hypothesis test.

Feature acceptance runs through one gate (`swingbot/core/backtesting/
acceptance.py`), driven by `python scripts/backtest/validate_component.py
--stage mde|walkforward|validation`. Within that gate win rate is the
objective and expectancy a non-inferiority constraint (ranking work is the
other way round). Six clauses, all applicable ones must pass: mix-standardised
ΔWR > 0 at one-sided p < 0.05 on a ticker-cluster bootstrap; ΔExpR lower 95%
bound > −0.01R; median planned RR and mean win R each fall no more than 2%;
accepted-alert count cut no more than 25%; permutation p < 0.05; and, for a
subset feature, the removed trades must be the bad ones (removed WR < retained
WR and removed ExpR ≤ 0). Two free stages stand in front of the one-shot
VALIDATION budget: an MDE precheck that refuses an unanswerable question with
the budget intact, and a fold-test consistency gate (≥ 2 of 3 fold years
improving, none worse than −1.0pp, N ≥ 30 per fold). The absolute
`win_rate >= 50` floor no longer gates feature acceptance — it survives only
as a strategy-badge threshold. `Edge: harvest` features are out of scope for
this funnel and must name the gate they use instead.

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

That hook gained three more deny rules this session: one blocking deletion of
a protected branch, one blocking a backtest/grid invocation that reopens a
closed pre-registration knob, and one blocking a malformed spec/plan write.
Each backs a prose rule already listed above — read `git-safety.md`,
`backtest-methodology.md`, or `document-conventions.md` respectively rather
than guessing why an equivalent Claude-side action was denied. Claude
sessions also now carry eight unprompted "Tier 1" integrity-tier skills that
self-trigger around these same situations; Codex has no skill runtime, so
those same `docs/claude/` files remain the only source of the underlying
rules here.

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
record for multi-step background work. Past 15 minutes of expected runtime,
that record must resolve to a percent-complete figure (rewritten at each
unit, not summed by the reader) so a mid-run progress question can be
answered with a number; delete the log once the task finishes.

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

Never hard-code a `ui`/`bot` version number in a plan, and give a plan no
`Version:` line at all. `Bump:` states the release level only — `bot patch`,
`ui minor`, `none`. The actual numbers are resolved by the plan's release task
at close-out: read `VERSION.json` from disk at that moment, increment the line
`Bump:` names, leave the other line alone, then regenerate the version history
with `scripts/dev/build_version_matrix.py` and commit it with the bump. Plans
run for days beside other plans, so any number predicted in advance is wrong as
soon as another plan releases first.

No plan file may exceed 1500 lines. Split an over-long plan into more `_N`
parts — lettered `_2a`/`_2b` when one part needs several files — and never
compress a task or split one across files. After any split, list
`^### Task` ids across the resulting files and confirm the sequence has no gap.

A plan runs the full test suite ONCE, as its own final verification task —
never per-task, and never again after a clean merge. The per-task check is the
narrow one: `python scripts/dev/testrun.py file tests/<the one file that task
touched>.py` (~7s), or `npm test -- --include <the one spec>` for `frontend/`.
Writing "run the full suite" into every task costs 40–260s per task for
information the narrow run already gave. Full cadence and the one exception:
`docs/claude/document-conventions.md`.

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

For v74-style parameter searches, use `config.searchable_attrs()` only.
`ScanParams` is frozen/picklable for process-pool safety; replay blind spots
must be recorded in the observability test, never hidden by a grid change.
Live scan and replay gating differ through OPEX and manual-scan behavior, so
do not unify them without a separate behavior-change decision.

Make focused, isolated changes that preserve module seams and surrounding code
style. Run proportionate verification and report the actual command/result; do
not claim a change works without evidence. For edits, finish with the concise
file summary required by the repository's development instructions.
