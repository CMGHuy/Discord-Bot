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

Two entry points: `python bot.py` (the bot) and `python admin_ui.py` (Flask
admin UI). Deployed as two Docker containers off one image (`DOCKER.md`,
`DEPLOY_HETZNER.md`); `.env` is the single config source, hot-reloaded via
SIGHUP (schema lives in `swingbot/config.py` — every setting is one `Field`
entry that feeds both the env parser and the admin UI's Settings page).

## Token discipline (read first — this repo has context landmines)

- **NEVER read a plan file whole.** They are the largest files here by far:
  `cockpit-v3.md` 662 KB, `edge-engine-v4.md` 358 KB. Pull one task instead:
  `/task-brief E53`, or `grep -n "^### Task E53" -A 120 <plan>`. `gatekeeper-v6`
  exists ONLY as `_0-index.md` + `_1..._11` (the 822 KB monolith was deleted
  2026-07-26 — the parts are a verified content superset; recover it from git
  history if ever needed). Use `grep -c "^### Task"` / `grep -n "^# Phase"` to orient.
- **Grep is fixed by the root `.ignore` file; Glob is NOT.** `.ignore` hides
  `.claude/worktrees/` (3 full repo copies), `market_data/`, `data/`, `logs/` and
  the SDD diffs from ripgrep — an unscoped `Grep("def sector_heat")` at repo root
  used to **time out at 20 s returning nothing** and now answers instantly.
  **Glob does not honour `.ignore`**: `Glob("**/*.py")` still returns 500 matches
  (truncated at 100) for 232 real project files, ~70% of them worktree copies.
  So still scope Glob by hand — `Glob("swingbot/**/*.py")`, never `**/*.py`.
  For symbol lookups prefer `git grep -n "def foo"`: tracked files only, ~1 s, and
  it cannot see the worktrees at all. Never edit files under `.claude/worktrees/`
  from a main-tree session.
- **README.md is 645 lines** — grep its `^## ` headers and read the one
  section you need. Same for `.superpowers/sdd/progress.md`: `tail` it, never
  `cat` it (one entry per completed task, hundreds of lines each).
- **Don't re-run the full suite to check a local change** — it takes ~3
  minutes. Run the touched file (`pytest tests/test_edge_gates.py -q`), and
  save the full suite for the pre-commit gate.
- Hand wide/exploratory searches to the `Explore` agent or a subagent so the
  raw grep output never lands in this context.

**Where things stand:** deliberately not written down here. This paragraph used to
name the active task and drifted 25 tasks stale (it claimed ~E22–E27 while E50 was
already committed), which is worse than no information. The
`SessionStart` hook `.claude/hooks/session-cursor.ps1` now prints the derived
cursor at every session start: plan file + task count, the ledger's last completed
task and the next one, `git` HEAD and dirty files, live worktrees, and a warning if
another session's multi-hour backtest is running. Derived state cannot go stale.

Active plan is whichever plan file the hook names. Completed plan lines:
unified-plan-engine-v2, strategy-winrate-redesign. Also on disk but not the current
focus: cockpit-v3, gatekeeper-v6, llm-advisor-v5, admin-ui-tradingview-redesign-v7.

**Repo tooling (`.claude/`):** `/task-brief <id>` extracts one plan task and runs a
preflight for this repo's documented traps (fabricated symbols, the
`commands/scanning.py` wiring no-op, cache mix-ups). `/gate` is the pre-commit
verification gate and knows the one permitted pre-existing failure. Subagents:
`backtest-runner` (runs multi-hour jobs in an isolated context, returns only gate
verdicts) and `symbol-verifier` (cheap `git grep` existence checks on symbols a plan
names). `.mcp.json` provides context7 for version-correct yfinance / pandas-ta /
discord.py docs.

## Commands

