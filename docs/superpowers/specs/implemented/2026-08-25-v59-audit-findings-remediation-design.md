# v59 — Repo-wide audit findings: remediation

Version: ui 1.8.4 · bot 1.4.3
Bump: bot patch · ui patch
Edge: none (integrity)

## What this is

A read-only audit swept all five subsystems on 2026-08-25 and returned ~36
concrete defects. Seven were fixed and committed the same session; this
document inventories **everything left**, splits it into what may be patched
directly and what may not, and is the source for the v59 plan.

The `Edge:` line is `none (integrity)` deliberately. Nothing here adds a
discriminator or harvests more R — it corrects measurement and stops silent
losses. Two findings (A-T4, A-T5) nevertheless matter enormously to edge
*work*, because they corrupt the pooled `ExpR` that `edge-priorities.md`
ranks every candidate plan by. Fixing a broken ruler buys no edge; it makes
the next measurement mean something.

## Already fixed (do not re-open)

| Commit | Defect |
|---|---|
| `b70027b` | `.env` line-break injection forged settings on both the PUT and import paths; audit log and `.env` disagreed permanently |
| `b70027b` | `build_scenarios` shared one `Level.sources` list between directions; confidence scoring's in-place append leaked a bullish candlestick label onto the **bearish stop** |
| `b70027b` | `dedup_sector_items` read `g.ticker`, absent on a real `ScanItem` — latent scan-killing `AttributeError` |
| `452864e` | **Root cause of the production cache corruption.** v56's `_adjustment_ratio` rescaled off a single overlapping bar, so a mid-session refresh of a half-formed daily bar rescaled the whole history on any >1% mover |
| `452864e` | `_send_alerts` and `weekend_deep_scan` unpacked 4-tuples into 3 names — **every** alert lost on any scan over `MAX_ALERTS_PER_SCAN` |
| `ffb8297` | `close_if_live_price_hit` closed v2 plan trades (destroying scale-out end to end) and recorded the nominal stop, faking exactly −1.00 R on every gap |

Suite after those: `2360 passed, 66 skipped, 0 failed, 0 xfailed`.

## Group A — plain bugs, patch directly

Ranked within each subsystem. Every one has a named failure scenario; none
changes which trades qualify or how they are scored.

### A-T · Trade lifecycle, money math, persistence

| id | Site | Defect and consequence |
|---|---|---|
| A-T4 | `core/analytics/metrics.py:158` `r_multiple`, `:312` `trade_return_pct`, `core/analytics/risk_metrics.py:53` | "THE single shared R-multiple computation" still prices off `exit_price` alone, which for a scaled-out trade is the **runner leg only**. `closed_r_multiple` was fixed; these were not. Corrupts `expectancy_r`, the R histogram, sharpe/sortino, equity curve, calendar returns, journal `r_realized`, MFE/MAE efficiency and the Kelly inputs. 50% at TP1 (+2R) then runner at break-even reads +0.05R instead of ≈+1.02R |
| A-T5 | `core/tracking/performance.py:784` `get_extended_stats` | Reimplements the same raw formula inline, so `/api/v1/analytics` and the Dashboard disagree with `admin/dashboard.py:156`, which correctly calls `closed_r_multiple`. Same trade, two numbers |
| A-T3 | `core/planning/account.py:112` `_sum_realized_pnl`, `:419` `apply_realized_pnl` | The legs fallback never checks `status`, so a **still-open** PARTIAL trade's banked TP1 leg is counted; at final close it is added again on top. `balance` self-heals on next load, `balance_history` does not — and that history feeds `throttle.drawdown_pct` (the kill-switch trigger), `growth_path` and the equity chart |
| A-T6 | `core/tracking/performance.py:510` `close_plan_trade` | The only close path that never calls `_journal_close_safely` / `_refresh_snapshot_safely`. With `PLAN_ENGINE_V2` on by default, **every** v2 close is absent from `journal.json` forever, silently emptying the retrospective, weekly digest, both journal browsers and `/calendar`'s MFE/MAE + lesson + tag columns |
| A-T8 | `core/analytics/snapshots.py:107` | Passes `get_trades(status="all")` into a parameter named and documented `closed`. `overall["n"]` and every `stats_by` row then count open trades, producing an `n` that can never equal wins+losses; the v1 route filters correctly, so the two surfaces disagree |
| A-T10 | `commands/views.py:25` | Module-level `_plan_store = PlanStore()` loaded at import, never reloaded. Every alert's Chart/Breakdown button answers "this plan no longer exists" for its whole 180s life — only plans that existed at process start ever work. `commands/stats.py:17` shares the defect |
| A-T7 | `core/planning/plan_manager.py:143` `poll()` | Reloads once, then rewrites the whole store after each network-bound price call. A plan added by the scan thread mid-poll is erased — the exact failure `reload()` exists to prevent, moved inside the loop |
| A-T12 | `core/edge/throttle.py` / `engine.py:1841` | Kill switch has no hysteresis and no manual-release memory, so a human `off` is re-tripped by the next scan. The DD ladder has `RESUME_DD_PCT` for precisely this; `7314194` removed the *cause* of the observed loop but left the design gap |
| A-T11 | `core/infra/jsonio.py:71` | `atomic_write_json` uses a fixed `<path>.tmp`; bot and admin are separate processes, so `_LOCK` (a `threading.Lock`) protects nothing. Interleaved writes can truncate `trades.json`, which `read_json` then returns as `[]` and the next save persists — wiping the trade log. PLAUSIBLE, narrow window, severe outcome |
| A-T9 | `core/backtesting/backtest_wf.py:412` | Portfolio dedup mirrors `has_open_trade`/`has_similar_open_trade`, which the live path no longer calls; the real rule is `open_trade_for_ticker` (one per ticker, direction-blind). `wf_run.py --portfolio` runs `one_per_ticker=False`, so headline walk-forward results model capital the live account cannot commit |

