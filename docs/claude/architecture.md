# Architecture

Referenced from the root `CLAUDE.md`. Read this before touching
`swingbot/core`, `plan_engine`, or the scanning pipeline.

- `swingbot/core/` is business logic with **no Discord dependency**;
  `swingbot/commands/` is the Discord command layer; `swingbot/admin/` is the
  Flask **API** (`admin/api_v1/`) plus the server side of the Angular SPA
  (`admin/spa.py`), whose source lives in `frontend/` and is built by a Node
  stage in the Dockerfile. The Jinja UI `admin/` used to render was deleted
  2026-08-14; `admin/queries.py` holds the read-side helpers the API kept
  using when `pages.py` went. `bot_core.py` owns the shared bot instance and
  hot-reload handler.
  `core/` is fully packaged (v27 repo restructure, 2026-08-15) — no flat
  `.py` modules remain under it, only ten subpackages: `core/marketdata/`
  (fetching and caching, both OHLCV caches together), `core/market/`
  (everything computed from bars — indicators, levels, strategies, entry
  filters), `core/planning/` (plan construction, lifecycle and sizing —
  `plan_engine.py`, `plan_manager.py`, `plan_store.py`), `core/backtesting/`
  (offline replay, walk-forward and the validation registry —
  `backtest.py`, `backtest_wf.py`, `backtest_scenarios.py`, `registry.py`,
  `shadow_log.py`), `core/tracking/` (the trade log's write path —
  `performance.py`, `retrospective.py`, `risk_metrics.py`), `core/infra/`
  (JSON, locks and delivery channels — `jsonio.py`, `state.py`,
  `notifier.py`, `silent_channel.py`), plus the four that predate the
  restructure: `core/edge/`, `core/scanning/`, `core/analytics/`,
  `core/charts/`, and `core/presentation/`. `presentation/` owns every
  Discord colour, glyph, number format and embed part: pure `tokens.py`,
  phone-safe `ansi.py`, then whole embed parts in `components.py`. Nothing
  outside it may touch `discord.Color`; its AST guard enforces that boundary.
- **`swingbot/core/edge/`** (edge-engine-v4, current active work area) is
  growth/risk math, mostly pure functions: `sizing.py` (fractional-Kelly, vol
  targeting), `heat.py` (portfolio heat cap), `correlation.py` (cluster
  exposure), `ruin.py` (Monte Carlo), `growth.py` (log-scale growth path),
  `regime2.py` (4-state classifier), `factors.py` (RS percentile, sector RS),
  `gates.py` (gap model, earnings blackout), `frictions.py` (slippage +
  commission). Many ship **deliberately unwired** — tested pure functions
  landed ahead of the task that wires them into the scan path. Before "fixing"
  a seemingly-dead edge function, grep the plan for its wiring task.
- **Entry signals have a single source:** `swingbot/core/market/entry_filters.py`
  is consumed by BOTH the backtest (`backtest._vectorized_entries`) and the
  live scanner (`signals.py`). Change a filter there and both worlds change
  together — that is the point. Per-strategy tunables live in its
  `DEFAULT_PARAMS`; direction/horizon restrictions in
  `strategy_types.STRATEGY_GATES`.
- **NO-LOOKAHEAD RULE (law):** entry conditions may reference only the current
  bar and earlier (`shift(+n)`, trailing rolling windows). Every boolean gate
  is `.fillna(False)` — a gate that cannot be computed yet blocks entries,
  never passes. New gates need a truncation test (`full.iloc[:-1] == trunc`).
- **Plan Engine v2** (`swingbot/core/planning/plan_engine.py`): `TradePlanV2`
  with lifecycle `PENDING → ACTIVE → PARTIAL → CLOSED/CANCELLED`, per-strategy
  sizing builders, and the exit simulator (TP1 = win; scale-out banks 50% at
  TP1, stop to break-even, runner rides to TP2 with a chandelier ATR trail).
  `swingbot/core/backtesting/backtest.py run_backtest(..., exit_model="v2",
  scale_out=True)` uses the same simulator, so live behavior equals
  backtested behavior. That is an **invariant this repo maintains, not one the code structure guarantees**: the live path polls a tape every 60s while the simulator walks daily bars, and v64 fixed extended-hours prints, sampled-tick stop fills, and same-session moved stops. Any new live-path exit rule must name the simulator line it matches.
  v70 then reopened exactly one capability outside those hours: `poll()` gates
  three ways (quiet window → nothing; regular → the full `_step()`; otherwise
  → `_step_extended()`), and the extended branch may only close a plan that
  has finished — a confirmed stop breach, or the last remaining target — after
  `EXTENDED_HOURS_DEBOUNCE_TICKS` consecutive polls agree. Break-even arming,
  TP1 partials, the chandelier ratchet and pending fills stay regular-hours
  only, so the simulator still has nothing to match outside 09:30–16:00 ET.
  `planning/plan_manager.py` +
  `planning/plan_store.py` drive the live lifecycle from the 60s monitor;
  `backtesting/backtest_scenarios.py` replays the confluence scan
  historically.
- **Badges/registry:** `swingbot/core/backtesting/validation_registry.json`
  (loader: `backtesting/registry.py`) stamps every v2 plan ✅ VALIDATED or
  ⚠️ WEAK with real out-of-sample stats. It is regenerated ONLY via
  `run_backtest_range.py --emit-registry` (or `--from-json` replay of a saved
  run) — never hand-edited. WEAK strategies are **never suppressed**; they
  emit plans with a caution block (user requirement).
- **Scan pipeline:** `swingbot/core/scanning/engine.py` (crawl → analyze →
  dedup → alert) and `scanning/embeds.py` (pure presentation).
  `plan_numbers_for_display()` in embeds.py is THE cutover switch deciding
  whether alerts show legacy scenario numbers or v2 plan numbers — route any
  new consumer of plan prices through it. Rollout flags (`PLAN_ENGINE_V2`
  off/shadow/on, `SCALE_OUT_ENABLED`, `INTRADAY_MANAGER_V2`) are documented in
  the README; `shadow` mode logs to `data/shadow_plans.jsonl` via
  `backtesting/shadow_log.py`.
- **Opex-day caution (v44):** `swingbot/core/market/opex.py` holds both the
  US options-expiration calendar (`opex_tier` -> `"monthly"`/`"weekly"`/None,
  stdlib only) and the policy built on it — effective confidence/confluence
  thresholds, the near-close suppression window, the ATR stop and position-size
  multipliers, and the embed badge. Behind `OPEX_CAUTION_ENABLED`, default off,
  and the flag is re-checked in `_resolve()` so passing an explicit tier cannot
  bypass it. Deliberately **not** a `market_context` CTX column: `market_context.get()`
  returns None whenever `REGIME_GATES_ENABLED` is off, which would let an
  unrelated flag silently disable this one.
- Tests build OHLCV frames with `tests/conftest.py:make_ohlcv` /
  `make_trend_df` (columns `Open,High,Low,Close,Volume`, business-day
  DatetimeIndex) and `tests/helpers.py`. Read conftest before writing new
  entry/exit tests. Synthetic fixtures for entry filters usually need
  REPL-tuning until the ungated function actually fires — freeze the shape in
  the test with a comment once it does.
