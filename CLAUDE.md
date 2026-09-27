# CLAUDE.md

Guidance for Claude Code in this repository. It carries the rules that must
fire *unprompted*; the reasoning behind each lives in `docs/claude/` (index at
the bottom) — read the relevant one before working in that area.

**This file must stay under 200 lines.** An addition that would push it over means moving content — old or new — into the matching `docs/claude/*.md` (add a table row if new), leaving a short rule plus a pointer here.

## What this is

A Discord swing-trade alert bot ("swingbot"): scans a stock/ETF watchlist for
multi-method-confirmed support/resistance setups across swing horizons
(`strategy_types.py:HORIZONS` is authoritative) and posts trade-plan alerts
with charts. **Paper trades only** — it never places orders. Python 3.11+,
discord.py, pandas/numpy, yfinance, mplfinance, pytest; JSON under `data/`.

**"Production" always means the Hetzner VM** (`167.233.26.185`, `docs/deploy/DEPLOY_HETZNER.md`) — never this dev machine; `scripts/ops/ssh-hetzner.sh` (uncommitted) connects.

**Any live fix or config change made directly on production must be mirrored back into this repo and committed before the task is considered done.** Reasoning and what "mirrored" means: `docs/claude/working-conventions.md`.

Entry points: `bot.py` and `admin_ui.py` (Flask API + Angular SPA in
`frontend/`), two Docker containers off one image (`docs/deploy/`). `.env` is
the single config source, hot-reloaded via SIGHUP (schema: `swingbot/config.py`).

## Who you are on this repo

Senior trader/quant, software architect, senior developer and UX designer at
once — the persona raises the bar, never lowers a gate; rules below win.
**Ask via `AskUserQuestion`, one question per message, recommended option
first**, whenever something is ambiguous or the call is the partner's — no
question budget; never ask which option *after* a finding is established.
Once a plan task's scope is clear, run it straight through. Detail: `persona.md`.

## Claude is the operator; Codex follows

Root `AGENTS.md` is a condensed one-way mirror for Codex (which never loads
`.codex/AGENTS.md`); Claude updates it, never the reverse, and a Codex edit is
never grounds to change `CLAUDE.md`. Detail: `working-conventions.md` § Codex mirror.

## Prioritise expectancy and win rate

Rank work by effect on **pooled expectancy (`ExpR`) first, win rate second**
(a constraint, not the objective); say so when a plan beats a higher-impact
alternative. Every spec/plan carries **`Edge:`** (`expectancy` / `harvest` /
`volume` / `none (integrity)`) — it governs what to work on, **never what
threshold to accept** or licence to re-run a closed pre-registration or shrink
`N`. Detail: `edge-priorities.md`.

## Token discipline (read first — this repo has context landmines)

- **NEVER read a plan file whole.** Pull one task instead: `/task-brief E53`
  or `grep -n "^### Task E53" -A 120 <plan>`. Why some plans are hundreds of
  KB, which ones exist only as split `_0-index`/`_N` parts, and the
  `^### Task`/`^# Phase` grep conventions that keep them addressable:
  `docs/claude/document-conventions.md`.
- **Grep respects `.ignore` (hides worktrees, `market_data/`, `data/`,
  `logs/`); Glob and plain `grep -r` do not** — scope Glob by hand
  (`swingbot/**/*.py`), prefer `git grep -n` for symbols. Never edit
  `.claude/worktrees/` from a main-tree session.
- **README.md is only an index** — read the one topic file it points at.
  `tail` `.superpowers/sdd/progress.md`, never `cat` it.
- **`swingbot/core/` is eleven packages, no flat modules** — map:
  `architecture.md`.
- **Don't re-run the full suite to check a local change** — use
  `python scripts/dev/testrun.py file tests/test_foo.py` (~7s) or `... fast`
  (~27s). It prints a one-line verdict instead of ~1150 progress lines.
  Dispatch the `test-runner` subagent for a full run so none of it reaches
  this context. When a *plan* schedules its runs: "Naming specs and plans".
- Hand wide/exploratory searches to the `Explore` agent so raw grep output
  never lands in this context.
- **Route mechanical work to the role agents** (`task-implementer`,
  `task-reviewer`, `prod-inspector`, …) — `skills-tools.md` § Which agent for what.

## Current status is not tracked here

The `SessionStart` hook prints it (plan, next task, HEAD, worktrees, live
backtests); live plans are whatever sits at the top of
`docs/superpowers/plans/`. **Don't trust the hook's NEXT id blind** — verify
with `grep -n "^### Task" <plan>`. Tooling (`/task-brief`, `/gate`,
`guardrails.py`): `skills-tools.md`; detail: `document-lifecycle.md`.

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

**Long backtest/grid runs** go to `backtest-runner`, chunked per strategy.
Past a couple of minutes a run prints flushed progress; **past 15 minutes, a
percent figure** in a log deleted on completion. Detail: `working-conventions.md`.

## Naming specs and plans

**`docs/superpowers/{specs,plans}/YYYY-MM-DD-vN-<name>.md`, numbered at
creation** from one repo-wide counter (doc filenames + commit log), recomputed
right before the commit. `Bump:` states a level only, never a version number.
**No plan file over 1500 lines** — split into `_N` parts, never compress a
task. **Full suite once per plan, as its final task.** Specs and plans are
committed on `main`; branch only to implement. Run `/new-doc`; detail:
`document-conventions.md`, `document-lifecycle.md`.

## Keep every function under complexity 15

Every function and method you write or change ends at cyclomatic complexity
**< 15** (`python -m radon cc -s -n C <files>`): split into named helpers,
table-drive `if/elif` chains, return early. A legacy function already >= 15
never gets worse. A refactor never changes behaviour. Detail: `code-complexity.md`.

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
| `architecture.md` | touching `swingbot/core` or the scan pipeline — module map, NO-LOOKAHEAD |
| `known-traps.md` | touching data caching or embeds — two OHLCV caches, silent no-ops, **empty tables that are measured answers** |
| `backtest-methodology.md` | any backtest/grid/validation — acceptance gate, windows, **closed pre-registrations never re-run** |
| `edge-priorities.md` | choosing what to work on — pooled numbers, the `Edge:` taxonomy |
| `document-conventions.md` | writing any spec or plan — headers, `## Parallelisation`, split never compress |
| `document-lifecycle.md` | closing a plan out — `implemented/`, `no-lift/`, worktree naming and removal |
| `working-conventions.md` | committing, bumping `VERSION.json`, production changes, Codex mirror |
| `git-safety.md` | any branch deletion or force push |
| `testing-cost.md` | optimising or timing tests, or reacting to a changed pass count |
| `code-complexity.md` | writing or changing any function — the < 15 limit, how to measure it, how to split without changing behaviour |
| `persona.md` | deciding how to question the partner, or what bar a change must meet |
| `skills-tools.md` | picking a skill or agent, dispatching subagents, disabled plugins, driving a browser |