### A-D · Discord layer, scheduling, config

| id | Site | Defect and consequence |
|---|---|---|
| A-D1 | `commands/scanning.py:1106` `notify_plan_events` | The one unguarded await in `trade_monitor`. `plan_manager` emits `pyramid_add`, absent from `embeds._EVENT_STYLE` → `KeyError`. `trade_monitor` has no `.error` handler, so the 60s SL/TP monitor dies **permanently** the first time `PYRAMIDING_ENABLED` is switched on |
| A-D3 | `commands/scanning.py:918-1023` | The admin-trigger branch of `config_watcher` is entirely unguarded and the loop has no `.error` handler. One exception permanently kills `.env` hot-reload, the "Run !check now" trigger and the manual-close notify queue — and on deployments without a Docker socket this loop is the *only* apply path |
| A-D10 | `bot_core.py:229` `in_session` | Cannot express a window crossing midnight, and `START >= END` is accepted by the UI (`min=0, max=23`) and silently disables **all** automatic scanning, with every surface reporting a normal off-hours state |
| A-D11 | `commands/scanning.py:1452`, `854` | `MARKET_DATA_AUTO_REFRESH` false→true can never take effect live (both the start call and the loop body gate on it), and `MARKET_DATA_REFRESH_MINUTES` is applied only via the SIGHUP path — a no-op on exactly the deployment `config_watcher` exists for. The UI promises a live apply |
| A-D8 | `commands/scanning.py:1213` | `weekend_deep_scan` mutates `SIGNAL_CONFIRMATION_SCANS` / `MIN_ALERT_CONFIDENCE_LEVEL` and restores **captured** values, silently reverting any hot-reload that landed during the scan — permanently, since `reload()` has already stamped `_ENV_MTIME` |
| A-D9 | `config.py:924` + `engine.py:1336` | `auto_reload_if_changed` rewrites the hard-filter globals with no `is_scan_running()` check, while the scan body reads them per-ticker in a worker thread. One scan can price its first tickers at one `MIN_RISK_REWARD_RATIO` and the rest at another, reporting a single threshold |
| A-D7 | `commands/scanning.py:1119`, `1292` | `daily_recap` / `weekend_deep_scan_task` once-per-day guards are in-memory globals over a 45-minute window: a restart inside it re-fires the whole retrospective or deep scan, and downtime across it skips the day with no catch-up |
| A-D5 | `commands/scanning.py:1426` `on_ready` | Re-announces "Bot online" and re-runs `tree.sync()` on every gateway reconnect; sync failures are swallowed, so exhausting the 200/day limit is invisible |
| A-D12 | `commands/scanning.py:1680` `_check_historical` | `limit=None` then one unbatched `ctx.send` per matching trade, uncapped — a plausible contributor to the 429s already logged in production, alongside the 0.8s progress-edit poller |

