# v245 — Two-stage analysis: scale the live scan to ~300 tickers

**Version:** ui 1.47.0 · bot 2.19.6
**Bump:** bot minor
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Panel:** quant-engineer, veteran-trader, staff-engineer

`Edge: none (integrity)` because this spec buys no edge itself: it adds no
strategy, filter or exit. It is the precondition for a later watchlist increase
(`volume`), which is a separate step (§ Rollout, step 7). `Bump: bot minor`
because alerts posted during market hours can differ (levels no longer move
with the in-progress bar). The partner sees that difference, even though most
of the work is internal.

## Why

Production, 2026-11-21..23 (84 scans, 92 watchlist tickers, `SCAN_WORKERS=1`,
bot capped at `cpus: 1.0` on a 2 vCPU / 3.8 GB VM), from
`data/scan_telemetry.jsonl`:

| Measure | Value |
|---|---|
| Scan duration median / p90 / max | 385 s / 483 s / 607 s, against `SCAN_INTERVAL_MINUTES=5` (300 s) |
| `phases_s.analysis` median | 293.5 s (76 % of the scan), about 3.2 s per ticker |
| `crawl` / `live_prices` / `enrichment` medians | 46.2 s / 23.1 s / 24.2 s |
| `cold_fetch_s` p50 / p95 | 1.11 s / 1.21 s |
| Market-data 429s, Alpaca breaker trips (7 days of logs) | 0 / 0 |

Scans already run back to back. Analysis is the wall. It runs serially
(`fetch.map_tickers` with `SCAN_WORKERS=1`; config.py records that threads gave
no speedup under the GIL), and its cost grows linearly with tickers ×
horizons × strategies. Rate limits and fetch latency are not the problem today;
they belong to later sub-projects (§ Out of scope).

Most of the per-scan work repeats itself. During market hours the daily frame
passed to `analyze._scan_one` (`swingbot/core/scanning/analyze.py:941`) ends
with **today's in-progress bar**, so every 5 minutes the bot recomputes pivots,
trendline candidates (`trendlines.custom_scanner_levels`, O(pivots³), measured
6-9 s on long histories before v56 bounded it), every strategy's candidate
levels for 10 horizons, and the HTF/macro EMA bias. All of that comes from
years of completed bars plus one bar that is still forming. The completed part
changes once a day.

**Goal:** a full live scan of **~300 tickers fits inside the 5-minute interval**
on the current VM. Analysis must drop from ~3.2 s to **≤ 0.7 s per ticker
(p50)**.

## Design

### Task 0 comes first: profile, then fix hot spots without changing behaviour

The 293 s has never been broken down by function. Before anything is cached:

1. A profiling script (`scripts/perf/profile_analysis.py`) replays one session
   scan's frames through `_scan_one` under `cProfile`. Inputs: the 92
   production tickers, frames captured from the local replica's market data
   cache with an in-progress bar synthesised from the last row (OHLC = last
   close ± 0.5 ATR), live prices = that close. Output: cumulative time per
   function, grouped into the candidates below. The result is written to
   `docs/superpowers/results/2026-11-23-v245-analysis-profile.md`.
2. Candidates to attribute: `custom_scanner_levels`, `_horizon_scenarios` per
   horizon, `levels.count_confirming_strategies` (it simulates every strategy
   and is called twice per scenario, once for target and once for stop, over
   the same `candidates`), `score_confidence`, `get_htf_bias`,
   `macro_aligned`, `adjacent_aligned`, `_rs_pctile`,
   `universe.liquidity_reason`, `universe.data_quality_issues`,
   `_apply_pullback_dryup`, `_apply_headroom`.
3. Any hot spot fixable **with byte-identical output** ships first, as its own
   commits. Examples: indicators recomputed per horizon or per strategy that
   could be computed once per frame, or the two `count_confirming_strategies`
   calls sharing one strategy simulation. These fixes also make room for the
   shadow run's extra cost (§ Shadow mode).

The profile also settles exactly which functions move into Stage 1. The table
below is the design intent. The profile can move a function from Stage 2 to
Stage 1 only if that function provably does not read the in-progress bar or
the price.

### The two stages

| Stage 1: structure | Stage 2: trigger |
|---|---|
| Input: **completed bars only**, i.e. `df` without the in-progress bar | Input: the Stage 1 structure + the full `df` (in-progress bar included) + `current_price` |
| Runs once per ticker per session day, on a cache miss | Runs every scan for every ticker |
| Every strategy's raw candidate levels per horizon (the price-independent part of `_horizon_scenarios` / `collect_candidate_levels`); pivots and trendline candidate *lines* (`custom_scanner_levels` split into line fitting, Stage 1, and evaluation at today's price, Stage 2); fib legs; volume profile; `get_htf_bias`, `macro_aligned`, `adjacent_aligned` inputs; RS-percentile inputs | Nearest-level selection relative to `current_price`; scenario build (entry, stop, TP, tight-stop, ATR floor); `_apply_pullback_dryup`; `_apply_headroom`; confluence counting within `confluence_deviation_pct`; `score_confidence`; `_build_requirement_checks`; `ScanItem` assembly |
| Cache key: `(ticker, last_completed_bar_date, config_fingerprint, code_version)` | Not cached |

