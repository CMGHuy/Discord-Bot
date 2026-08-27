# v59 — Repo-wide audit findings: remediation (plan)

Version: ui 1.8.4 · bot 1.4.3
Bump: bot patch · ui patch
Edge: none (integrity)

Spec: `docs/superpowers/specs/2026-08-25-v59-audit-findings-remediation-design.md`
— read it first; it carries the diagnosis and failure scenario for every `A-*`
id referenced below, and this plan does not repeat them.

## Progress

Completed 2026-08-27. All implementation tasks landed on `main`; final
verification completed with `2447 passed, 66 skipped, 0 failed, 0 xfailed`.

## Goal

Close every Group A finding. Group B is explicitly **out of scope**: those
change which trades qualify or how they are scored and need their own
pre-registered spec.

## Global constraints

1. **TDD, no exceptions.** Write the test, run it, *see it fail for the stated
   reason*, then fix. Several of these bugs survived because an existing test
   asserted a shape production never produces — a test that passes against the
   **real** type is part of the fix.
2. **No behaviour change beyond the finding.** No "while I'm here" refactors.
3. **Money-math tasks isolate `DATA_DIR`.** `_settle_account_balance →
   apply_realized_pnl` writes `account.json` with no `path=`; parallel workers
   racing the real file is a documented past failure.
4. **Per-task verification is the narrow run** (`testrun.py file <path>`).
   `testrun.py full` runs **once**, as Task 20.
5. **No `VERSION.json` bump inside these tasks.** The release commit is
   separate and must regenerate `version_history.json` with it.

## Parallelisation

Tasks touch mostly disjoint files. Three groups can run concurrently in
separate worktrees; within a group, run in order.

| Track | Tasks | Files owned |
|---|---|---|
| **A — money & lifecycle** | 1–6, 19 | `core/analytics/`, `core/tracking/`, `core/planning/`, `commands/views.py`, `commands/stats.py`, `core/backtesting/` |
| **B — bot loops & market data** | 7–15 | `commands/scanning.py`, `bot_core.py`, `config.py`, `core/marketdata/`, `core/scanning/`, `core/market/` |
| **C — admin & SPA** | 16–18 | `swingbot/admin/`, `frontend/` |

Task 17 touches `core/infra/jsonio.py` (shared) — land it **after** Track A's
Task 3, or serialise it. Task 20 runs last, alone, after all tracks merge.

---

## Phase 1 — Analytics tell the truth

### Task 1: One leg-aware R-multiple

- [ ] `core/analytics/metrics.py:158` `r_multiple` and `:312`
  `trade_return_pct`, plus `core/analytics/risk_metrics.py:53`, price off
  `exit_price` alone — the **runner leg only** for a scaled-out trade (A-T4).
- [ ] Test first, `tests/analytics/test_metrics_legged_trades.py`: a trade with
  `legs=[{fraction:.5, r:2.0, exit_price:…}, {fraction:.5, r:0.05, …}]` and an
  `exit_price` equal to the runner's. Assert `r_multiple` ≈ `+1.02`, not
  `+0.05`. Add the no-legs case asserting the old formula still holds exactly.
- [ ] Fix: blend fraction-weighted leg `r` when `legs` is truthy, identical to
  `performance.closed_r_multiple:258` (fall back to deriving a leg's `r` from
  its own `exit_price` when absent). `metrics.py` is documented as pure — **no
  file I/O, no config imports** — and `performance.py:373` already imports
  *from* it, so do **not** import `performance` here; keep the computation
  self-contained and cross-reference `closed_r_multiple` in the docstring.
- [ ] Apply the same blend to `trade_return_pct` and `risk_metrics._trade_return_pct`,
  which the docstrings promise "can never quietly disagree".
- [ ] Verify: `python scripts/dev/testrun.py file tests/analytics/test_metrics_legged_trades.py`

### Task 2: Both expectancy surfaces agree

- [ ] `core/tracking/performance.py:784` `get_extended_stats` reimplements the
  raw formula inline, so `/api/v1/analytics` and the Dashboard disagree with
  `admin/dashboard.py:156`, which calls `closed_r_multiple` (A-T5).
- [ ] Test: one legged win; assert `get_extended_stats()["expectancy_r"]`
  equals the value derived via `closed_r_multiple` for the same record.
- [ ] Fix: delegate to `closed_r_multiple`. Delete the inline arithmetic.
- [ ] Verify: `... file tests/tracking/test_tradelog_v2.py`

### Task 3: Account settlement stops double-counting TP1