### A-M · Market data

| id | Site | Defect and consequence |
|---|---|---|
| A-M2 | `core/marketdata/data_store.py:322` `update_cache`, `:386` `get_intraday` | Two more `existing ∪ fresh` merges with **zero** adjustment-basis protection — the v56 guard landed only in `data_refresh._merge_save`. A split during a `--universe sp500` run reproduces the original cliff, in the cache the live scan reads |
| A-M4 | `core/marketdata/universe.py:153` | The volume-spike denominator includes the spike bar itself (`rolling(20)` is inclusive), deflating the ratio and capping it at 20. A genuine gap-up (QBTS 2024-12-16, +44.6% on 164M shares) reads 2.88x, fails the `>=3.0` escape, and the ticker is dropped from **all** new-signal scanning and every backtest for ~500 bars. A systematic false-positive class, not a one-off |
| A-M5 | `core/marketdata/data_refresh.py:167` docstring vs `universe.py:17` | The stated reason volume is left unrescaled ("every live consumer keys off a volume RATIO") is false: `_avg_dollar_vol` computes an absolute `Close × Volume` against a fixed $20M floor. After a 10:1 split a $200M/day name reads ~$20M for ~20 bars and can fail the liquidity screen |
| A-M6 | `core/marketdata/export_data.py:225` | A 5-thread `ThreadPoolExecutor` over `yf.download` — the exact non-reentrant `shared._DFS` hazard `known-traps.md` documents and `_fetch_cold_frames` uses processes to avoid. Reachable from `!scrape`; the standing guard test covers only the scan path |
| A-M8 | `core/marketdata/backtest_cache.py:94` | A ticker cached once is never refreshed and no consumer checks the CSV's end date, so a ticker added months ago contributes zero trades to a recent VALIDATION window while being printed as loaded. Pooled `N` is quietly smaller than the ticker count implies |
| A-M3 | (no site) | Nothing detects or repairs an already-two-basis archive. `validate_data.py` runs only `data_quality_issues`, whose >40% threshold cannot see a compounding 1–5% seam. The only working repair is delete-and-cold-refetch, done by hand this session |
| A-M9 | `core/marketdata/data_refresh.py:260` | A silently-empty provider response is recorded as `"fresh"` and clears `fail_count`, so a renamed/delisted symbol never reaches `pending_gaps()` — the operator sees a healthy state file while the data froze |
| A-M11 | `core/marketdata/data.py:174` | `ticker_meta_cache.json` is a non-atomic whole-dict overwrite from two processes — not among the six `known-traps.md` enumerates. Lost updates, and a truncation-window reader silently restarts with an empty cache |
| A-M7 | `core/marketdata/data_store.py:194` | `get_intraday`'s `save_to_disk` is a bare `to_csv` into a file `data_refresh` writes atomically and reads; a crash mid-write permanently truncates the hourly archive this function exists to protect |
| A-M10 | `core/marketdata/data_store.py:170` | An exception in the first `_capped_attempts` shape advances the *candidate symbol* loop, skipping the recent-listing fallback entirely — a recent IPO's hourly cache stays permanently cold, retried every 30 min forever |

### A-S · Scan pipeline

| id | Site | Defect and consequence |
|---|---|---|
| A-S1 | `core/scanning/engine.py:478`, `875` | `LRUFrames(max_frames=200)` silently evicts most of a larger universe (`SCAN_UNIVERSE="sp500"` is a shipped option). Evicted tickers are never scanned, **their open paper trades stop being monitored for SL/TP**, and each sets `data_quality_failed`, driving `data_fail_frac` past `KILL_DATA_FAIL_FRAC` so the kill switch engages every scan |
| A-S4 | `core/scanning/engine.py:1992` | An unguarded, unbounded `get_daily_data()` inside the alert-building loop. One transient fetch failure unwinds the whole scan: every already-built alert is lost, and `notify_closed_trades`/`notify_near_close` never fire for trades already persisted as closed this pass |
| A-S2 | `core/market/trendlines.py:293` | `strongest_trendline_pair` converts trimmed-frame geometry with untrimmed bar indices, so a support line can be drawn 16% *above* spot and `window_bars` inflates ~20x. `_chart_trendline_fit` then persists that wrong fit onto the trade record permanently |
| A-S5 | `core/scanning/engine.py:2085` | With `PLAN_ENGINE_V2` on (default) the logged trade mixes v2 prices with the legacy `risk_reward_ratio` and `target_sources` — storing a capped target price alongside an 8.0 R:R and source labels naming a level that is not the stored target |
| A-S7 | `core/scanning/embeds.py:228` | The opex near-close gate re-reads the wall clock per scenario from worker threads, while the engine resolves the tier once per scan for exactly this reason — a scan straddling the boundary blocks some tickers and not others, non-reproducibly |

