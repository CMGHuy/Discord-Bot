# v245 — Exact analysis caching: make the live scan cheap per ticker

**Version:** ui 1.47.0 · bot 2.19.6
**Bump:** bot patch
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Panel:** quant-engineer, veteran-trader, staff-engineer

`Edge: none (integrity)`: this spec adds no strategy, filter or exit and
changes no alert. It makes analysis cheaper per ticker, which is one of the
two preconditions for a larger watchlist (`volume`). Growing the watchlist is
a separate partner action (§ Rollout). `Bump: bot patch`: every alert is
byte-identical to today's; only scan time changes.

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

Scans already run back to back. Analysis is the biggest cost. It runs
serially (`fetch.map_tickers` with `SCAN_WORKERS=1`; config.py records that
threads gave no speedup under the GIL), and its cost grows linearly with
tickers × horizons × strategies.

Much of that work is repeated on identical input: every 5 minutes `_scan_one`
(`swingbot/core/scanning/analyze.py:941`) re-detects years of confirmed pivots
and re-runs the O(pivots³) trendline pair search
(`trendlines.custom_scanner_levels`) over them. Only the last few bars and the
live price change between scans.

**Goal:** analysis **≤ 0.7 s per ticker (p50), measured from production
`phases_s`**, with **every alert byte-identical to today's**.

**What this goal does not cover.** A 300-ticker watchlist also needs the
non-analysis phases to scale. At 92 tickers they already total ~93 s
(medians). Scaled linearly to 300 tickers they reach ~305 s before any
analysis runs. That is a rough figure (medians from different scans don't
strictly add up, and `live_prices` is batched), but it makes sub-project B
(fetch path) a **precondition** for growing the watchlist past ~150 tickers
(§ Out of scope).

## Design

### Task 0: profile, tag, fix hot spots without changing behaviour

1. **Profile.** `scripts/perf/profile_analysis.py` replays one scan's frames
   through `_scan_one` under `cProfile` and `tracemalloc`. Inputs: the 92
   production tickers from the local replica's market data, run twice: once
   with no forming bar, and once with a forming bar synthesised from the last
   row (OHLC = last close ± 0.5 ATR) and live price = that close. The script
   reports each candidate's **share** of analysis time. The absolute 0.7 s
   target is judged only from production `phases_s`, because the laptop is not
   the VM under `cpus: 1.0`.
2. **Tag each hot spot** with whether it reads the evaluation (last) row and
   whether it reads `current_price`. Candidates: `custom_scanner_levels`
   (pivot detection, pair search, `_score_candidate`), `_trendln_fallback_levels`,
   `_horizon_scenarios` per horizon, `collect_candidate_levels` per source,
   `_cluster_levels`, `levels.count_confirming_strategies` (called twice per
   scenario over the same `candidates`), `score_confidence`, `get_htf_bias`,
   `macro_aligned`, `adjacent_aligned`, `_rs_pctile`, the E12/E16 screens,
   `_apply_pullback_dryup`, `_apply_headroom`.
3. Write the result to
   `docs/superpowers/results/2026-11-23-v245-analysis-profile.md`: shares, the
   tags, and bytes per cached object (so the cache below gets a memory figure,
   not just an entry count).
4. **Fix hot spots with byte-identical output** first, one commit each.
   Examples: an indicator recomputed per horizon or per strategy that could be
   computed once per frame, or the two `count_confirming_strategies` calls
   sharing one strategy simulation. Characterisation tests (§ Testing) pin the
   output before each fix.
5. **Exit criterion.** If production analysis p50 is ≤ 0.7 s per ticker after
   the Task 0 fixes, the work stops there: the prefix cache below is not
   built, and the spec closes with its results.

### Exact prefix caching (only if Task 0 misses the target)

