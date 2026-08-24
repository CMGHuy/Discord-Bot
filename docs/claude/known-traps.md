# Known traps

Referenced from the root `CLAUDE.md`. Each of these has already cost a
session — read this before touching data caching, `scan_engine`/`scan_embeds`,
`embeds.py`, or the scan loop.

- **Two parallel OHLCV cache subsystems — do not conflate them.** Both now
  live in `swingbot/core/marketdata/` (v27 repo restructure, 2026-08-15).
  `marketdata/backtest_cache.py` → `data/backtest_cache/` (flat `TICKER.csv`,
  daily only, ~77 tickers, what every existing backtest/grid script reads).
  `marketdata/data_store.py` → `market_data/` (grouped by candle timeframe:
  `{timeframe}/{TICKER}.csv`, e.g. `market_data/daily/AAPL.csv`, ~521 daily +
  78 hourly, what the edge-engine tasks depend on -- and, since v47, what
  the live scan reads first). Both are gitignored.
  Check which one a script reads before pointing it at a path.
- **`market_data/` is timeframe-first, not ticker-first.** Folders are the
  semantic names in `data_store.TIMEFRAMES` (`monthly`, `weekly`, `daily`,
  `hourly`, `15min`, …); filenames are sanitized (`GC=F` → `GC_F.csv`, same
  scheme as `backtest_cache`). Every accessor takes EITHER the semantic name
  or the yfinance code — `load_from_disk(t, "1h")` and
  `load_from_disk(t, "hourly")` resolve to the same file. Go through
  `cache_path()`/`load_from_disk()`; never hand-build the path.
- **The bot self-refreshes this cache while running**
  (`core/marketdata/data_refresh.py`, driven by the `market_data_refresh`
  task loop in `commands/scanning.py`).
  Incremental and staleness-gated per timeframe (hourly 4h, daily 12h,
  weekly/monthly 24h), so most wake-ups cost no network. Flags:
  `MARKET_DATA_AUTO_REFRESH`, `MARKET_DATA_REFRESH_MINUTES`,
  `MARKET_DATA_TIMEFRAMES`.
- **Yahoo's intraday depth is a hard ceiling, not a tuning knob.** 1h serves
  ~730 *trading* days (~3 calendar years, measured); 15m/30m/5m only ~60 days;
  1m ~30 days. "Since IPO" hourly data does not exist from this source at any
  tier — only daily and coarser reach the listing date. Do not write a task
  that assumes otherwise.
- **The legacy shims are gone — do not go looking for them.**
  `core/scan_engine.py` (an `import *` shim over `core/scanning/engine.py`)
  and `core/trade_plan.py` (a deprecated adapter over
  `planning/plan_engine.build_strategy_plan`) were both removed 2026-08-15 by
  the v27 repo restructure, alongside the `core/scan_embeds.py`,
  `core/confidence.py` and `core/regime.py` shims that predated them (those
  three had no callers left even before v27). Every call site now imports the
  real module directly — `from swingbot.core.scanning import engine as
  scan_engine` is the live equivalent of the old `scan_engine.py` shim import,
  keeping the `scan_engine.*` vocabulary at usage sites unchanged.
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
- **An empty config table is not automatically an unfinished one.**
  `strategy_types.REGIME_ALLOW = {}` with `REGIME_GATES_ENABLED` defaulting off
  reads like a stub someone forgot to fill. It is the **measured answer**: the
  v17 P2a harness (`scripts/data/fill_regime_allow.py`) ran the pre-registered rule
  across 78 tickers × 11 strategies × 10 horizons on TRAIN and no cell cleared
  it, recorded in `docs/superpowers/results/2026-08-08-regime-allow-train.md`.
  The spec pre-committed to accepting that outcome. Filling the table by hand,
  or re-running with looser thresholds, undoes a closed pre-registration —
  see `docs/claude/backtest-methodology.md`. **Before "finishing" any empty
  table or default-off flag, grep `docs/superpowers/results/` for its name.**
- **An "unused import" here is often a deliberate re-export — check before
  deleting one.** A linter's unused-import list is not a delete list in this
  repo: `core/market/strategy.py` re-exports its `signals`/`strategy_types`
  split so `from swingbot.core.market.strategy import <anything>` keeps
  working, `core/scanning/engine.py` re-exports embeds symbols that callers
  reach directly now that the `core/scan_engine.py` `import *` shim is gone
  (removed 2026-08-15 by v27), and `admin/app.py` re-exports
  `docker_sdk`/`_SECTION_META` purely for `api_v1/system.py`. A
  2026-08-14 cleanup pass found **4 of 29** flagged imports were load-bearing
  this way. Before removing one, grep for both `from <module> import <name>`
  and `<module>.<name>` across `swingbot/`, `tests/` and `scripts/`. The known
  re-export blocks now carry `# noqa: F401` and a comment saying so — leave
  them.
- **Function names that don't exist** (plans and briefs guess wrong at these
  constantly — verify before use): there is no `market_events.days_to_earnings`
  (use `events.get_next_earnings_date` / `earnings_within_window`), no
  `jsonio.write_json` (use `atomic_write_json`), no `TradeLog().all_trades()`
  (use `get_trades(limit=None)`). **A plan file is a design document, not
  ground truth about the current code** — grep the symbol before you call it.