### A-A · Admin API and SPA

| id | Site | Defect and consequence |
|---|---|---|
| A-A1 | `frontend/.../trades/trades.ts:222` + `admin/api_v1/trades.py:59` | The Trades workspace ships a live **Tier** filter that sends `?tier=`, but `tier` was removed from the server allow-list and `parse_collection_params` 400s on any undeclared parameter. `TradesStore.load()`'s error branch leaves `data` untouched, so the table keeps showing the **previous, unfiltered rows** under a filter bar reading "Tier A". `tier` is never emitted by the row builders either, so the column renders permanently blank. A spec asserts the client sends it, against a mock that never 400s |
| A-A5 | `admin/api_v1/trades.py:644` | The `ticker` filter falls to the generic exact, case-**sensitive** branch and is not in `_CASELESS_FILTERS`, while the SPA control is a free-text input passing raw keystrokes. Typing `aapl` returns an empty table with no explanation; the predecessor used case-insensitive substring matching |
| A-A6 | `admin/jobs.py:249` vs `:231` | `status()`/`all()` call `_reap_stale`, which writes `admin_jobs.json` **without** `self._lock`, while the watcher thread's completion write holds it. A `GET /api/v1/jobs` landing as a job completes can overwrite `done` back to `running`; the watcher has already exited, so the next reap marks it `failed` — a successful tuning grid reported as failed |
| A-A8 | `admin/helpers.py:106` + `config.py:924` | `_write_env_text` is truncate-then-write and `auto_reload_if_changed()` runs on **every** admin request in a threaded server. A concurrent reader can apply a partial config and stamp `_ENV_MTIME` with the partial file's mtime; at 1-second mtime granularity (this deployment's documented reality) the completed write carries the same mtime and is **never** reloaded — the admin serves half-applied config indefinitely |
| A-A9 | `admin/api_v1/trade_commands.py:56` | `_queue_notify` is an unlocked read-modify-write over `manual_close_notify.json`, which the separate bot process consumes and clears — duplicate trade-history posts, or a close that never reaches Discord. Not atomic and not watched, so the loss is silent |
| A-A3 | `frontend/.../stores/chart.store.ts:89` | `load()` uses a bare `.subscribe()` with no cancellation or request/response matching, so a slow response for the previous ticker renders under the current one's header. `market.py:474` echoes `"ticker"` back **specifically** so a response can be matched to its request; the client never reads it |
| A-A7 | `frontend/.../stores/trades.store.ts:134`, `dashboard.store.ts:210` | No `switchMap` or sequence guard in any store but watchlist-suggest, though `interceptors.ts:79`'s own comment asserts one exists. `/api/v1/trades` fetches live prices and is genuinely slow, and `trades` events fire throughout a scan — an older snapshot can replace a newer one, and `loading` flips false with a request still out |
| A-A2 | `frontend/.../stores/session.store.ts:123` vs `:191` | A 401's `unauthorized.report()` schedules an `expire()` effect that sets `error: null`; the promise rejection continuation is a microtask and sets the message first. A wrong password returns the form to idle with **no feedback at all**. Its spec passes only because zoneless tests never `tick()` before asserting |
| A-A12 | `admin/api_v1/jobs.py:162` | `create_proposal` indexes `row["params"]` and calls `strategy.lower()` with no shape check, so a crashed/partial `tune_strategy.py` result file (written by `Path.write_text`, listed before complete) raises into a bare Flask **HTML 500** rather than the v1 error body the SPA parses |
| A-A11 | `admin/api_v1/analytics.py:72` | `/analytics/performance` has no unknown-parameter rejection, unlike `calendar.py`. `?form=...` is silently ignored, `range.from` returns `null`, and all-time figures are read on screen as the requested window |
| A-A10 | `admin/api_v1/calendar.py:57` | `strptime(raw, "%Y-%m")` accepts `2026-1`, but `month_grid` compares `r["day"][:7]` as a plain string — a month with real trades returns 200 with `days: []`, the exact outcome the 400 exists to prevent |