Open-trade SL/TP monitoring (`io.monitor_scan`) and the E12 liquidity and E16
data-quality screens stay where they are, on the full `df`, every scan.
Monitoring must react to the in-progress bar and the live price, and the
screens are cheap. The confirmation debounce stays serial after the join, as
today. `rescenario` (v171 D5) rebuilds a scenario at a new price. It calls the
same Stage 2 function with the item's cached structure, so it never pays for
Stage 1.

**In-progress bar rule.** The last row of `df` is in progress when its date is
today in America/New_York, today is a session (`calendar.is_session`), and
`now_et() < session.session_close(today)` (`swingbot/core/market/session.py:229`,
which handles half days). This matches `compression_context._signal_day`. One
helper, `split_in_progress(df, now) -> (completed_df, in_progress_row | None)`,
lives in `swingbot/core/scanning/` and is the only place the rule is written.
Outside a session nothing is in progress, so `completed_df is df`.

**Hard parity invariant.** When `in_progress_row is None`, the two-stage
output is **byte-identical** to today's `_scan_one` output: the same
`ScanItem` list, same order, same fields, same `stats`. Tests pin it
(§ Testing). Shadow mode measures it in production (switch criterion 1).
Backtests and replays evaluate at the close, so this invariant is also why
they need no re-run.

**Where it lives.** A new module `swingbot/core/scanning/structure.py` holds
the Stage 1 builder (`build_structure(ticker, completed_df, horizons,
hard_filters) -> TickerStructure`), the frozen `TickerStructure` dataclass
(tuples, not lists; Stage 2 never mutates it), and `StructureCache`. The Stage
2 function is extracted from `_scan_one`, which becomes a thin dispatcher on
the mode (§ Shadow mode). Every new and changed function stays below
cyclomatic complexity 15.

**The cache.** `StructureCache` is a bounded in-process LRU in the bot process
(`max_entries` = `STRUCTURE_CACHE_MAX` in `config.py`, default 600, i.e.
2 × the 300 target). It is guarded by a lock for the extra-lane caller, and
logs every eviction. It is not stored in Postgres: a restart costs one full
scan, and persisting every strategy's level objects would add an Alembic
migration and a serialisation format for no measured gain (revisit only if
restarts during market hours become common). `config_fingerprint` is a hash
of the config fields the Stage 1 builder reads, recomputed on SIGHUP, so a hot
config change invalidates the cache without a restart. `code_version` is
`VERSION.json`'s bot version.

**Post-close warm-up.** A bot loop task, once per session day after
`session_close + 30 min`, builds Stage 1 for every watchlist ticker against
the day's now-completed bars. It runs in `asyncio.to_thread` and is skipped if
a scan is running. That way the first pre-market scan is a cache hit. It logs
its duration, the ticker count and the miss count.

**Scope of the switch.** Only the live scan (`_sync_run_scan`) and the SHORT
extra lane (V118-4, `ExtraScanContext`) use two-stage. The replay and backtest
`io` paths (V118-7) keep calling the single-stage body. Both are evaluated at
the close, where the two paths are identical by the invariant.

### Shadow mode

Config knob `ANALYSIS_TWO_STAGE = off | shadow | on` in `.env`, hot-reloaded
via SIGHUP, default `off`. Rollback is `off`, with no deploy.

- `off`: today's path only.
- `shadow`: today's path stays authoritative and is the only one that posts.
  For each ticker the two-stage path runs on the same `df`, `current_price`,
  regime, filters and `rs_cache`. A comparator matches results on
  `(ticker, horizon_key, direction)` and compares: is there a scenario at all,
  entry / stop / TP (rounded to the cent), `target_confluence[0]`,
  `stop_confluence[0]`, `conf.level`, `conf.score`, each requirement's
  `passed`, `all_ok`. Each diff records whether `in_progress_row` was present.
- `on`: two-stage only.

Output, written in `shadow`:
- per scan, into `scan_telemetry`: `shadow_compared`, `shadow_diffs`,
  `shadow_diffs_no_in_progress`, `shadow_diffs_qualifying` (`all_ok` on either
  side);
- per diff: one JSON line in `logs/two_stage_shadow.jsonl` with the scan id,
  key, both sides' fields, and `in_progress` (bounded with a
  RotatingFileHandler-style size cap, 20 MB × 3);
- daily: `scripts/reports/two_stage_shadow_report.py` reads the jsonl and
  prints counts per field and per horizon, plus every qualifying diff for
  hand classification.

**Shadow cost.** The extra two-stage run adds roughly 15 % to scans that
already overrun. That is why Task 0's hot-spot fixes ship before shadow
starts. If shadow pushes scan p90 past 600 s, the comparator samples a
rotating third of the watchlist per scan instead of every ticker (each ticker
is still compared every third scan).

### Switch criteria (fixed before the soak)

