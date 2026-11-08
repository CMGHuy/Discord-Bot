---
name: task-brief
description: "Fill one task's handoff file with this repo's known traps pre-corrected and bounded code excerpts (/task-brief <handoff path>); for a task without a handoff, extract it into a pasted brief instead (/task-brief <id>). Use when starting a numbered plan task (E53, G134, V199-5...). Run as /task-brief, or by Claude itself right after task_handoff.py writes a handoff."
---
<!-- GENERATED from .claude/skills/task-brief/SKILL.md by scripts/dev/sync_codex.py -- edit the source, then re-run the script. Never edit this copy. -->

# Task brief with trap preflight

**A plan file is not ground truth about the current code.** It was written
against an older tree, and briefs built from plans have shipped wrong module
paths, invented symbols and wiring that was a silent no-op — every one caught
by hand before dispatch. This skill does that pass mechanically, and writes it
into the task's handoff file.

## Step 1 — Read the handoff

`/task-brief <handoff path>` is the normal call. The controller has just run
`python scripts/dev/task_handoff.py <plan file> <id> --worktree <wt> --attribution "<line>"`,
which printed that path as its last line
(`.superpowers/sdd/<plan base>/task-<id>-handoff.md` under the main checkout).
Read the handoff whole. Its `## Task` section is the plan task verbatim and
its `## Environment` names the worktree; every check below runs in that
worktree. Never open the plan file. If either slot marker is already gone,
the handoff has been filled: stop and say so.

`/task-brief <id>` without a handoff is the fallback for a task the script
refused (`no deliverables derivable for <id>`). Pull the task with an exact
heading match across the plan's files (`_0-index.md` and every `_<n>-*.md`
part), never the whole plan:

```bash
grep -n "^### Task <id>:" docs/superpowers/plans/<plan base>*.md
grep -n "^### Task <id>:" -A 140 <the one file that matched>
```

An id found in no file, or in two, is a stop, not a guess. Never `cat`
`.superpowers/sdd/progress.md` (173 KB); `tail` it if you need the last task.

## Step 2 — Gather the code excerpts

For every symbol and file the task names, take a bounded excerpt: the
signature plus the lines the task changes, with line numbers
(`git -C <wt> grep -n`, then that line range). Where a `plan-briefer` brief
exists (`.superpowers/briefs/<plan base>.md`), take the excerpts from it and
re-check each against the worktree (same lines, same text) instead of
re-deriving them; a mismatch becomes a CORRECTED Preflight entry carrying
the current lines.

Budget for **Code**: about 12 KB in total. Above that, replace the largest
bodies with `path:line-range — <what it is>` pointers until it fits.

## Step 3 — Trap preflight (the point of this skill)

Run every check. Report each as CONFIRMED / CORRECTED / NA in the brief.

**3a. Every symbol the brief names must exist.** Plans guess wrong constantly:

```bash
git grep -n "def <symbol>" -- "swingbot/**/*.py"
```

`git grep` not Grep: it walks tracked files only, so it finishes in ~900 ms where
an unscoped ripgrep at repo root times out. Known non-existent symbols plans keep
inventing:

| Plan says | Reality |
|---|---|
| `market_events.days_to_earnings` | `events.get_next_earnings_date` / `earnings_within_window` in `swingbot/core/market/events.py` |

**3b. Wiring target.** If the task wires sizing, embeds or alert fields, the brief
will likely name the posting package `swingbot/commands/scanning/` (`alerts.py`,
`loops.py`). **That is a silent no-op** — it only posts and re-renders alerts
that are already built. Sizing and embed-building happen in the alert loops,
right before `build_embed()`: `swingbot/core/scanning/scan_run.py` (long scan),
`swingbot/core/scanning/short_run.py` (shorts) and
`swingbot/core/scanning/outlook_run.py` (outlook). `build_embed` itself lives in
`swingbot/core/scanning/alert_embeds.py`. Find today's call sites with
`git grep -n "build_embed(" -- swingbot/core/scanning` rather than trusting a
line number. Correct the brief before dispatch and say so.

**3c. Embed fields** go through the `sections["headline"]` accumulator in
`swingbot/core/scanning/alert_embeds.py`, never a raw `embed.add_field()`
(breaks `SECTION_ORDER`).

**3d. Which OHLCV cache?** Two unrelated subsystems:
`backtest_cache.py` -> `data/backtest_cache/` (flat `TICKER.csv`, daily only, ~77
tickers, what backtest/grid scripts read) vs `data_store.py` -> `market_data/`,
which is **timeframe-first, not ticker-first**: `{timeframe}/{TICKER}.csv`, e.g.
`market_data/daily/AAPL.csv` (verified: 521 daily + 78 hourly). Folder names are the
semantic names in `data_store.TIMEFRAMES`; filenames are sanitized (`GC=F` ->
`GC_F.csv`). Accessors take either the semantic name or the yfinance code —
`load_from_disk(t, "1h")` and `load_from_disk(t, "hourly")` hit the same file. Go
through `cache_path()`/`load_from_disk()`; never hand-build the path.

