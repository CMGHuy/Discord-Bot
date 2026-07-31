# Architecture

Referenced from the root `CLAUDE.md`. Read this before touching
`swingbot/core`, `plan_engine`, or the scanning pipeline.

- `swingbot/core/` is business logic with **no Discord dependency**;
  `swingbot/commands/` is the Discord command layer; `swingbot/admin/` is the
  Flask UI. `bot_core.py` owns the shared bot instance and hot-reload handler.
  Subpackages: `core/edge/`, `core/scanning/`, `core/analytics/`, `core/charts/`.
- **`swingbot/core/edge/`** (edge-engine-v4, current active work area) is
  growth/risk math, mostly pure functions: `sizing.py` (fractional-Kelly, vol
  targeting), `heat.py` (portfolio heat cap), `correlation.py` (cluster
  exposure), `ruin.py` (Monte Carlo), `growth.py` (log-scale growth path),
  `regime2.py` (4-state classifier), `factors.py` (RS percentile, sector RS),
  `gates.py` (gap model, earnings blackout), `frictions.py` (slippage +
  commission). Many ship **deliberately unwired** — tested pure functions
  landed ahead of the task that wires them into the scan path. Before "fixing"
  a seemingly-dead edge function, grep the plan for its wiring task.
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
  off/shadow/on, `INTRADAY_MANAGER_V2`) are documented in the README;
  `shadow` mode logs to `data/shadow_plans.jsonl` via `shadow_log.py`. Scale-out
  itself is hardcoded on in `plan_manager.py` whenever the intraday manager
  runs — `SCALE_OUT_ENABLED` used to advertise it as separately switchable but
  was never actually read, so it was deleted (plan v8 Task V4). With the
  manager on, `plan_manager` — not the legacy SL/TP loops in `performance.py`
  — owns the **target** side of a plan-linked trade
  (`performance.manager_owns_target()`); the stop side stays with them as a
  backstop. See `known-traps.md`: any new close path must consult it.
- Tests build OHLCV frames with `tests/conftest.py:make_ohlcv` /
  `make_trend_df` (columns `Open,High,Low,Close,Volume`, business-day
  DatetimeIndex) and `tests/helpers.py`. Read conftest before writing new
  entry/exit tests. Synthetic fixtures for entry filters usually need
  REPL-tuning until the ungated function actually fires — freeze the shape in
  the test with a comment once it does.