- [ ] `core/planning/account.py:112` `_sum_realized_pnl`'s legs fallback never
  checks `status`, counting a **still-open** PARTIAL trade's banked TP1 leg;
  `apply_realized_pnl` then adds it again at close (A-T3).
- [ ] Test, extending `tests/planning/test_account_legs.py` (which only covers
  `status="win"`): an `open` trade carrying a TP1 leg must contribute **zero**
  to `_sum_realized_pnl`; then close it and assert `balance_history` gains
  exactly one point for the blended total, not TP1 twice.
- [ ] Fix: restrict the fallback to closed statuses. Note in the docstring that
  `balance` self-heals on reload but `balance_history` does not — and that
  history feeds `throttle.drawdown_pct` (kill-switch), `growth_path` and the
  equity chart, which is why the stale point matters.
- [ ] Verify: `... file tests/planning/test_account_legs.py`

### Task 4: Snapshots count closed trades only

- [ ] `core/analytics/snapshots.py:107` passes `get_trades(status="all")` into a
  parameter named and documented `closed` (A-T8).
- [ ] Test: 10 closed + 10 open trades; assert `overall["n"] == 10` and that
  `n == wins + losses` holds for every `stats_by` row, and that no `"unknown"`
  day/month bucket appears.
- [ ] Fix: pass closed trades only, matching `api_v1/analytics.py:107`.
- [ ] Verify: `... file tests/analytics/test_snapshots.py`

## Phase 2 — v2 trade lifecycle is complete

### Task 5: v2 closes reach the journal

- [ ] `core/tracking/performance.py:510` `close_plan_trade` is the only close
  path that never calls `_journal_close_safely` / `_refresh_snapshot_safely`;
  `plan_manager._on_event` has no hook either. With `PLAN_ENGINE_V2` on by
  default, every v2 close is absent from `journal.json` forever (A-T6).
- [ ] Test: close a plan-linked trade via `close_plan_trade`; assert a journal
  entry exists for it and the snapshot was refreshed. Mirror the assertions the
  `update_open_trades` path already has.
- [ ] Fix: call both, in the same order and with the same failure-swallowing
  as the sibling paths (a journal failure must never break a close).
- [ ] Verify: `... file tests/tracking/test_tradelog_v2.py`

### Task 6: Plan store is never stale and never truncating

- [ ] `core/planning/plan_manager.py:143` `poll()` reloads once, then rewrites
  the whole store after each network-bound price call — a plan added by the
  scan thread mid-poll is erased (A-T7). Separately,
  `commands/views.py:25` and `commands/stats.py:17` hold a module-level
  `PlanStore()` loaded at import and never reloaded, so every alert's
  Chart/Breakdown button reports "this plan no longer exists" (A-T10).
- [ ] Test (a): seed a plan, start a `poll()` whose `price_fn` adds a *second*
  plan via a fresh `PlanStore` on first call, assert both survive. This is the
  repro shape `tests/planning/test_manager_singleton_staleness_repro.py`
  already established.
- [ ] Test (b): create a plan *after* importing `commands.views`; assert the
  button lookup finds it.
- [ ] Fix (a): reload-before-write (or write only the mutated plan) inside the
  loop. Fix (b): resolve a fresh `PlanStore` per interaction, as every other
  call site does.
- [ ] Verify: `... file tests/planning/test_manager_singleton_staleness_repro.py`
  and `... file tests/test_views.py`

## Phase 3 — The bot survives its own edge cases

### Task 7: No single exception can kill a task loop

- [ ] `notify_plan_events` is the one unguarded await in `trade_monitor`, and
  `plan_manager` emits `pyramid_add`, absent from `embeds._EVENT_STYLE` →
  `KeyError` → the 60s SL/TP monitor dies permanently the first time
  `PYRAMIDING_ENABLED` is switched on (A-D1). The admin-trigger branch of
  `config_watcher` is likewise unguarded and that loop has no `.error` handler
  either — killing `.env` hot-reload, the trigger, and manual-close notifies on
  exactly the deployments where `config_watcher` is the only apply path (A-D3).
  `on_ready` re-announces and re-runs `tree.sync()` on every reconnect (A-D5).
- [ ] Tests: (a) an event with an unknown `transition` must not raise out of
  `notify_plan_events`; (b) `trade_monitor` and `config_watcher` both have a
  registered `.error` handler that restarts them, as `session_scan` does;
  (c) a second `on_ready` posts no second "Bot online" and re-syncs nothing.
- [ ] Fix: give `build_plan_event_embed` a default style for unknown
  transitions (render it, do not drop it), wrap the `config_watcher` trigger
  branch, add `.error` restart handlers to both loops, and add a module-level
  once-only flag for the announce/sync, matching the existing
  `_reload_handler_installed` / `_session_was_active` idiom.
