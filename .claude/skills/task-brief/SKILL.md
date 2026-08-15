---
name: task-brief
description: Extract one plan task into an execution brief with this repo's known traps pre-corrected. Use when starting a numbered plan task (E53, G134, C43...).
disable-model-invocation: true
---

# Task brief with trap preflight

Plan files here are 358-822 KB design documents. **A plan file is not ground truth
about the current code.** Briefs generated from them have shipped the same wrong
assumptions in E7, E8, E17, E18, E30, E35, E45, E46, E48 and E49 — every one caught
by hand before dispatch. This skill does that pass mechanically.

## Step 1 — Locate the plan and the task

Default plan is the most recently modified non-split file in
`docs/superpowers/plans/`. The task id comes from the argument (`/task-brief E53`);
with no argument, derive it from the ledger:

```powershell
Get-Content .superpowers/sdd/progress.md -Tail 1   # "Task E52: complete ..." -> next is E53
```

Never `cat` progress.md (173 KB) or read a plan whole.

## Step 2 — Extract the task section only

Find the superpowers `task-brief` script (profile and version vary — glob, don't
hardcode; 43 stale version-pinned permission entries came from hardcoding it):

```powershell
$s = Get-ChildItem "E:/Claude/claude-config/*/plugins/cache/claude-plugins-official/superpowers/*/skills/subagent-driven-development/scripts/task-brief" |
     Sort-Object FullName -Descending | Select-Object -First 1
bash $s.FullName docs/superpowers/plans/<plan>.md <N>
```

If the script is unavailable, extract directly:

```powershell
$f='docs/superpowers/plans/implemented/2026-07-11-v4-edge-engine.md'
$start=(Select-String -Path $f -Pattern '^### Task E53\b').LineNumber
Get-Content $f | Select-Object -Skip ($start-1) -First 140
```

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

## Step 5 — Emit the brief

Task id and title, files to create/modify (corrected paths), interfaces, the TDD
steps verbatim from the plan, then a **Preflight** section listing every 3a-3h
result with the corrections made. Flag anything you could not verify rather than
guessing.