**The rule:** a computation may be cached only if it is a pure function of a
**prefix** of the frame, `df.iloc[:m]`, where `m = len(df) - W` and `W` is the
widest right-hand window that computation reads (for example, a pivot needs
`k` bars after it to be confirmed, so pivots older than `W = k + 1` bars from
the end never change). Everything that reads the last `W` rows or
`current_price` is recomputed every scan, exactly as today. Output is
therefore identical to today's **at all times**, during market hours or not:
no frozen levels and no session shift.

What the profile is expected to make cacheable, each subject to its tag:

| Cached (prefix-pure) | Recomputed every scan (reads the tail or the price) |
|---|---|
| Confirmed pivots older than the confirmation window | Pivots inside the window, plus the forming bar |
| The trendline pair search over confirmed pivots: **every scored candidate line before the price gates** (slope, intercept, touches, score), kept in the original `i<j` iteration order | Pairs involving any tail pivot; both `current_price` gates in `_score_candidate` (`trendlines.py:235-242`); the best-line pick with the same strict `>` tie-break; evaluation at index `len(df) - 1` of the full frame |
| Any other source the profile shows is prefix-pure **and** can be split without a float difference | `_trendln_fallback_levels`; floor pivots (`levels.py:320`, `iloc[-2]`); rolling S/R and Donchian (`shift(1)`); EMA/ATR/VWAP/Bollinger series (incremental `ewm`/`rolling` is not float byte-identical); `get_htf_bias` and `horizon_trend` (last close); `_cluster_levels` (order-dependent over a candidate set that includes per-scan sources); scenarios, confluence, confidence, requirements |

One code path: the refactored functions take an optional prefix result. With
the cache disabled they compute the prefix themselves. So "cache off" and
today's behaviour are the same code, and there is no second analysis body to
maintain.

**Cache key and invalidation.**
- Key: `(ticker, unit, prefix_fingerprint)`. `unit` names the cached
  computation and, where it is horizon-specific, the horizon. A horizon
  missing from an entry is a **miss** that gets built, never an empty result.
- `prefix_fingerprint` = `m` + the prefix's first-row close + its last row's
  date and OHLCV. A split or dividend restatement, a revised volume, or a
  provisional bar that later changes all produce a new key. Stale prefix
  results are never served.
- Every SIGHUP that changes config clears the whole cache, through the
  existing `_reload_callbacks` registry (`swingbot/bot_core.py:262-293`). No
  hand-kept list of config fields, and no `code_version` (a deploy restarts
  the process anyway).
- No post-close warm-up task. The cache fills on the first scan after a
  restart, which costs one normal-speed scan.

**Storage.** `StructureCache` in a new `swingbot/core/scanning/structure.py`:
- a bounded in-process LRU in the bot process, guarded by a lock;
- `STRUCTURE_CACHE_MAX` (default 600 entries) is re-read on SIGHUP, and the
  cache is resized on the spot;
- Task 0's bytes-per-entry figure sets the default so the worst case stays
  under 150 MB;
- cached objects are frozen (tuples; `Level.sources` copied to a tuple), so
  no caller can mutate a shared entry.

**Call sites.** The live scan (`scan_run.py:754`) and the SHORT extra lane
(`analyze.py:1375`) pass the cache in. `outlook_run` and `scan_replay` call
`_scan_one` unchanged with no cache, so historical replay frames never fill
or evict live entries. The `ScanItem` carries the prefix results it was built
from, the same way it already carries `trendline_candidates`
(`analyze.py:1294`). That way `rescenario` (`analyze.py:1310`, called from
`planning/rebuild.py:143`) never has to look anything up in the cache after
the fact. The cache mode is read once per scan, not once per ticker.

### Knob and shadow check

`ANALYSIS_CACHE = off | shadow | on` in `.env`, hot-reloaded via SIGHUP,
default `off`. Since output must be identical, `shadow` is a pure bug
detector, not a behaviour study:

- `off`: no cache.
- `on`: cache.
- `shadow`: the cached path is authoritative. On a rotating third of the
  watchlist per scan (each ticker every third scan), the same ticker is also
  run with the cache disabled, and the results are compared field by field:
  - is there a scenario at all, entry / stop / TP, both confluence counts,
    `conf.level`, `conf.score`;
  - each requirement's `passed`, `all_ok`;
  - the trendline candidates.

  **Any difference is a bug.**

The comparison run has no side effects:
- a `ScanIO` with no `monitor_scan` (open trades are monitored once), and
  `track_record` answered from the authoritative run's own results;
- `progress=None`, and its log lines at DEBUG, so ops greps such as
  "plan rejected (" don't double-count;
- the same `now` and `current_price` as the authoritative run, both captured
  once per scan.

A comparator exception is logged and swallowed; it never touches posting.

Output, written in `shadow`:
- per scan, into `scan_telemetry`: `cache_compared` and `cache_diffs`;
- per diff: one JSON line in `logs/analysis_cache_shadow.jsonl`, with a size
  cap of 20 MB × 3.

### Switch criteria

- `shadow` runs for **5 trading days, with zero diffs**.
- A single diff is a bug: fix it, deploy, and restart the count.
- Then switch to `on`, and measure analysis p50 per ticker in production
  over one trading day.

### Observability (built into this spec)

- `phases_s` gains `analysis_prefix` (time spent building cache entries).
- `scan_telemetry` gains `cache_hits`, `cache_misses`, `cache_evictions`,
  `cache_entries`, and **`rss_mb`** (the bot process's resident memory at the
  end of the scan, from `/proc/self/status`; `None` where unavailable).
- The scan summary line logs the hit and miss counts at INFO.
- A build failure is logged at WARNING with the ticker; that ticker then
  computes without the cache for this scan.

### Error handling

- If a prefix build fails, the failure is logged and that ticker is computed
  uncached. Nothing is stored, so the next scan retries.
- A fingerprint mismatch means a rebuild, never a stale result.
- A comparator failure in `shadow` is logged and swallowed.

## Testing

All under the existing scanning and market suites; no new `tests/`
directory.

- **Characterisation, written before any refactor.** Golden `_scan_one`
  outputs on fixture frames:
  - all 10 horizons, both directions, `mtf_adjacent_gate` on and off;
  - a ticker below `MIN_BARS` for some horizons, and `df is None`;
  - each frame with and without a forming bar;
  - `current_price` at the close, gapped through entry, through stop and
    through target, plus a stale print far from the close.

  Every Task 0 fix and the prefix refactor must keep these byte-identical.
- **Prefix property test.** Over successive truncations `df.iloc[:n]` of a
  long fixture frame, with varying `current_price`, the cache-on result equals
  the cache-off result, with the cache carried across `n` the way scans carry
  it across days. That includes a half-day frame and a frame whose last row is
  yesterday.
- **Trendline split.** The stored pre-gate candidates, re-gated and re-picked,
  equal `_find_best_trendline` on the full frame, including ties and a
  candidate rejected by each price gate.
- **Cache.**
  - hit on the same key;
  - miss on a changed prefix fingerprint: new bar, restated history, revised
    last-prefix volume;
  - miss on a horizon absent from the entry;
  - cleared on a config-changing SIGHUP;
  - resized when `STRUCTURE_CACHE_MAX` changes;
  - LRU eviction;
  - concurrent get and put from two threads.
- **Immutability.** Two scans with different prices against one entry return
  independent results, and the entry deep-equals itself before and after,
  `Level.sources` included.
- **Shadow comparator.**
  - equal inputs give zero diffs;
  - each compared field gives exactly one diff when changed;
  - the comparison run makes no journal write and no progress write;
  - an exception does not propagate.
- **`rescenario`.** Same result from the item's carried prefix results as
  from a fresh computation.

## Rollout

1. Task 0: profile, write the results doc, ship the byte-identical fixes,
   measure in production. Stop here if the exit criterion is met.