The soak is 5 trading days in `shadow`. Switching to `on` requires all of:

1. **Zero diffs** on scans with no in-progress bar (`shadow_diffs_no_in_progress`
   = 0 summed over the soak). A single diff is a bug: fix it, deploy, and
   restart the 5-day count.
2. Every diff on an **alert-qualifying** item is classified by hand as either
   `in-progress-bar` (the level or score moved because Stage 1 no longer sees
   today's forming bar) or `bug`. **Zero `bug` diffs.**
3. The share of qualifying items that differ is **reported, not thresholded**.
   The partner decides on the report. This is integrity work and claims no
   lift, so no lift gate applies.

Then, under `on`: analysis p50 per ticker ≤ 0.7 s, measured from
`phases_s.analysis_stage1 + analysis_stage2` over one trading day.

### Observability (built into this spec)

- `phases_s` gains `analysis_stage1` and `analysis_stage2` (summed per scan).
- `scan_telemetry` gains `structure_cache_hits`, `structure_cache_misses`,
  `structure_cache_evictions`, and the shadow counters above.
- Stage 1 logs each miss once at DEBUG, with ticker, key and build ms; the scan
  summary line logs hit/miss counts at INFO.
- The warm-up logs start, end, duration and counts at INFO; a failure logs at
  WARNING with the ticker, and the scan falls back to building on a miss.

### Error handling

- If a Stage 1 build fails for a ticker, the failure is logged at WARNING and
  that ticker falls back to the single-stage body for this scan. Nothing is
  cached, so the next scan retries.
- If the comparator raises in `shadow`, the exception is logged and swallowed.
  It never affects the authoritative path or posting.
- On a cache-key mismatch (new bar date, config change, deploy), the entry is
  rebuilt; stale structure is never served.

## Testing

All under the existing scanning suite (`tests/scanning/`); no new `tests/`
directory.

- **Parity:** byte-identity between two-stage and `_scan_one` on fixture frames
  with no in-progress bar, across all 10 horizons, both directions, with
  `mtf_adjacent_gate` on and off, including a ticker below `MIN_BARS` for some
  horizons and the `df is None` case.
- **In-progress rule:** `split_in_progress` on a regular session before and
  after the close, a half day, a weekend, a holiday, and a frame whose last row
  is yesterday.
- **Cache:** hit on the same key; miss on a new bar date, a changed config
  fingerprint (simulated SIGHUP) and a changed code version; LRU eviction at
  `max_entries`; concurrent get/put from two threads.
- **Immutability:** Stage 2 run twice against one `TickerStructure` with
  different prices gives independent results, and the structure is unchanged
  (a deep equality check before and after).
- **Shadow comparator:** equal inputs give zero diffs; each compared field
  produces exactly one diff when changed; a comparator exception does not
  propagate.
- **Fallback:** a Stage 1 build that raises gives the single-stage result for
  that ticker and caches nothing.
- **`rescenario`:** gives the same result through Stage 2 as before, with no
  in-progress bar.
- **Report script:** empty jsonl, one diff, and mixed in-progress rows.

## Rollout

1. Task 0: profile, write the results doc, ship the byte-identical hot-spot
   fixes.
2. Deploy two-stage with `ANALYSIS_TWO_STAGE=off`.
3. Switch to `shadow` for 5 trading days.
4. Review the shadow report against the switch criteria.
5. Switch to `on` and measure analysis p50 per ticker.
6. Record the results in this spec's `## Results`.
7. Grow the watchlist only after step 6, in steps (150, then 225, then 300
   tickers), checking scan p90 < 300 s for a full trading day at each step.
   Watchlist growth is a partner action, not a plan task.

## Out of scope (later sub-projects, each its own spec)

- **B. Fetch path and quote freshness.** Every bounded fetch spawns a fresh
  Python interpreter (`fetch._run_bounded`), including one per remainder
  ticker, serially. Live prices come mostly from old yfinance prints or are
  missing entirely (prod 3 days: alpaca 2,441 · yfinance-old-print 3,592 ·
  none 1,294). Rate-limit headroom also needs re-checking at 300 tickers
  (`YF_BUDGET_PER_MINUTE=60`, `ALPACA_BUDGET_PER_MINUTE=150`).
- **C. Resource guardrails.** No memory limits on the bot, admin or db
  containers, and no memory (RSS) telemetry. Things that are never pruned:
  `scan_telemetry.jsonl` (8.6 MB, re-read in full by `recent_telemetry` every
  scan), `exports/` (531 MB) and `market_fetch_counts` (5,487 rows). The
  256-entry `_normalized_frame_cache` will thrash past 256 ticker×timeframe
  pairs.
- **D. Event logging.** The refresher logs to stdout only. Spawned processes
  lose `scan_id`. Logs are plain text with no event catalogue, and provider
  calls carry no latency log.
- A process pool for analysis. Revisit only if Stage 2 alone misses the
  0.7 s target; the bot's `cpus: 1.0` cap and the admin's ~77 % CPU on a
  2 vCPU host limit its benefit.
