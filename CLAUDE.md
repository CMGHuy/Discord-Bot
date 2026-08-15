# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Discord swing-trade alert bot ("swingbot"): it scans a watchlist of stock/ETF
tickers through the trading session, looks for multi-method-confirmed
support/resistance setups across 10 swing horizons (`2w`…`9m`, defined in
`swingbot/core/market/strategy_types.py:HORIZONS` — code is authoritative when the
README's tables lag), and posts trade-plan alerts with charts. It tracks
everything as **paper trades only** — it never places orders. Python 3.11+,
discord.py, pandas/numpy, yfinance, mplfinance, pytest. JSON persistence under
`data/`; no database.

Two entry points: `python bot.py` (the bot) and `python admin_ui.py` (the
admin). The admin is a Flask **API** plus an Angular SPA served from
`frontend/` — the Jinja UI it used to render was deleted on 2026-08-14
(Release B). Flask now serves only `/api/v1/*`, the SPA's routes and `/`;
the SPA is built by a Node stage in the Dockerfile, so a deploy needs it. Deployed as two Docker containers off one image (`docs/DOCKER.md`,
`docs/DEPLOY_HETZNER.md`); `.env` is the single config source, hot-reloaded via
SIGHUP (schema lives in `swingbot/config.py` — every setting is one `Field`
entry that feeds both the env parser and the admin UI's Settings page).

## Token discipline (read first — this repo has context landmines)

- **NEVER read a plan file whole** — `cockpit-v3.md` is 662 KB, `edge-engine-v4.md`
  358 KB. Pull one task instead: `/task-brief E53` or
  `grep -n "^### Task E53" -A 120 <plan>`. `gatekeeper-v6` exists only as
  `_0-index.md` + `_1..._11` parts (the 822 KB monolith was deleted; recover it
  from git history if needed). `grep -c "^### Task"` / `grep -n "^# Phase"` to orient.
  All three now live under `docs/superpowers/plans/implemented/`.
- **Grep respects the root `.ignore` file (hides `.claude/worktrees/`,
  `market_data/`, `data/`, `logs/`); Glob does not.** Always scope Glob by hand
  (`Glob("swingbot/**/*.py")`, never `**/*.py`) or it returns hundreds of
  worktree-copy matches. For symbol lookups prefer `git grep -n "def foo"`
  (tracked files only, can't see worktrees). Never edit files under
  `.claude/worktrees/` from a main-tree session.
- **README.md is now a 97-line overview + documentation index** (the v27 repo
  restructure split the old 645-line file into `docs/strategy.md` (how the bot
  decides), `docs/setup.md` (creating/configuring/running the bot),
  `docs/commands.md` (Discord command reference), and `docs/features.md` (Plan
  Engine v2, analytics, admin cockpit, growth playbook)) — read the one file
  that covers what you need, not README.md itself. Same for
  `.superpowers/sdd/progress.md`: `tail` it, never `cat` it.
- **`swingbot/core/` is ten packages, no flat modules.** Six from the v27
  restructure — `marketdata/`, `market/`, `planning/`, `backtesting/`,
  `tracking/`, `infra/` — plus the four that predate it — `edge/`,
  `scanning/`, `analytics/`, `charts/`. See `docs/claude/architecture.md` for
  which modules live where.
- **Don't re-run the full suite to check a local change** — use
  `python scripts/dev/testrun.py file tests/test_edge_gates.py` (~7s) or
  `... fast` (~27s, skips the render-heavy tier), and save `... full` for the
  pre-commit gate. Always go through the wrapper: it prints a one-line verdict
  instead of ~1150 progress lines. Better still for a full run, dispatch the
  `test-runner` subagent so none of it reaches this context.
- Hand wide/exploratory searches to the `Explore` agent so raw grep output
  never lands in this context.

**Current status is not tracked here** (it drifts stale). The `SessionStart`
hook (`.claude/hooks/session-cursor.ps1`) prints it every session: active plan
+ task count, last/next task, git HEAD and dirty files, live worktrees, and any
in-progress multi-hour backtest. **The live plans are whatever sits at the top
level of `docs/superpowers/plans/`** — everything closed, abandoned or rolled
back has moved to `plans/implemented/` (see "Naming specs and plans"), so that
listing is the status, not a paragraph here.

**Don't trust the hook's "NEXT" task ID blind** — it can name IDs (e.g. `E89`)
that don't exist in the plan file it labels as active (which may use a
different prefix, e.g. `U34`). Verify with `grep -n "^### Task" <plan>` before
chasing a task the hook mentioned.

**Repo tooling (`.claude/`):** `/task-brief <id>` extracts one plan task and
preflights this repo's documented traps. `/gate` is the pre-commit verification
gate (knows the one permitted pre-existing failure). Subagents:
`backtest-runner` (multi-hour jobs in an isolated context, returns only
verdicts), `symbol-verifier` (`git grep` existence checks for symbols a plan
names), `test-runner` (runs the suite via `scripts/dev/testrun.py` and returns
only the verdict, so ~1150 progress lines stay out of your context).
`.mcp.json` provides context7 for yfinance/pandas-ta/discord.py docs.

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

**Green means `0 failed`, and now also `0 xfailed`.** Reference baseline:
`1686 passed, 66 skipped, 0 failed`. A *changed* count is not a failure — only
`failed` is. A new `xfailed` is, and it is never the old quarantine coming back.

Why the count fell from 1898 (correctly), why the last `xfail` was a permanent
failure rather than a flake, and why timings swing 40s–262s with machine load:
`docs/claude/testing-cost.md`.

Long backtest/grid runs: a full 75-ticker × 10-horizon sweep takes tens of
minutes (`replay_scenarios` is ~30s per ticker-horizon — hours for a full
grid; never run it casually). Chunk long grids per-strategy.

**Any script meant to run in the background for more than a couple of minutes
must print one flushed line per unit of work** (fold/ticker/chunk), not just a
final summary. Confirm it does — or add the `print(..., flush=True)` — *before*
kicking it off, not hours into an unmonitorable run. The run this rule cost us
is in `docs/claude/working-conventions.md`.

## Naming specs and plans

**`docs/superpowers/{specs,plans}/YYYY-MM-DD-vN-<document-name>.md`** — date,
then version, then name. `vN` is one repo-wide counter shared by both
directories; never reuse a number and never renumber a committed one. A document
split across files reuses the parent's number with a `_N` suffix. Next number:

```bash
find docs/superpowers/specs docs/superpowers/plans -name '*.md' \
  | grep -oE 'v[0-9]+' | sort -V | tail -1
```

`find`, not `ls` on the two directories — closed documents live one level down
in `implemented/`, and missing them returns a stale maximum.

**When a plan stops being live work, `git mv` it — and every spec it was built
from — into `implemented/` as part of the closing commit**, so the top level of
`plans/` and `specs/` is exactly the live work. `implemented/` means "off the
live list", not "every box is ticked": it deliberately holds finished, abandoned
and rolled-back plans alike, so read a moved plan's Progress block before
assuming its code ships. Derive "done" from deliverables and merge commits — the
`[x]` boxes lie in both directions.

**A worktree executing a plan takes that plan's file stem** as both its
directory and its branch name.

`docs/claude/document-conventions.md` has the rest: when a spec may move (and why
one feeding live plans may not), the references to re-point in the same commit,
and why the `SessionStart` hook stops seeing a moved plan.

## Never delete a branch whose name contains "backup"

**Hard rule, no exceptions, no "but it looks merged":** any branch with
`backup` in its name is off limits to every destructive git command —
`branch -d`, `branch -D`, `push --delete`, and pruning that would remove it.
Ask the human partner; do not decide.

The same care applies to `stable-*` branches. They are rollback points, not
topic branches, and "already merged" is not what they are for.

**"Merged" is the wrong test for deletable, and this repo proves it.**
`backup-main` and `origin/cleanup-gate-fixtures` are the same commit
(`496caa1`) and carry **242 commits that are not on `main`** — the entire
gatekeeper-v7 line, built to 86/90 and then rolled back by `c84924a`. `main`
deliberately does not contain them. Deleting either branch destroys the only
copy. A related near-miss is already on record: local `main` was once 135
commits behind `origin/main`, where a force push would have destroyed them.

Before ANY branch deletion, run this and read it:

```bash
git rev-list --count main..<branch>    # commits that would be lost
```

Non-zero means stop. Zero means it is *merged*, which makes deletion safe
only for a topic branch you created for this task — never for a `backup*` or
`stable-*` branch, whose whole purpose is to hold a state `main` moved past.

## Reference docs

Not auto-loaded — read the relevant one before starting work in that area.

- `docs/claude/architecture.md` — core/commands/admin split, edge-engine
  module map, entry-signal single source, NO-LOOKAHEAD rule, Plan Engine v2,
  badges/registry, scan pipeline. Read before touching `swingbot/core`,
  `plan_engine`, or the scan pipeline.
- `docs/claude/known-traps.md` — the two parallel OHLCV caches, legacy shims,
  silent sizing/wiring no-ops, scan-loop ordering, symbol names plans get
  wrong, and **empty tables that are measured answers rather than stubs**. Read
  before touching data caching, `scan_engine`/`scan_embeds`, or `embeds.py` —
  and before "finishing" any empty config table or default-off flag.
- `docs/claude/backtest-methodology.md` — TRAIN/VALIDATION windows, acceptance
  gates, frozen constants, and the table of **closed pre-registrations that
  must not be re-run**. Read before running or interpreting any
  backtest/grid/validation.
- `docs/claude/working-conventions.md` (6 KB) — commit style, concurrent-session
  git hygiene, worktrees, and **when to bump `VERSION.json`** (two independent
  `ui`/`bot` lines; the test is observable difference, not diff size — Release B
  deleted the entire Jinja UI for a *patch*). Read before bumping a version.
- `docs/claude/document-conventions.md` (13 KB) — everything about authoring a
  spec or plan: filenames and the `vN` counter, the `implemented/` rule, and the
  three that bind every new document — a **`Bump:`** header line predicting the
  release level the work earns; a **`## Parallelisation`** section naming which
  tasks may run concurrently and what forces the rest sequential (the test is
  disjoint *files* plus no contract dependency — this working tree is shared, so
  two agents on one file overwrite rather than merge); and a **length budget**,
  a spec under 500 lines because it is read whole, a plan split into `_N` parts
  past 30 tasks or 120 KB. Over budget, **split, never compress**: cost per task
  is a near-constant 2.7–5.7 KB in every plan here, so the landmines are long,
  not verbose, and thinning a task just recreates the placeholders
  `writing-plans` forbids. Read before writing any spec or plan.
- `docs/claude/skills-tools.md` — which Superpowers skill or subagent to reach
  for on a given kind of task in this repo.
- `docs/claude/testing-cost.md` — measured suite timings, why `-n 4` beats
  `-n auto`, the two traps that make test timings unreliable, and what a changed
  pass count does and doesn't mean. Read before optimising or timing tests, and
  before reacting to a count that moved.