2. Deploy the prefix cache with `ANALYSIS_CACHE=off`.
3. Switch to `shadow` for 5 trading days (zero diffs).
4. Switch to `on`, measure, and record `## Results` in this spec.
5. **Watchlist growth is not part of this spec.** It needs sub-project B as
   well. When it happens, it goes in steps, each held a full trading day with
   scan p90 < 300 s.
6. **Rollback.**
   - Before any growth, `ANALYSIS_CACHE=off` alone is a full rollback (same
     output, slower).
   - After growth, `off` would bring back ~3.2 s per ticker on a bigger
     list. So the rollback is to switch `off` **and** shrink the watchlist to
     the last size whose p90 was under 300 s without the cache (92 today).
   - The partner shrinks the watchlist; the bot keeps the removed tickers'
     open trades monitored, as it does today for any removal.
7. **Removal of the shadow scaffolding.** Once `on` has run for 10 trading
   days with no incident, a follow-up commit deletes the `shadow` mode, the
   comparator and the jsonl. That leaves `off`/`on` (kept as the rollback
   switch). The owner is whoever closes this plan out.

## Deferred alternative: frozen completed-bar structure

The first draft of this spec cached all structure on completed bars once per
session day. The panel showed that this is a real behaviour change, and a
messier one than "levels stop moving intraday":
- floor pivots, rolling S/R, Donchian and the HTF bias index the last row by
  position, so during market hours they would shift back a full session;
- trendline scoring gates on `current_price`;
- the shadow soak could not tell that shift from a benign difference.

That design comes back to the partner as its own decision **only if** exact
caching misses the 0.7 s target. It would then need, per level source, the
session it must read while a bar is in progress, and the tradeability rules
the veteran-trader seat listed (levels already pierced by today's bar, plans
already posted, switching outside a session).

## Out of scope (later sub-projects, each its own spec)

- **B. Fetch path and quote freshness.** Precondition for watchlist growth.
  - Every bounded fetch spawns a fresh Python interpreter
    (`fetch._run_bounded`), including one per remainder ticker, serially.
  - Live prices mostly come from old yfinance prints or are missing (prod,
    3 days: alpaca 2,441 · yfinance-old-print 3,592 · none 1,294).
  - Rate-limit headroom needs re-checking at 300 tickers
    (`YF_BUDGET_PER_MINUTE=60`, `ALPACA_BUDGET_PER_MINUTE=150`).
- **C. Resource guardrails.**
  - No memory limits on the bot, admin or db containers.
  - Never pruned: `scan_telemetry.jsonl` (8.6 MB, re-read in full by
    `recent_telemetry` every scan), `exports/` (531 MB) and
    `market_fetch_counts` (5,487 rows).
  - The 256-entry `_normalized_frame_cache` thrashes past 256
    ticker×timeframe pairs.
  - This spec adds only the `rss_mb` gauge.
- **D. Event logging.**
  - The refresher logs to stdout only.
  - Spawned processes lose `scan_id`.
  - Logs are plain text with no event catalogue.
  - Provider calls carry no latency log.
- **A process pool for analysis.** Revisit only if caching misses the
  target; the bot's `cpus: 1.0` cap and the admin's ~77 % CPU on a 2 vCPU host
  limit what it can gain.

## Panel review

Panel of 2026-11-23 on the first draft (ae1ba761): frozen completed-bar
structure, cached once per session day. The partner then chose to redesign
exact-first. Findings that only applied to the frozen design are recorded
as resolved by that redesign.

**BLOCKING**
- quant-engineer: trendline candidate lines depend on `current_price` (`trendlines.py:216-242`), so a cached best line breaks parity even with no forming bar -- applied: the pre-gate candidates are cached in iteration order; price gates and the pick stay per scan.
- quant-engineer: the `_trendln_fallback_levels` per-horizon fallback is unowned by either stage -- applied: recomputed every scan.
- quant-engineer + veteran-trader: the cache key lacks a content/provenance part (scan straddling the close, revised volume, split restatement) -- applied: `prefix_fingerprint` in the key.
- veteran-trader: dropping the forming bar shifts positional sources (floor pivots, rolling S/R, HTF bias) back a full session, inside the shadow's blind spot -- applied: the exact-first redesign never drops a bar; those sources are recomputed every scan.
- staff-engineer: rollback by `off` stops working once the watchlist has grown -- applied: § Rollout step 6.
- staff-engineer: the shadow side would re-run journal writes, progress, INFO logs and a shifted `track_record` -- applied: side-effect-free comparison run.

