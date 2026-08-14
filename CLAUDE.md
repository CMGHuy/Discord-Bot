# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A Discord swing-trade alert bot ("swingbot"): it scans a watchlist of stock/ETF
tickers through the trading session, looks for multi-method-confirmed
support/resistance setups across 10 swing horizons (`2w`…`9m`, defined in
`swingbot/core/strategy_types.py:HORIZONS` — code is authoritative when the
README's tables lag), and posts trade-plan alerts with charts. It tracks
everything as **paper trades only** — it never places orders. Python 3.11+,
discord.py, pandas/numpy, yfinance, mplfinance, pytest. JSON persistence under
`data/`; no database.

Two entry points: `python bot.py` (the bot) and `python admin_ui.py` (the
admin). The admin is a Flask **API** plus an Angular SPA served from
`frontend/` — the Jinja UI it used to render was deleted on 2026-08-14
(Release B). Flask now serves only `/api/v1/*`, the SPA's routes and `/`;
the SPA is built by a Node stage in the Dockerfile, so a deploy needs it. Deployed as two Docker containers off one image (`DOCKER.md`,
`DEPLOY_HETZNER.md`); `.env` is the single config source, hot-reloaded via
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
- **README.md is 645 lines** — grep its `^## ` headers and read the one section
  you need. Same for `.superpowers/sdd/progress.md`: `tail` it, never `cat` it.
- **Don't re-run the full suite to check a local change** — use
  `python scripts/testrun.py file tests/test_edge_gates.py` (~7s) or
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
names), `test-runner` (runs the suite via `scripts/testrun.py` and returns
only the verdict, so ~1150 progress lines stay out of your context).
`.mcp.json` provides context7 for yfinance/pandas-ta/discord.py docs.

## Commands

```bash
python scripts/testrun.py full             # full suite via -n 4 — the pre-commit gate; one-line verdict
python scripts/testrun.py fast             # ~27s, skips the slow tier; auto-escalates if charts/templates touched
python scripts/testrun.py file tests/test_foo.py  # one file (~7s) — use this while iterating
python -m pytest tests/test_foo.py::test_bar -v   # single test, raw pytest
make check                                 # py_compile syntax pass (no make on Windows: run python -m py_compile over bot.py admin_ui.py swingbot/**/*.py)
python scripts/fetch_backtest_data.py      # populate the CSV cache (once, network) — required by every backtest/grid script
python scripts/run_backtest_range.py --train|--validation [--exit-model v2 --scale-out] [--strategy "RSI"] [--json out.json]
python scripts/tune_strategy.py --strategy "RSI" --grid key=v1,v2 --exit-model v2 --scale-out   # TRAIN-only grid
python scripts/shadow_parity_report.py     # v2-vs-legacy comparison from data/shadow_plans.jsonl
make up / make logs / make restart         # docker compose lifecycle
```

**Green means `0 failed`, and now also `0 xfailed`.** Reference baseline:
`1686 passed, 66 skipped, 0 failed`.

**That count dropped from 1898 on 2026-08-14 and the drop is correct**, not
lost coverage: Release B deleted the Jinja UI, and with it the tests whose
subject was rendered HTML — 10 whole files plus 45 individually-removed tests
that asserted v1-against-Jinja parity or "the Jinja page still owns this URL".
Builder-level tests were kept untouched, which is what they were extracted
for. An unexplained drop from here is a different matter; investigate it. The pass count drifts up as tasks land
tests and concurrent sessions commit — a *changed count* is not a failure;
only `failed` is.

**The long-standing `xfail` quarantine is gone (2026-08-14).**
`test_flag_on_polls_open_plans` was quarantined as "wall-clock dependent",
which undersold it: the shared `_pending()` fixture is created at a fixed
`2026-07-11` with `expiry_bars=5`, while `_bars_since` counts real trading
days from a real data fetch. Once five trading days passed, the plan expired
before it could fill — so it was not failing intermittently, it was failing
**permanently and drifting further every day**, behind a `strict=False` that
could never become an `xpass`. Fixed by injecting `_bars_since` the same way
the test already injected `_price_fn`, plus a second test covering expiry
through the same path. If a new `xfailed` appears, it is new — investigate it
rather than assuming it is this one.

Timings move a lot with machine load (the same run has measured 40s idle and
262s under contention), and measuring them has its own traps —
`docs/claude/testing-cost.md` has the numbers and the method.

Long backtest/grid runs: a full 75-ticker × 10-horizon sweep takes tens of
minutes (`replay_scenarios` is ~30s per ticker-horizon — hours for a full
grid; never run it casually). Chunk long grids per-strategy.

**Any script meant to run in the background for more than a couple of
minutes must print incremental progress** (one flushed line per unit of
work — fold/ticker/chunk — not just a final summary once everything is
done). `scripts/wf_run.py --full` is the counterexample that cost a whole
monitoring session: it only prints the fold table after `run_folds()`
fully returns, so a multi-hour run gives zero signal beyond OS-level CPU
time until the very end. When writing or invoking a new long-running
script, either confirm it already logs per-unit progress, or add a
`print(..., flush=True)` (or `log.info`) per completed unit before
kicking it off — don't discover this gap hours into an unmonitorable run.

