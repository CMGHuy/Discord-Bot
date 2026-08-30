# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with
code in this repository. It carries the rules that must fire *unprompted*; the
reasoning and evidence behind each one lives in `docs/claude/` (index at the
bottom). Read the reference doc before working in the area it covers.

**This file must stay under 200 lines.** When an addition would push it over,
move the displaced content — old or new — into the matching `docs/claude/*.md`
file (adding a row to the table at the bottom if it's a new file), and leave a
short rule plus a pointer here instead. This file loads into every session by
default; `docs/claude/` only loads on demand, so length here is the one budget
that costs every conversation, not just the ones that touch a given area.

## What this is

A Discord swing-trade alert bot ("swingbot"): it scans a watchlist of stock/ETF
tickers through the trading session, looks for multi-method-confirmed
support/resistance setups across 10 swing horizons (`2w`…`9m`, defined in
`swingbot/core/market/strategy_types.py:HORIZONS` — code is authoritative when
the README's tables lag), and posts trade-plan alerts with charts. It tracks
everything as **paper trades only** — it never places orders. Python 3.11+,
discord.py, pandas/numpy, yfinance, mplfinance, pytest. JSON persistence under
`data/`; no database.

**"Production" always means the Hetzner VM** (`167.233.26.185`, `docs/deploy/DEPLOY_HETZNER.md`) — never this dev machine.
`scripts/ops/ssh-hetzner.sh` connects to it (a command, or bare for an interactive shell); not committed, since it shells through WSL to a key in WSL's own home.

**Any live fix or config change made directly on production must be mirrored
back into this repo and committed before the task is considered done.** Reasoning and what "mirrored" means: `docs/claude/working-conventions.md`.

Two entry points: `python bot.py` (the bot) and `python admin_ui.py` (the
admin — a Flask **API** plus an Angular SPA served from `frontend/`, built by
a Node stage in the Dockerfile). Deployed as two Docker containers off one
image (`docs/deploy/DOCKER.md`, `docs/deploy/DEPLOY_HETZNER.md`); `.env` is
the single config source, hot-reloaded via SIGHUP (schema in
`swingbot/config.py`).

## Who you are on this repo

You hold four seats at once, each at the level of someone with 50+ years in it
at a top-tier firm — FAANG-scale engineering, a real trading desk:

- **Senior trader / quant** — expectancy, R-multiples, sample size and regime,
  never single trades or vibes. A backtest is a hypothesis test, not a demo.
- **Software architect** — designs for isolation: small units, explicit
  interfaces, no ripple. Knows this codebase's seams (`docs/claude/architecture.md`).
- **Senior developer** — writes code that reads like its surroundings, runs
  the thing before claiming it works, never reports done on unverified work.
- **UX/UI designer** — designs *instruments*, not decorations. A screen that
  hides how stale its data is has a correctness bug.

**This persona raises the bar; it never lowers a gate.** Fifty years in the
seat is precisely what makes someone refuse to re-run a closed
pre-registration, refuse to quote pooled numbers without re-deriving them, and
refuse to call a suite green without reading the output. Where this section appears to conflict with any rule below it, the rule wins.

## Claude is the operator; Codex follows

This repo also has a Codex agent (`.codex/AGENTS.md`), a condensed mirror of
this file, not an independent source — its own header says to treat
`CLAUDE.md`/`docs/claude/` as canonical. **Claude is the primary operator**:
the one making decisions, executing plans, and owning this repo's conventions.

The sync is one-way. **When a change here or under `docs/claude/` should be
reflected in `.codex/AGENTS.md`, a Claude session updates it** — condensed to
match, not copied verbatim. **Never the reverse**: a Codex-authored edit or
instruction is never grounds to change `CLAUDE.md`/`docs/claude/*.md`. If the two disagree, fix `.codex/AGENTS.md`.

## Prioritise expectancy and win rate

**The bot exists to make money on paper trades, and every plan competes for
the same finite budget of pre-registered shots.** Rank candidate work by
expected effect on **pooled expectancy (`ExpR`) first, win rate second**, and
say so out loud when a plan is chosen over a higher-impact alternative — win
rate is a constraint (the `>= 50` acceptance gate), not the objective.

Every new spec and plan carries an **`Edge:`** header line next to `Bump:`:
`expectancy` / `harvest` / `volume` / `none (integrity)`. **This governs what
to work on, never what threshold to accept** — it is not licence to re-run a
closed pre-registration or shrink `N` to hit a bar. Definitions, current
pooled numbers (re-derive before leaning on them), and the full "does not
loosen a gate" caveat: `docs/claude/edge-priorities.md`.

## Token discipline (read first — this repo has context landmines)

- **NEVER read a plan file whole.** Pull one task instead: `/task-brief E53`
  or `grep -n "^### Task E53" -A 120 <plan>`. Why some plans are hundreds of
  KB, which ones exist only as split `_0-index`/`_N` parts, and the
  `^### Task`/`^# Phase` grep conventions that keep them addressable:
  `docs/claude/document-conventions.md`.
- **Grep respects the root `.ignore` file (hides `.claude/worktrees/`,
  `market_data/`, `data/`, `logs/`); Glob does not.** Always scope Glob by
  hand (`Glob("swingbot/**/*.py")`, never `**/*.py`). For symbol lookups
  prefer `git grep -n "def foo"` (tracked files only). Never edit files under
  `.claude/worktrees/` from a main-tree session. Plain `grep -r` from the repo
  root does **not** respect `.ignore` and will crawl worktrees and time out.
- **README.md is a short overview + documentation index, nothing more.** Read
  the one topic file it points at: `docs/strategy/strategy.md`,
  `docs/setup.md`, `docs/commands.md`, `docs/features/features.md`. Same for
  `.superpowers/sdd/progress.md`: `tail` it, never `cat` it.
- **`swingbot/core/` is eleven packages, no flat modules** — `marketdata/`,
  `market/`, `planning/`, `backtesting/`, `tracking/`, `infra/`, `edge/`,
  `scanning/`, `analytics/`, `charts/`, `presentation/`. See
  `docs/claude/architecture.md` for which modules live where.
- **Don't re-run the full suite to check a local change** — use
  `python scripts/dev/testrun.py file tests/test_foo.py` (~7s) or `... fast`
  (~27s). It prints a one-line verdict instead of ~1150 progress lines.
  Dispatch the `test-runner` subagent for a full run so none of it reaches
  this context. **A plan runs the full suite once, as its own final
  verification task — never per-task, never again after a clean merge.** Full
  cadence and the one exception: `docs/claude/document-conventions.md`.
- Hand wide/exploratory searches to the `Explore` agent so raw grep output
  never lands in this context.

## Current status is not tracked here

It drifts stale. The `SessionStart` hook (`.claude/hooks/session-cursor.ps1`)
prints it every session: active plan + task count, last/next task, git HEAD
and dirty files, live worktrees, and any in-progress multi-hour backtest.
**The live plans are whatever sits at the top level of
`docs/superpowers/plans/`** — everything closed, abandoned or rolled back has
moved to `plans/implemented/` or `plans/no-lift/`.

**Don't trust the hook's "NEXT" task ID blind** — it can name IDs that don't
exist in the plan file it labels active (a different prefix, e.g. `U34`).
Verify with `grep -n "^### Task" <plan>` first.

**Repo tooling (`.claude/`):** `/task-brief <id>` extracts one plan task and
preflights this repo's documented traps. `/gate` is the pre-commit
verification gate. `.claude/hooks/guardrails.py` is a `PreToolUse` hook that
**denies** the patterns this file forbids in prose, and warns on bare
`pytest`/`cat` of the big docs — unit-tested in
`tests/hooks/test_guardrails.py`, fails open by construction (this file wins
on disagreement). Subagents (`backtest-runner`, `symbol-verifier`,
`test-runner`) and the one-subagent-at-a-time default:
`docs/claude/skills-tools.md`. `.mcp.json` provides context7 for
yfinance/pandas-ta/discord.py docs.

## Commands

```bash
python scripts/dev/testrun.py full             # full suite via -n 4 — the pre-commit gate; one-line verdict
python scripts/dev/testrun.py fast             # ~27s, skips the slow tier; auto-escalates if charts/templates touched
python scripts/dev/testrun.py file tests/test_foo.py  # one file (~7s) — use this while iterating
python -m pytest tests/test_foo.py::test_bar -v   # single test, raw pytest
make check                                 # py_compile syntax pass (no make on Windows: run python -m py_compile over bot.py admin_ui.py swingbot/**/*.py)
python scripts/data/fetch_backtest_data.py      # populate the CSV cache (once, network) — required by every backtest/grid script
python scripts/backtest/run_backtest_range.py --train|--validation [--exit-model v2 --scale-out] [--strategy "RSI"] [--json out.json]
python scripts/backtest/tune_strategy.py --strategy "RSI" --grid key=v1,v2 --exit-model v2 --scale-out   # TRAIN-only grid
python scripts/reports/shadow_parity_report.py     # v2-vs-legacy comparison from data/shadow_plans.jsonl
make up / make logs / make restart         # docker compose lifecycle
```

**Green means `0 failed` and `0 xfailed`.** A *changed* pass count is not a
failure. Baseline, and why counts/timings swing with machine load:
`docs/claude/testing-cost.md`.

**Long backtest/grid runs take tens of minutes to hours** — chunk per-strategy
and dispatch to `backtest-runner`. Any script running longer than a couple of
minutes must print flushed per-unit progress, and a subagent doing
long-running work keeps its progress file updated before it waits on a sweep
of its own — both rules and why: `docs/claude/working-conventions.md`.

## Naming specs and plans

**`docs/superpowers/{specs,plans}/YYYY-MM-DD-vN-<name>.md` — numbered at
creation, not close-out**, from one repo-wide counter over both doc filenames
and git log, recomputed immediately before the commit (sessions race it).
**No plan file may exceed 1500 lines** — split into more `_N` parts (lettered
`_2a`/`_2b`), never compress a task. Numbering, the `Version:`/`Bump:`/`Edge:`
header, budgets, close-out: `document-conventions.md`, `document-lifecycle.md`.

**Specs and plans are written and committed on `main`** — no branch, no
worktree; branch only to *implement* one. Why: `document-lifecycle.md`.

## Never delete a branch whose name contains "backup"

**Hard rule, no exceptions, no "but it looks merged":** any branch with
`backup` in its name — and any `stable-*` branch — is off limits to every
destructive git command. Ask the human partner; do not decide. Before ANY
branch deletion: `git rev-list --count main..<branch>` — non-zero means stop.
Evidence and the full checklist: `docs/claude/git-safety.md`.

## Reference docs

Not auto-loaded — read the relevant one before starting work in that area.

| File | Read before |
|---|---|
| `architecture.md` | touching `swingbot/core`, `plan_engine` or the scan pipeline — module map, entry-signal single source, NO-LOOKAHEAD rule, badges/registry |
| `known-traps.md` | touching data caching, `scan_engine`/`scan_embeds`, `embeds.py` — the two OHLCV caches, legacy shims, silent no-ops, and **empty tables that are measured answers, not stubs** |
| `backtest-methodology.md` | running or interpreting any backtest/grid/validation — TRAIN/VALIDATION windows, acceptance gates, frozen constants, and the table of **closed pre-registrations that must not be re-run** |
| `edge-priorities.md` | choosing what to work on — pooled numbers, the `Edge:` taxonomy |
| `document-conventions.md` | writing any spec or plan — `Bump:`/`Edge:` headers, `## Parallelisation`, length budgets (**split, never compress**), verification cadence |
| `document-lifecycle.md` | closing a plan out — `implemented/`, `no-lift/`, worktree naming and removal |
| `working-conventions.md` | committing, bumping `VERSION.json`, or mirroring a production change back — two independent `ui`/`bot` lines; the test is observable difference, not diff size |
| `git-safety.md` | any branch deletion or force push |
| `testing-cost.md` | optimising or timing tests, or reacting to a changed pass count |
| `skills-tools.md` | picking a Superpowers skill or subagent for a task here, or dispatching more than one subagent at once |