```bash
python -m pytest tests/ -q                 # full suite, ~3min — pre-commit gate (see known failure below)
python -m pytest tests/test_foo.py::test_bar -v   # single test — use this while iterating
make check                                 # py_compile syntax pass (no make on Windows: run python -m py_compile over bot.py admin_ui.py swingbot/**/*.py)
python scripts/fetch_backtest_data.py      # populate the CSV cache (once, network) — required by every backtest/grid script
python scripts/run_backtest_range.py --train|--validation [--exit-model v2 --scale-out] [--strategy "RSI"] [--json out.json]
python scripts/tune_strategy.py --strategy "RSI" --grid key=v1,v2 --exit-model v2 --scale-out   # TRAIN-only grid
python scripts/shadow_parity_report.py     # v2-vs-legacy comparison from data/shadow_plans.jsonl
make up / make logs / make restart         # docker compose lifecycle
```

**Known-good baseline (verified 2026-07-25, commit `a7d23ab`):**
`841 passed, 54 skipped, 1 failed` in ~3m13s. The one failure is
`tests/test_trade_monitor_wiring.py::test_flag_on_polls_open_plans`
(`cancelled_expired` != `filled`) — a **pre-existing, expiry/wall-clock
dependent** failure carried in the ledger since Task E7. Do **not** treat it
as a regression you caused and do not "fix" it as a side quest. "Green" for
the commit gate means *this* baseline: your diff adds no new failure. If you
see a different count or a second failure, that one is yours. Note the sibling
`test_pending_fills_when_price_crosses_trigger` passes on the same fixture —
the difference is `run_manager_tick()` going through real dates.

Long backtest/grid runs: a full 75-ticker × 10-horizon sweep takes tens of
minutes (`replay_scenarios` in `backtest_scenarios.py` is ~30s per
ticker-horizon — hours; never run it casually). Background jobs killed
mid-run have happened before; chunk long grids per-strategy.

## Architecture

- `swingbot/core/` is business logic with **no Discord dependency**;
  `swingbot/commands/` is the Discord command layer; `swingbot/admin/` is the
  Flask UI. `bot_core.py` owns the shared bot instance and hot-reload handler.
  99 modules total; the subpackages are `core/edge/`, `core/scanning/`,
  `core/analytics/`, and `core/charts/`.
- **`swingbot/core/edge/` is the current active work area** (edge-engine-v4).
  Growth/risk math, mostly pure functions: `sizing.py` (fractional-Kelly, vol
  targeting), `heat.py` (portfolio heat cap), `correlation.py` (cluster
  exposure), `ruin.py` (Monte Carlo), `growth.py` (log-scale growth path),
  `regime2.py` (4-state classifier), `factors.py` (RS percentile, sector RS),
  `gates.py` (gap model, earnings blackout), `frictions.py` (slippage +
  commission). Many of these ship **deliberately unwired** — landed as tested
  pure functions, wired into the scan path in a later task. Before "fixing" a
  seemingly-dead edge function, grep the plan for its wiring task.
- **Entry signals have a single source:** `swingbot/core/entry_filters.py` is
  consumed by BOTH the backtest (`backtest._vectorized_entries`) and the live
  scanner (`signals.py`). Change a filter there and both worlds change
  together — that is the point. Per-strategy tunables live in its
  `DEFAULT_PARAMS`; direction/horizon restrictions in
  `strategy_types.STRATEGY_GATES`.
- **NO-LOOKAHEAD RULE (law):** entry conditions may reference only the current
  bar and earlier (`shift(+n)`, trailing rolling windows). Every boolean gate
  is `.fillna(False)` — a gate that cannot be computed yet blocks entries,
  never passes. New gates need a truncation test (`full.iloc[:-1] == trunc`).
- **Plan Engine v2** (`swingbot/core/plan_engine.py`): `TradePlanV2` with
  lifecycle `PENDING → ACTIVE → PARTIAL → CLOSED/CANCELLED`, per-strategy
  sizing builders, and the exit simulator (TP1 = win; scale-out banks 50% at
  TP1, stop to break-even, runner rides to TP2 with a chandelier ATR trail).
  `backtest.py run_backtest(..., exit_model="v2", scale_out=True)` uses the
  same simulator, so live behavior equals backtested behavior by construction.
  `plan_manager.py` + `plan_store.py` drive the live lifecycle from the 60s
  monitor; `backtest_scenarios.py` replays the confluence scan historically.
