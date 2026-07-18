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

## Commands

```bash
python -m pytest tests/ -q                 # full suite — must be green before every commit
python -m pytest tests/test_foo.py::test_bar -v   # single test
make check                                 # py_compile syntax pass (no make on Windows: run python -m py_compile over bot.py admin_ui.py swingbot/**/*.py)
python scripts/fetch_backtest_data.py      # populate the CSV cache (once, network) — required by every backtest/grid script
python scripts/run_backtest_range.py --train|--validation [--exit-model v2 --scale-out] [--strategy "RSI"] [--json out.json]
python scripts/tune_strategy.py --strategy "RSI" --grid key=v1,v2 --exit-model v2 --scale-out   # TRAIN-only grid
python scripts/shadow_parity_report.py     # v2-vs-legacy comparison from data/shadow_plans.jsonl
make up / make logs / make restart         # docker compose lifecycle
```

Long backtest/grid runs: a full 75-ticker × 10-horizon sweep takes tens of
minutes (`replay_scenarios` in `backtest_scenarios.py` is ~30s per
ticker-horizon — hours; never run it casually). Background jobs killed
mid-run have happened before; chunk long grids per-strategy.

## Architecture

- `swingbot/core/` is business logic with **no Discord dependency**;
  `swingbot/commands/` is the Discord command layer; `swingbot/admin/` is the
  Flask UI. `bot_core.py` owns the shared bot instance and hot-reload handler.
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