Also: Yahoo's intraday depth is a hard ceiling — 1h serves ~730 trading days,
15m/30m/5m ~60 days, 1m ~30 days. If a task assumes deeper intraday history than
that, flag it rather than implementing it.

**3e. Real module, not a shim that no longer exists.** `core/scan_engine.py`,
`core/scan_embeds.py`, `core/confidence.py`, `core/regime.py` and
`core/trade_plan.py` were all removed 2026-08-15 by the v27 repo restructure.
A task naming one of those paths is naming a deleted shim — point it at the
real module instead (`core/scanning/engine.py`, `core/scanning/embeds.py`,
`planning/plan_engine.build_strategy_plan`).

**3f. Is it meant to be wired at all?** Many `core/edge/` functions ship
deliberately unwired, wired in a later task. Grep the plan for the wiring task
before treating an unused function as a bug.

**3g. Scan-loop ordering.** Ticker screens go *after* the open-trade monitor and
*before* the new-signal horizon loop, all inside `_scan_one` in
`swingbot/core/scanning/analyze.py`: first `io.monitor_scan` (live:
`_live_monitor_scan`, which runs `trade_log.update_open_trades` then
`_check_near_close`), then the screens (`universe.liquidity_reason`,
`universe.data_quality_issues`), then `for horizon_key in horizons_to_scan:`.
`swingbot/core/scanning/scan_run.py` only maps `_scan_one` over the tickers
(`fetch.map_tickers`); a screen placed there runs outside that order.

**3h. No-lookahead law.** New entry gates may reference only the current bar and
earlier, must be `.fillna(False)`, and need a truncation test
(`full.iloc[:-1] == trunc`).
**3i. Stores are Postgres-only.** Every store reads and writes Postgres; a task
that writes a JSON file under `data/` as a store writes to nothing the bot
reads. A shape change follows `docs/claude/schema-evolution.md` (the
`schema-change` skill). A task whose tests reach the database runs
`/replicate-prod-db` first, against the one shared `swing-db` container, never
a per-task container or database.

**3j. Test placement.** A new `tests/` directory joins exactly one suite in
`tests/suites.toml` in the same commit. A new data file a test reads gets a
`DATA_READERS` row in `scripts/dev/select_tests.py`. Pytest admin-login
fixtures never use the main-tree `.env` admin credentials: those override the
fixture's own and the login returns 401 (V177). A Playwright or local-instance
check still logs in with the `.env` values (root `CLAUDE.md`).

**3k. Short work never downgrades longs.** A SHORT-targeted task keeps long
plans byte-identical and pins that with a regression test (the same input gives
the same long plan before and after the change).

**3l. UI tasks are checked at three widths.** A task that changes a screen is
checked with Playwright at 390, 768 and 1440 px (`docs/claude/ui-design.md`),
never with claude-in-chrome.
## Step 4 — Check the tree is safe to work in

Concurrent sessions share this working tree.

```powershell
git log --oneline -3
git status --porcelain
Get-Process python -ErrorAction SilentlyContinue | Where-Object CPU -gt 300
```

From Git Bash (no `cd`; point `git -C` at the worktree):

```bash
git -C <wt> log --oneline -3
git -C <wt> status --porcelain
powershell -NoProfile -Command "Get-Process python -ErrorAction SilentlyContinue | Where-Object CPU -gt 300"
```

If HEAD moved since the session started, or a multi-hour python run is live, say so
in the brief and do not start a backtest.

## Step 5 — Fill the two slots

With a handoff, write exactly two things into it, with the Edit tool, each
marker line as the `old_string`:

- the line `<!-- task-brief: fill Preflight -->` becomes the Preflight: the
  task's `**Model:**` line check (plans above v145 — if it is missing, say
  so rather than guessing a tier), every 3a-3l result as CONFIRMED /
  CORRECTED / NA with the correction made, and the Step 4 tree check;
- the line `<!-- task-brief: fill Code -->` becomes the Code from Step 2,
  each excerpt headed by its `path:start-end`.

Change nothing else in the file: not `## Task`, not `## Deliverables`, not
`## Environment`. A correction to the task goes in Preflight, never into the
task text. Return one line: the handoff path, then
`Preflight: <n> CONFIRMED, <n> CORRECTED, <n> NA; Code: <size> KB`. Flag
anything you could not verify rather than guessing.

Without a handoff (`/task-brief <id>`), emit the brief instead: task id and
title, the `**Model:**` line verbatim, files to create/modify (corrected
paths), interfaces, the TDD steps verbatim from the plan, then the
Preflight and Code sections as above.
