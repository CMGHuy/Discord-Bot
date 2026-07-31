# Known traps

Referenced from the root `CLAUDE.md`. Each of these has already cost a
session — read this before touching data caching, `scan_engine`/`scan_embeds`,
`embeds.py`, or the scan loop.

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
- **`download_and_cache()` overwrites destructively; only `update_cache()`
  merges.** `download_and_cache` → `save_to_disk` → `df.to_csv(path)`, full
  replace, no merge. Because the on-disk hourly cache accumulates
  incrementally past Yahoo's rolling ~730-day window (the bot's own refresh
  loop keeps appending), calling `download_and_cache(t, "hourly")` on an
  *existing* cache silently **deletes** whatever history predates what Yahoo
  will serve today — and that history can never be re-fetched, since Yahoo
  has already aged it out. Measured 2026-07-31: `GC=F` hourly cache held
  13,758 bars from 2024-03-08, but Yahoo would only serve 11,488 from
  2024-07-31 that same day — a naive re-fetch would have destroyed ~5 months.
  Equities are exposed the same way (`NVDA` hourly cache reaches back to
  2023-08-25, well past the 730-day line). **Rule: never call
  `download_and_cache` on a timeframe that already has a cache file; use
  `update_cache` (incremental, merges, atomic replace), or merge-then-write
  with a guard that refuses to shrink row count.** Daily/weekly/monthly are
  not at risk — full history is always re-servable, so an overwrite there
  loses nothing.
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
- **Two independent things close a trade, and the legacy one runs first.**
  A v2 plan-linked trade is logged with `take_profit = plan.tp1`, but the
  legacy loops in `performance.py` (`close_if_live_price_hit`,
  `update_open_trades`) iterate *every* open trade and run **before**
  `plan_manager.run_manager_tick()` in the same 60s `trade_monitor` pass —
  and again inside the scan. Until v8 Task V4 they full-closed v2 trades at
  TP1, and the manager's `tp1_partial` then no-opped in
  `append_leg_by_plan` (it requires a still-open trade), so scale-out never
  reached the trade log at all. Guard is `performance.manager_owns_target()`
  — plan-linked + `INTRADAY_MANAGER_V2` on hands over the **target** side
  only, keeping the stop as a backstop. **Any new "close an open trade"
  path must consult it**, or it silently steals the runner back. The
  failure mode is invisible: no error, no log line, just a leg that never
  gets written.
- **Function names that don't exist** (plans and briefs guess wrong at these
  constantly — verify before use): there is no `market_events.days_to_earnings`
  (use `events.get_next_earnings_date` / `earnings_within_window`), no
  `jsonio.write_json` (use `atomic_write_json`), no `TradeLog().all_trades()`
  (use `get_trades(limit=None)`). **A plan file is a design document, not
  ground truth about the current code** — grep the symbol before you call it.
- Scans run through `map_tickers()` (`SCAN_WORKERS`, default 4). Anything
  touching shared state (`state.confirm_or_update`, funnel counters) must stay
  serial/post-join.