## Naming specs and plans

**`docs/superpowers/{specs,plans}/YYYY-MM-DD-vN-<document-name>.md`** — date,
then version, then name:

```
2026-08-08-v16-angular-migration.md          (plan)
2026-08-08-v15-jinja-cutover-design.md       (spec)
2026-07-14-v6-gatekeeper_0-index.md          (one document split into parts)
```

`vN` is one repo-wide counter shared by both directories — `v11` is the
eleventh design document in this repo, whether spec or plan. Next number:

```bash
find docs/superpowers/specs docs/superpowers/plans -name '*.md' \
  | grep -oE 'v[0-9]+' | sort -V | tail -1
```

Use `find`, not `ls` on the two directories — finished documents live one level
down in `implemented/` (below), and an `ls` that misses them returns a stale
maximum and makes you reuse a number.

Never reuse a number, and never renumber a committed one — commit messages and
cross-links reference it. Revising a document in place keeps its number; only a
genuinely new document takes the next. A document split across files reuses the
parent's number with a `_N` part suffix rather than consuming N numbers.

`docs/claude/working-conventions.md` has the reasoning and the history of the
2026-08-13 sweep that moved every file to this layout.

### Plans that are no longer live move to `implemented/`

**When a plan stops being live work, `git mv` it — and every spec it was built
from — into `docs/superpowers/plans/implemented/` and
`docs/superpowers/specs/implemented/` as part of the closing commit.** The top
level of those two directories then holds exactly the live work: what is in
flight, and what is designed but still to be built. Everything else is below.

- **`implemented/` means "off the live list", not "every box is ticked".** It
  holds three kinds of document, deliberately: plans that finished; plans
  abandoned part-way (`v3-cockpit` at 15/467, `v4-edge-engine` at 133/399); and
  plans whose code was later deleted by a rollback (`v6-gatekeeper`, undone by
  `c84924a`). Read a moved plan's Progress block before assuming its code ships
  today — the folder does not promise that.
- **A plan is done when its own work is done**, not when the checkboxes agree.
  A plan closing with tasks deliberately cut, deferred to a successor, or left
  open for manual QA is finished — say so in its Progress block, then move it.
  `[x]` boxes lie in both directions; derive the verdict from deliverables and
  merge commits, never from the boxes.
- **A spec moves only when nothing live still builds from it.** A spec feeding
  several plans stays put until the last of them closes — `v15-jinja-cutover`
  is the example: its plan (`v16-angular-migration`) is closed and moved, but
  the cutover itself was handed to a future plan, so the spec stayed.
- **Not every spec has a plan.** A multi-component design doc can be executed
  component-by-component with no plan file at all; it is closed when every
  component is resolved — and **"resolved" includes a negative result or a
  component correctly not built because its own gate never opened.**
  `v17-market-context` is the example: P0/P1 shipped, P2a closed on measured
  evidence with an *empty* `REGIME_ALLOW`, P2b was gated off by P2a's failure,
  P3's script shipped. It carries a status table in its header; write one
  before moving a spec like that, or the next session will read the empty
  table as unfinished work and re-run a closed pre-registration.
- **Fix the references in the same commit.** Plans, specs, source docstrings
  (`swingbot/core/analytics/*.py`, `swingbot/admin/**`), tests and
  `.claude/skills/task-brief/SKILL.md` all cite these paths; after moving,
  re-point every reference and confirm none dangle.
- **The `SessionStart` hook only globs `plans/*.md`**, so a moved plan drops out
  of the cursor's "active plan" line by design. To resume one, move it back up
  first.

### Worktrees are named after the plan

**A worktree created to execute a plan takes the plan's file stem**, so the
branch, the directory and the document always name the same thing:

```
docs/superpowers/plans/2026-08-13-v21-spa-refresh.md
  → .claude/worktrees/2026-08-13-v21-spa-refresh/   (branch: same name)
```

Never invent a fresh topic name — a worktree called `trade-history-filter`
takes a second lookup to tie back to plan v9. For work that is not executing a
plan, a short topic name is fine; the rule binds only when a plan exists.

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
- `docs/claude/working-conventions.md` — commit style, concurrent-session git
  hygiene, worktrees, the full document-naming convention, and **when to bump
  `VERSION.json`** (two independent `ui`/`bot` lines; the test is observable
  difference, not diff size — Release B deleted the entire Jinja UI for a
  *patch*). Read it before writing any new spec or plan, and before bumping a
  version.
- `docs/claude/skills-tools.md` — which Superpowers skill or subagent to reach
  for on a given kind of task in this repo.
- `docs/claude/testing-cost.md` — measured suite timings, why `-n 4` beats
  `-n auto`, and the two traps that make test timings unreliable. Read before
  optimising or timing tests.