## Group B — methodology-gated, NOT patched here

These change which trades qualify or how they are scored. Per
`backtest-methodology.md` each needs a written hypothesis and a
pre-registered TRAIN run before any code change. **Listing them is not
approval to implement them.**

| id | Site | Question to pre-register |
|---|---|---|
| B-1 | `core/scanning/confidence.py:564` | The expectancy adjustment scores off the **legacy** scenario's R:R, but the trade is placed at `plan_v2.tp1`, capped at `MAX_RISK_REWARD_RATIO`. A legacy 8.0 R:R can buy the +1 level that clears `MIN_ALERT_CONFIDENCE_LEVEL` for a trade whose real payoff is 4R. Live on defaults |
| B-2 | `core/market/levels.py:680` | `build_scenarios` only ever tests `resistances[0]`/`supports[0]`; `target2` is computed *after* target1 qualifies. A farther, horizon-appropriate level is never tried when the nearest fails — measured live as ~96% of ticker/horizon combos rejected, `min_reward` present in 85% of failures |
| B-3 | `core/market/levels.py:124` | `_cluster_levels` compares each candidate to the running bucket **mean**, so greedy chaining can merge a span far wider than `CLUSTER_TOLERANCE_PCT` into one level at a price no method predicted, carrying all their labels |
| B-4 | `core/scanning/confidence.py:427` | Every momentum/volatility quality factor (MACD 12/26/9, RSI 14, ADX 14, squeeze 20/10) is horizon-blind across all ten horizons, though `MACD_PERIODS_BY_HORIZON` exists to scale them. `score_confidence` takes no `horizon_key` at all |
| B-5 | `core/scanning/confidence.py:633` | Under `UNIFIED_CONFIDENCE` the base level counts raw source labels, not strategy families, so `["EMA8","EMA13"]` counts 2 where `count_confirming_strategies` counts 1 — two counters documented as unable to disagree. Also makes Level 5 structurally unreachable. Dormant (flag defaults off) |
| B-6 | `core/market/mtf.py:41` | `len(df) < slow + 1` is too weak a warm-up bar for an `adjust=False` EWM: 201 bars satisfies it for an EMA200 and returns a meaningless value, which `adjacent_aligned` can then hard-drop a scenario on instead of returning "exempt" |

## Decisions

1. **Group A is fixed under TDD**: a test reproducing the defect, confirmed
   failing, before each fix. Several findings survived precisely because an
   existing test asserted a shape production never produces
   (`dedup_sector_items`) or never exercised the real branch
   (`_send_alerts` overflow) — so a test that passes against the *real*
   type is part of each fix, not an optional extra.
2. **Group B ships no code in v59.** Each becomes its own numbered spec with
   a pre-registered hypothesis, or nothing.
3. **A-M3 gets a detector, not an auto-repair.** A tool that silently
   rewrites price history is how this class of corruption spread in the
   first place; it reports and the operator chooses.
4. **`VERSION.json` is not bumped by the plan's tasks.** The release commit
   is separate and must regenerate `version_history.json` alongside it —
   the local gate runs before the bump and structurally cannot catch a miss.

## Out of scope

- The three stale worktrees (`v36`, `v49`, `v54`). `v36`/`v49` branches hold
  12 and 5 unmerged commits — the only copy of measured-but-rejected work,
  and `backup`/rollback safety rules apply.
- `v58` (unstarted, 9 tasks) and closing `v54` out to `implemented/`. Both
  are real outstanding work, tracked independently of this document.
- `commands/views.py:57`'s non-persistent `PlanActionView` timeout — the
  buttons grey out honestly on timeout, so it is a design question, not a
  defect. (A-T10 above, the *stale store*, is a defect and is in scope.)
