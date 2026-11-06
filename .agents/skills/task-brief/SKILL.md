---
name: task-brief
description: "Fill one task's handoff file with this repo's known traps pre-corrected and bounded code excerpts (/task-brief <handoff path>); for a task without a handoff, extract it into a pasted brief instead (/task-brief <id>). Use when starting a numbered plan task (E53, G134, V199-5...). Run as /task-brief, or by Claude itself right after task_handoff.py writes a handoff."
---
<!-- GENERATED from .claude/skills/task-brief/SKILL.md by scripts/dev/sync_codex.py -- edit the source, then re-run the script. Never edit this copy. -->

# Task brief with trap preflight

Plan files here are 358-822 KB design documents. **A plan file is not ground truth
about the current code.** Briefs generated from them have shipped the same wrong
assumptions in E7, E8, E17, E18, E30, E35, E45, E46, E48 and E49 — every one caught
by hand before dispatch. This skill does that pass mechanically, and writes it into the task's handoff file.

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

```powershell
git grep -n "def <symbol>" -- "swingbot/**/*.py"
```

`git grep` not Grep: it walks tracked files only, so it finishes in ~900 ms where
an unscoped ripgrep at repo root times out. Known non-existent symbols plans keep
inventing:

| Plan says | Reality |
|---|---|
| `market_events.days_to_earnings` | `events.get_next_earnings_date` / `earnings_within_window` |
| `jsonio.write_json` | `atomic_write_json` |
| `TradeLog().all_trades()` | `get_trades(limit=None)` |

**3b. Wiring target.** If the task wires sizing, embeds or alert fields, the brief
will likely say `swingbot/commands/scanning.py`. **That is a silent no-op** — that
module only posts already-built tuples. Sizing and embed-building happen in
`swingbot/core/scanning/engine.py`'s alert-building loop, right before
`build_embed()`. Correct the brief before dispatch and say so.

**3c. Embed fields** go through the `sections["headline"]` accumulator in
`scanning/embeds.py`, never a raw `embed.add_field()` (breaks `SECTION_ORDER`).

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

**3g. Scan-loop ordering.** Ticker screens go *after*
`update_open_trades`/`_check_near_close`, *before* the new-signal horizon loop.

**3h. No-lookahead law.** New entry gates may reference only the current bar and
earlier, must be `.fillna(False)`, and need a truncation test
(`full.iloc[:-1] == trunc`).

## Step 4 — Check the tree is safe to work in

Concurrent sessions share this working tree.

```powershell
git log --oneline -3
git status --porcelain
Get-Process python -ErrorAction SilentlyContinue | Where-Object CPU -gt 300
```

If HEAD moved since the session started, or a multi-hour python run is live, say so
in the brief and do not start a backtest.

## Step 5 — Fill the two slots

With a handoff, write exactly two things into it, with the Edit tool, each
marker line as the `old_string`:

- the line `<!-- task-brief: fill Preflight -->` becomes the Preflight: the
  task's `**Model:**` line check (plans above v145 — if it is missing, say
  so rather than guessing a tier), every 3a-3h result as CONFIRMED /
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