- **Badges/registry:** `swingbot/core/validation_registry.json` (loader:
  `registry.py`) stamps every v2 plan ✅ VALIDATED or ⚠️ WEAK with real
  out-of-sample stats. It is regenerated ONLY via
  `run_backtest_range.py --emit-registry` (or `--from-json` replay of a saved
  run) — never hand-edited. WEAK strategies are **never suppressed**; they
  emit plans with a caution block (user requirement).
- **Scan pipeline:** `swingbot/core/scanning/engine.py` (crawl → analyze →
  dedup → alert) and `scanning/embeds.py` (pure presentation).
  `plan_numbers_for_display()` in embeds.py is THE cutover switch deciding
  whether alerts show legacy scenario numbers or v2 plan numbers — route any
  new consumer of plan prices through it. Rollout flags (`PLAN_ENGINE_V2`
  off/shadow/on, `SCALE_OUT_ENABLED`, `INTRADAY_MANAGER_V2`) are documented in
  the README; `shadow` mode logs to `data/shadow_plans.jsonl` via `shadow_log.py`.
- Tests build OHLCV frames with `tests/conftest.py:make_ohlcv` /
  `make_trend_df` (columns `Open,High,Low,Close,Volume`, business-day
  DatetimeIndex) and `tests/helpers.py`. Read conftest before writing new
  entry/exit tests. Synthetic fixtures for entry filters usually need
  REPL-tuning until the ungated function actually fires — freeze the shape in
  the test with a comment once it does.

## Known traps (each of these has already cost a session)

- **Two parallel OHLCV cache subsystems — do not conflate them.**
  `backtest_cache.py` → `data/backtest_cache/` (flat `TICKER.csv`, daily only,
  ~77 tickers, what every existing backtest/grid script reads). `data_store.py`
  → `market_data/` (grouped by candle timeframe: `{timeframe}/{TICKER}.csv`,
  e.g. `market_data/daily/AAPL.csv`, ~521 daily + 78 hourly, what the
  edge-engine tasks depend on). Both are gitignored. Check which one a script
  reads before pointing it at a path.
- **`market_data/` is timeframe-first, not ticker-first.** Folders are the
  semantic names in `data_store.TIMEFRAMES` (`monthly`, `weekly`, `daily`,
  `hourly`, `15min`, …); filenames are sanitized (`GC=F` → `GC_F.csv`, same
  scheme as `backtest_cache`). Every accessor takes EITHER the semantic name
  or the yfinance code — `load_from_disk(t, "1h")` and
  `load_from_disk(t, "hourly")` resolve to the same file. Go through
  `cache_path()`/`load_from_disk()`; never hand-build the path.
- **The bot self-refreshes this cache while running** (`core/data_refresh.py`,
  driven by the `market_data_refresh` task loop in `commands/scanning.py`).
  Incremental and staleness-gated per timeframe (hourly 4h, daily 12h,
  weekly/monthly 24h), so most wake-ups cost no network. Flags:
  `MARKET_DATA_AUTO_REFRESH`, `MARKET_DATA_REFRESH_MINUTES`,
  `MARKET_DATA_TIMEFRAMES`.
- **Yahoo's intraday depth is a hard ceiling, not a tuning knob.** 1h serves
  ~730 *trading* days (~3 calendar years, measured); 15m/30m/5m only ~60 days;
  1m ~30 days. "Since IPO" hourly data does not exist from this source at any
  tier — only daily and coarser reach the listing date. Do not write a task
  that assumes otherwise.
- **Legacy shims that are not the real module.** `core/scan_engine.py` and
  `core/scan_embeds.py` are `import *` shims over `core/scanning/engine.py`
  and `core/scanning/embeds.py`. `core/trade_plan.py` is a deprecated adapter
  over `plan_engine.build_strategy_plan`. Edit the real module.
- **Sizing and embed-building happen in `core/scanning/engine.py`'s
  alert-building loop**, right before `build_embed()` — *not* in
  `commands/scanning.py::_send_alerts`, which only posts already-built
  tuples. Wiring sizing there is a silent no-op.
- **Add embed fields through the `sections["headline"]` accumulator** in
  `embeds.py`, never a raw `embed.add_field()` — the latter breaks
  `embed_theme.SECTION_ORDER`.