- Scans run through `map_tickers()` (`SCAN_WORKERS`, default 1 as of v56 --
  was 4, but measured directly against the real watchlist: cpu-time/wall-time
  stayed ~1.0x at every worker count 1-8, since the per-ticker work is
  pure-Python-glue-heavy, not vectorized enough to release the GIL for a
  useful stretch, so more threads bought no real parallelism and were
  measurably slower than serial). Anything touching shared state
  (`state.confirm_or_update`, funnel counters) must stay serial/post-join.
- **The live scan reads `market_data/daily/` now (v47).** `_crawl_latest_data`
  is cache-first: `_load_cached_daily()` serves any ticker whose CSV is fresher
  than `SCAN_CACHE_MAX_AGE_HOURS` (6h), and only the cold remainder is fetched.
  So the two OHLCV caches are no longer "backtest reads one, scan reads
  neither" -- `market_data/` is now on the live path, and a change to
  `data_store.load_normalized()` affects live alerts.
- **Cold fetches use PROCESSES, never threads** (`_fetch_cold_frames`). yfinance
  0.2.66's `download()` writes a shared module global (`_DFS`) non-reentrantly;
  a thread pool here once attributed one ticker's price data to another and
  logged both as open trades with identical values.
  `tests/scanning/test_no_cross_ticker_mixing.py` is the standing guard -- if
  you ever make this concurrent a different way, that test must still pass.
- **Trade History: filtering, sorting and paging must stay on the SAME side.**
  The dashboard's `ct-*` controls used to hide/reorder rows in the DOM while
  the server shipped up to 500 pre-rendered rows. Once paging moved
  server-side (plan v9; the route is `/api/v1/trades` now, the Jinja
  `/api/trade-history` having gone with Release B), any control left in the
  browser would silently operate on *the current page only* — a ticker filter
  would quietly mean "matches among these 25", which is worse than no paging
  at all. All six filters, all 14 sort columns and the pager go through
  `query_closed_trades()`, which survived the Jinja deletion precisely
  because it is builder-level and the v1 API uses it too. If you add a Trade
  History control, add it there too; do not filter or sort rows client-side.
  **The filter dropdown *options* used to be the deliberate exception** — the
  Jinja page built them from the FULL history via
  `dashboard.build_filter_options`, never from the loaded page, because values
  appearing only in older trades would otherwise become unselectable. The SPA
  answered that differently: the ticker filter is a free-text input, so there
  is no option list to go stale. `build_filter_options` had no caller left
  after Release B and was deleted on 2026-08-14. **If you ever reintroduce an
  enumerated filter dropdown, build its options from the full history
  server-side** — deriving them from the loaded page is the original bug.
- **Not every `data/` JSON file is written atomically — six are not.** Spec
  v12 Decision 2 asserted the whole directory was; the NG23 audit found
  otherwise, which is why that task existed. Atomic, via
  `jsonio.atomic_write_json` (`<path>.tmp` → fsync → `os.replace`):
  `trades.json` (`core/tracking/performance.py:225`), `plans.json`
  (`planning/plan_store.py`), `starred_plans.json` (`commands/views.py:36`),
  `account.json` (`core/planning/account.py:174`), `state.json`
  (`core/infra/state.py:31`), `analytics_snapshot.json`
  (`core/analytics/snapshots.py:71`), `journal.json`
  (`core/analytics/journal.py:32`), `killswitch.json`
  (`core/edge/throttle.py:94`). **Plain `open(path, "w")` + `json.dump`**
  — truncate first, then fill, so a reader inside that window gets a
  truncated document: `scan_snapshots.json` (`core/scanning/embeds.py:58`),
  `bot_heartbeat.json` (`commands/scanning.py:172`), `watchlist.json`
  (`core/marketdata/watchlist.py:21`), `ticker_directory.json`
  (`core/marketdata/ticker_directory.py:108`), `admin_jobs.json`
  (`admin/jobs.py:120`),
  and `.env` (`admin/helpers.py:114`). `tuning_results/<job>.json` uses
  `Path.write_text` (`scripts/backtest/tune_strategy.py:171`) — a fresh file per job,
  so nothing is truncated, but it is listed in the directory before it is
  complete. **The event watcher is not the exposure** — it compares
  `(mtime, size)` and never opens a watched file. The exposure is the SPA,
  which refetches through the v1 API on the event, and the API does parse.
  The 250ms trailing debounce puts that refetch at least a debounce after
  the last observed write, which covers all of these in practice (they are
  small), so this is a narrow race and not a live bug — but note that push
  *correlates* it where polling did not: the 5-second poll hit a write
  window by luck, an event fires precisely because of the write. Use
  `atomic_write_json` for any new file under `data/`, and before growing any
  of the six.
- **The non-parsed watched paths are deliberate, not an oversight.** The four
  `*.flag` files carry their whole meaning in existence + mtime, and
  `scan_telemetry.jsonl` is append-only, so a torn trailing line is the
  reader's problem and the API owns tolerating it (spec v12 Decision 2).
  Do not "fix" either by adding a parse to the watcher — that would trade
  away the property that makes it immune to schema changes.