- [ ] Verify: `... file tests/test_trade_monitor_task.py`

### Task 8: The session window is expressible and never silently off

- [ ] `bot_core.py:229` `in_session` cannot express a window crossing midnight,
  and `START >= END` is accepted by the UI and silently disables **all**
  automatic scanning while every surface reports normal off-hours (A-D10).
  `daily_recap` / `weekend_deep_scan_task` fire-guards are in-memory globals
  over a 45-minute window, so a restart inside it re-fires and downtime across
  it skips the day with no catch-up (A-D7).
- [ ] Tests: `START=22, END=6` is in-session at 23:00 and 02:00 and out at
  12:00; `START == END` is rejected or documented as always-on (pick one and
  assert it); a recap already fired today does not re-fire after a simulated
  restart.
- [ ] Fix: support the wrapping window; validate `START == END` at the config
  layer with a visible log line rather than silent death; persist the
  fired-date (it belongs with the other `data/` state, written through
  `atomic_write_json`).
- [ ] Verify: `... file tests/test_bot_core.py`

### Task 9: Config hot-reload cannot corrupt a scan or revert itself

- [ ] `weekend_deep_scan` restores **captured** config globals in `finally`,
  permanently reverting any hot-reload that landed mid-scan (A-D8).
  `auto_reload_if_changed` rewrites the hard-filter globals with no
  `is_scan_running()` check while worker threads read them per ticker, so one
  scan can price its first tickers at one `MIN_RISK_REWARD_RATIO` and the rest
  at another (A-D9). `MARKET_DATA_AUTO_REFRESH` false→true can never take
  effect live and the refresh interval applies only via SIGHUP (A-D11).
- [ ] Tests: a reload during a simulated scan does not change that scan's
  effective thresholds; after `weekend_deep_scan`, a value changed during it
  survives; toggling `MARKET_DATA_AUTO_REFRESH` on starts the loop.
- [ ] Fix: snapshot the hard filters once per scan alongside the two already
  snapshotted (`engine.py:1545`) and read the snapshot in `_scan_one`; have
  `weekend_deep_scan` restore only if unchanged (or scope the override rather
  than mutating globals); make the refresh loop start/stop on the flag and
  route interval changes through both reload paths.
- [ ] Verify: `... file tests/test_config_reload.py`

### Task 10: Discord send pressure

- [ ] `_check_historical` fetches `limit=None` and sends one unbatched message
  per matching trade, uncapped (A-D12) — a plausible contributor to the 429s
  already logged in production, alongside the 0.8s progress-edit poller.
- [ ] Test: 300 matching trades produce a bounded number of sends.
- [ ] Fix: batch into chunked messages (or page, as `!trades` does with
  `TradesPaginator`) and cap. Slow the progress-edit cadence.
- [ ] Verify: `... file tests/test_commands_check.py`

## Phase 4 — Market data

### Task 11: Adjustment-basis protection everywhere, plus a detector

- [ ] `data_store.py:322` `update_cache` and `:386` `get_intraday` do the same
  `existing ∪ fresh` merge with **zero** adjustment protection — the v56 guard
  landed only in `data_refresh._merge_save` (A-M2). Nothing detects an already
  two-basis archive (A-M3).
- [ ] Tests: a split across a `update_cache` merge leaves a single basis; the
  detector flags a synthetic two-basis frame and passes a clean one.