- **Scan-loop ordering invariant:** ticker screens (liquidity, data quality)
  go *after* `update_open_trades`/`_check_near_close` and *before* the
  new-signal horizon loop, so an already-open paper trade keeps being
  monitored for SL/TP even on a day its ticker fails the screen.
- **Function names that don't exist** (plans and briefs guess wrong at these
  constantly — verify before use): there is no `market_events.days_to_earnings`
  (use `events.get_next_earnings_date` / `earnings_within_window`), no
  `jsonio.write_json` (use `atomic_write_json`), no `TradeLog().all_trades()`
  (use `get_trades(limit=None)`). **A plan file is a design document, not
  ground truth about the current code** — grep the symbol before you call it.
- Scans run through `map_tickers()` (`SCAN_WORKERS`, default 4). Anything
  touching shared state (`state.confirm_or_update`, funnel counters) must stay
  serial/post-join.

## Backtest methodology (non-negotiable)

- **Windows:** TRAIN = 2020-01-01..2023-12-31, VALIDATION = 2024-01-01..2025-12-31.
  Tune on TRAIN only. Validation is a **budget**: one pre-registered run per
  component, results recorded as-is, never retuned after — a config that fails
  train never gets a validation shot. Treat the 2024–2025 window as tainted
  for any selection decision.
- **Acceptance gates:** `win_rate >= 80`, `expectancy_r > 0`, `N >= 30`
  (train) / `N >= 15` (validation), scratches+timeouts ≤ 50% of closed trades.
  Win = TP1 touched; win_rate over win+loss only; expectancy over all closed
  trades; same-bar conservative ordering (stop before target).
- Frozen constants: `STRATEGY_RR_OVERRIDE` + the 0.30 R:R floor,
  `BREAKEVEN_TRIGGER_FRACTION = 0.5`, `tp1_fraction = 0.50`.
- **No ML in the live path** — numpy/logistic audits live in `scripts/` only,
  never imported by `swingbot/`.
- Grid/validation results are written to `docs/superpowers/results/*.md` with
  the full table, the pre-registered selection rule quoted, and an honest
  observations section (failures are recorded, not fixed).

## Working conventions

- Conventional commits (`feat:`, `fix:`, `test:`, `docs:`, `refactor:`), one
  commit per task; full suite + `make check` green before each.
- Active plans live in `docs/superpowers/plans/*.md` with a Progress block at
  the top; the per-task execution ledger is `.superpowers/sdd/progress.md`
  (gitignored). Update both when completing plan tasks — past sessions have
  drifted (tasks marked done that weren't); verify against `git log` and
  actual files before trusting either.
- **Concurrent Claude sessions share this working tree.** Stage specific
  files, never `git add -A`; commit generated artifacts (especially the
  registry) immediately — uncommitted generated state has been silently wiped
  by another session's git operations before.
- Live git worktrees under `.claude/worktrees/` (currently `cockpit-v3` and an
  agent worktree) are full repo copies. Check `git worktree list` before
  assuming a stray path is dead. Never edit files there from a main-tree
  session — you will be editing a different branch.

## Skills and tools for this repo

- `superpowers:subagent-driven-development` — the plans in
  `docs/superpowers/plans/` are written for it (`### Task E42` + checkboxes).
  This is the default loop for plan execution; its `task-brief` and
  `review-package` scripts are what keep giant plans out of context.
- `superpowers:test-driven-development` — matches how entry filters get built
  here (fixture first, REPL-tune until the ungated function fires, freeze).
- `superpowers:systematic-debugging` — before any "fix" to a backtest number
  or a failing gate; guessing at these is expensive.
- `superpowers:verification-before-completion` — this repo has a documented
  history of tasks marked done that weren't. Verify against `git log` and the
  actual files.
- `superpowers:brainstorming` then `superpowers:writing-plans` for new
  components, so the result matches the existing plan format.
- `Explore` subagent for wide code searches; `feature-dev:code-reviewer` or
  `/code-review` for review passes.
- Skip `frontend-design`/`dataviz` conventions for the admin UI unless asked —
  it follows the existing TradingView-style theme.