**ADVISORY**
- quant-engineer: positional `iloc` sources change meaning on `completed_df`, so they need a truncation test -- applied: they are recomputed per scan; the prefix property test runs over truncations.
- quant-engineer: HTF/macro bias reads the last close -- applied: recomputed per scan.
- quant-engineer: the in-progress rule would be a third implementation that disagrees on half days and pre-open -- applied: the redesign needs no in-progress rule.
- quant-engineer: capture `now` once per scan for both paths -- applied.
- quant-engineer: a trendline evaluated at the wrong index makes levels a bar stale -- applied: evaluated at `len(df) - 1` of the full frame, pinned by the trendline-split test.
- quant-engineer: the fingerprint and caching unit were unspecified -- applied: config changes clear the cache via SIGHUP; `unit` includes the horizon.
- quant-engineer: `_cluster_levels` is order-dependent, and `Level.sources` is mutable -- applied: clustering stays per scan; sources are frozen; the immutability test deep-checks them.
- quant-engineer: outlook caller unnamed, and intraday output has no backtest counterpart -- applied: outlook and replay take no cache; with identical output, intraday parity is unchanged from today.
- quant-engineer: the "15 %" shadow cost was unmeasured -- applied: shadow samples a rotating third; cost is recorded via `analysis_prefix` and scan duration.
- veteran-trader: levels already pierced by today's bar go unflagged -- rejected: no behaviour change here; carried into § Deferred alternative.
- veteran-trader: no gap, half-day or stale-print cases -- applied: added to the characterisation and property tests.
- veteran-trader: a 5-day soak sees few regimes; report outcomes too -- rejected: with identical output the soak is a bug detector, not a behaviour study; carried into § Deferred alternative.
- veteran-trader: switching mid-session could re-level posted plans -- rejected: identical output, so no re-levelling; carried into § Deferred alternative.
- veteran-trader: half days and a lagging feed could misclassify the in-progress bar -- applied: no in-progress rule; covered by the half-day and yesterday-last-row truncations.
- veteran-trader: pin the config fingerprint's field list -- applied differently: any config-changing SIGHUP clears the cache, so there is no list.
- staff-engineer: horizons and hard_filters missing from the key -- applied: `unit` includes the horizon; a missing horizon is a miss; hard_filters are config, cleared on SIGHUP.
- staff-engineer: dispatching inside `_scan_one` would pull in outlook and replay -- applied: the cache is passed only at the two live call sites.
- staff-engineer: `rescenario` would look up the cache later -- applied: `ScanItem` carries its prefix results; the mode is read once per scan.
- staff-engineer: hand-kept fingerprint list; `code_version` useless; resize on SIGHUP -- applied.
- staff-engineer: cache bounded by entries only, and no RSS gauge -- applied: Task 0 measures bytes per entry; `rss_mb` added to telemetry.
- staff-engineer: the warm-up task races scans and duplicates `next_session_scan` -- applied: warm-up dropped.
- staff-engineer: two analysis bodies and shadow scaffolding with no owner -- applied: one code path with an optional prefix result; § Rollout step 7 removes the shadow scaffolding.
- staff-engineer: Task 0 had no exit criterion and no machine stated -- applied: exit criterion, local shares, and the target judged from production.
- staff-engineer: exact prefix caching is feasible for a subset only and should come first -- applied: it is the design now.
- staff-engineer: non-analysis phases alone reach ~305 s at 300 tickers -- applied: the goal is restated, and sub-project B is named as a precondition for growth.