- [ ] Fix: route both merges through the shared, now-hardened
  `_adjustment_ratio` + rescale path. Add a **detector** to
  `scripts/data/validate_data.py` that scans for a compounding seam
  (a sustained level shift `data_quality_issues`' >40% bar test cannot see) and
  **reports** it. Per spec Decision 3 it must not auto-rewrite history; it
  names the tickers for a delete-and-cold-refetch.
- [ ] Verify: `... file tests/marketdata/test_data_refresh.py`

### Task 12: Screens read the basis they think they read

- [ ] `universe.py:153`'s volume-spike denominator includes the spike bar
  itself, so a genuine gap-up reads ~2.88x and the ticker is dropped from all
  new-signal scanning **and** every backtest for ~500 bars (A-M4). The stated
  justification for leaving volume unrescaled is false: `_avg_dollar_vol` uses
  an absolute `Close × Volume` against a fixed floor (A-M5).
- [ ] Tests: the QBTS 2024-12-16 shape (+44.6% on 164M after an already-hot
  week) is **not** flagged; a true unadjusted-split shape still is. A
  post-split frame passes the liquidity floor it should pass.
- [ ] Fix: compare against the **prior** 20 bars (`.shift(1)`), and either
  rescale volume with price or make `_avg_dollar_vol` basis-invariant —
  whichever the test shows correct. Update the `_merge_save` docstring, which
  currently asserts the false claim.
- [ ] Verify: `... file tests/marketdata/test_universe.py`

### Task 13: Market-data robustness bundle

- [ ] `export_data.py:225` uses a 5-thread pool over `yf.download` — the exact
  non-reentrant `shared._DFS` hazard `known-traps.md` documents and
  `_fetch_cold_frames` uses **processes** to avoid; reachable from `!scrape`
  (A-M6). `get_intraday`'s `save_to_disk` is a bare `to_csv` into a file
  written atomically elsewhere (A-M7). A cached backtest CSV is never
  refreshed and no consumer checks its end date, silently shrinking pooled `N`
  (A-M8). A silently-empty provider response is recorded `"fresh"`, so a
  delisted symbol never reaches `pending_gaps()` (A-M9). An exception in the
  first `_capped_attempts` shape skips the recent-listing fallback (A-M10).
  `ticker_meta_cache.json` is a non-atomic whole-dict overwrite from two
  processes (A-M11).
- [ ] Tests: extend `tests/scanning/test_no_cross_ticker_mixing.py` to cover
  the export path; a stale backtest CSV is reported; an empty response is
  recorded as a failure, not `"fresh"`.
- [ ] Fix: processes for the export fetch; `atomic_write_json`/atomic CSV for
  both cache writes; a staleness check (and `--force` guidance) for
  `backtest_cache`; distinguish "empty window" from "fetch failed"; move the
  `except` so the attempt loop is exhausted before advancing candidates.
- [ ] Verify: `... file tests/scanning/test_no_cross_ticker_mixing.py`

## Phase 5 — Scan pipeline

### Task 14: A scan cannot silently drop tickers or lose a whole pass

- [ ] `LRUFrames(max_frames=200)` silently evicts most of a larger universe
  (`SCAN_UNIVERSE="sp500"` is shipped): those tickers are never scanned,
  **their open paper trades stop being monitored for SL/TP**, and each sets
  `data_quality_failed`, driving `data_fail_frac` past `KILL_DATA_FAIL_FRAC`
  so the kill switch engages every scan (A-S1). An unguarded, unbounded
  `get_daily_data()` inside the alert-building loop discards every built alert
  and skips the close/near-close notifications on one transient failure (A-S4).
- [ ] Tests: a 500-ticker universe scans all 500 (or fails loudly, never
  silently); a `get_daily_data` raising mid-loop still posts the alerts already
  built and still fires close notifications.
- [ ] Fix: size the cache to the universe or stream rather than accumulate, and
  make a genuine eviction a loud error rather than a data-quality verdict; wrap
  the fetch, and treat its failure as "no chart for this alert", not "no scan".
- [ ] Verify: `... file tests/scanning/test_engine_v2_plans.py`

### Task 15: Persisted scan data is internally consistent

- [ ] `trendlines.py:293` converts trimmed-frame geometry with untrimmed bar
  indices — a support line drawn 16% *above* spot, then **persisted** onto the
  trade record by `_chart_trendline_fit` (A-S2). The logged trade mixes v2
  prices with the legacy `risk_reward_ratio` and `target_sources` (A-S5). The
  opex near-close gate re-reads the wall clock per scenario from worker
  threads while the engine resolves the tier once per scan (A-S7).
- [ ] Tests: a 2000-bar frame's returned trendline geometry sits on the correct
  side of spot with a sane `window_bars`; a logged v2 trade's stored
  `risk_reward_ratio` matches its stored `take_profit`; the opex tier used is
  the one passed in.
- [ ] Fix: convert with the trimmed origin; derive R:R and sources from
  whichever plan actually produced the stored prices; thread `opex_tier_today`
  into `_build_requirement_checks`.
- [ ] Verify: `... file tests/charts/test_trendline_fit_persistence.py`

## Phase 6 — Admin and SPA

### Task 16: Trades filters work, and bad params fail loudly

- [ ] The Tier filter sends `?tier=`, the server 400s on it, and the error
  branch leaves the **previous unfiltered rows** on screen under a "Tier A"
  label (A-A1). The ticker filter is exact and case-sensitive behind a
  free-text input (A-A5). `?month=2026-1` returns 200 with empty days (A-A10).
  `/analytics/performance` ignores unknown params, so a typo'd bound silently
  returns all-time (A-A11). `create_proposal` raises a bare HTML 500 on a
  partial result file (A-A12).
- [ ] Tests: `tier=A` filters (or the control is gone — decide, don't leave
  both); `aapl` matches `AAPL`; `2026-1` is a 400; `?form=` is a 400; a
  malformed result file returns the v1 error body, not HTML.
- [ ] Fix: implement `tier` server-side **and** emit it from the row builders,
  or remove the control and its spec assertion. Add `ticker` to
  `_CASELESS_FILTERS` with substring matching. Tighten the month regex. Add
  unknown-param rejection. Shape-check the proposal row.
- [ ] Verify: `... file tests/admin/test_api_v1_trades.py`

### Task 17: Concurrent writers cannot corrupt shared state

- [ ] `jobs.py:249` `_reap_stale` writes without `self._lock`, so a `GET` during
  a completion can flip `done` back to `running` and the next reap marks a
  successful grid `failed` (A-A6). `_write_env_text` is truncate-then-write and
  `auto_reload_if_changed` runs on every admin request; at 1s mtime granularity
  a completed write can be **never** reloaded, serving half-applied config
  indefinitely (A-A8). `_queue_notify` is an unlocked RMW over a file the bot
  process consumes (A-A9). `atomic_write_json` uses a fixed `<path>.tmp`, so
  two processes collide and can truncate `trades.json` — which `read_json`
  returns as `[]` and the next save persists (A-T11).
- [ ] Tests: a reap concurrent with a completion never regresses state; a
  torn `.env` is never applied; `atomic_write_json` from two writers leaves a
  valid document.
- [ ] Fix: take the lock in `_reap_stale`; write `.env` via temp + `os.replace`
  and compare content/`mtime_ns` rather than 1s mtime; route the notify queue
  through `atomic_write_json` under a lock; give `atomic_write_json` a
  `tempfile.mkstemp` name in the same directory.
- [ ] Verify: `... file tests/admin/test_api_v1_jobs.py`

### Task 18: The SPA shows current data and honest errors

- [ ] `chart.store.ts:89` has no cancellation or request matching, so a slow
  response for the previous ticker renders under the current header —
  `market.py:474` echoes `"ticker"` back **specifically** to prevent this and
  the client ignores it (A-A3). No store but watchlist-suggest uses
  `switchMap`, though `interceptors.ts:79` asserts one does, so an older
  snapshot can replace a newer one and `loading` flips false with a request
  still out (A-A7). A 401's `expire()` effect clears the login error before it
  renders, so a wrong password gives **no feedback** (A-A2).
- [ ] Tests: an out-of-order chart response for a stale ticker is discarded; two
  overlapping `trades` loads leave the newer result; a rejected login still
  shows its message after `ApplicationRef.tick()`.
- [ ] Fix: `switchMap` (or a request-sequence guard) in the affected stores;
  match on the echoed `ticker`; do not let `expire()` clear an error the login
  flow just set.
- [ ] Verify: `npm test` in `frontend/` for the touched specs.

## Phase 7 — Remaining integrity, then verify

### Task 19: Kill-switch release sticks; backtest mirrors the live rule

- [ ] The kill switch has no hysteresis and no manual-release memory, so a
  human `off` is re-tripped by the next scan; the DD ladder has `RESUME_DD_PCT`
  for exactly this (A-T12). `backtest_wf.py:412`'s portfolio dedup mirrors
  `has_open_trade`/`has_similar_open_trade`, which the live path no longer
  calls — the real rule is `open_trade_for_ticker` (one per ticker,
  direction-blind) — and `wf_run.py --portfolio` passes `one_per_ticker=False`,
  so headline walk-forward results model capital the account cannot commit
  (A-T9).
- [ ] Tests: a manual `off` survives the next scan while the trigger condition
  still holds; `collect_portfolio_signals` admits at most one open position per
  ticker regardless of direction.
- [ ] Fix: record a manual release and require re-arming (or a hysteresis
  band) before re-engaging; default the portfolio replay to the live
  one-per-ticker rule and update the docstring's stale citation.
- [ ] Verify: `... file tests/edge/test_throttle.py`

### Task 20: Full-suite verification

- [ ] `python scripts/dev/testrun.py full` — the **only** full run in this plan.
- [ ] Green means `0 failed` **and** `0 xfailed`. The pre-v59 baseline is
  `2360 passed, 66 skipped` (already includes the seven fixes committed as
  `b70027b`, `452864e`, `ffb8297`). A higher passed count is expected; a
  changed count is not a failure, a new `xfailed` is.
- [ ] A red result here is where the fixing starts, not a reason to re-run.
- [ ] Dispatch the `test-runner` subagent so ~1150 progress lines never reach
  the controller's context.
