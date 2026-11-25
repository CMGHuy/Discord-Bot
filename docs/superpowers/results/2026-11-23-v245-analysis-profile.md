# v245 — Analysis profile (Task 0)

**Spec:** [2026-11-23-v245-exact-analysis-cache-design.md](../specs/2026-11-23-v245-exact-analysis-cache-design.md)
**Plan:** [index](../plans/2026-11-23-v245-exact-analysis-cache_0-index.md), task V245-3
**Run:** 2026-11-25 UTC, commit 7ff5b26b, 92 tickers from the local replica's watchlist (`swingbot_prod_replica`, MATCH at alembic v228_001), 66 profiled (26 without a local frame: APLD, APP, ASML, COHR, COIN, CVX, FLY, HD, HPQ, IBM, LLY, LRCX, NOV, ONDS, QCOM, RGTI, RIOT, SMCI, SPCX, TTD, UNH, VRT, VST, WDC, XAGUSD, XAUUSD), frames trimmed to 2515 bars (median 2515), horizons 2w..9m, 12th Gen Intel Core i7-1255U.

Shares are local and relative. The 0.7 s per ticker target is judged only
from production `phases_s` (V245-6), never from these numbers.

Raw outputs (not committed, `logs/` is ignored): `logs/v245-profile/chunk-00..04.json`
with their `-completed.prof` / `-forming.prof`, `journal-00.json`, `merged.json`,
`top45.txt`, `callers.txt`. The profile ran in five persisted chunks of 20
watchlist tickers; a chunk's tickers without a local frame are skipped, which
is why chunks hold 15, 15, 17, 14 and 5 profiled tickers.

## Shares

Calls are per profiled ticker (66). 9.85 rather than 10 per-horizon calls: one
ticker stops at the E16 data-quality screen (65 `custom_scanner_levels` calls)
and short frames skip the horizons their `MIN_BARS` excludes.

| Candidate | Completed share | Completed calls/ticker | Forming share | Forming calls/ticker |
|---|---|---|---|---|
| `_scan_one` | 100 % | 1.00 | 100 % | 1.00 |
| `_horizon_scenarios` | 68.6 % | 9.85 | 69.9 % | 9.85 |
| `collect_candidate_levels` | 60.1 % | 9.85 | 61.1 % | 9.85 |
| `custom_scanner_levels` | 28.4 % | 0.98 | 27.5 % | 0.98 |
| `_find_best_trendline` | 28.3 % | 1.97 | 27.5 % | 1.97 |
| `_score_candidate` | 21.1 % | 2755.39 | 20.5 % | 2752.24 |
| `atr_floor_pct` | 8.0 % | 9.85 | 8.3 % | 9.85 |
| `atr` | 7.9 % | 9.88 | 8.2 % | 9.86 |
| `_volume_confirmed_pivots` | 6.4 % | 1.97 | 6.1 % | 1.97 |
| `bollinger_bands` | 4.6 % | 9.91 | 4.7 % | 9.88 |
| `zigzag_pivots` | 4.3 % | 11.82 | 4.2 % | 11.82 |
| `rolling_vwap` | 3.8 % | 9.85 | 3.9 % | 9.85 |
| `data_quality_issues (E16)` | 1.8 % | 1.00 | 1.8 % | 1.00 |
| `ema` | 1.2 % | 19.73 | 1.3 % | 19.74 |
| `fibonacci_levels` | 1.1 % | 9.85 | 1.1 % | 9.85 |
| `_fvg_candidates` | 0.7 % | 9.85 | 0.8 % | 9.85 |
| `build_level_map` | 0.4 % | 9.85 | 0.4 % | 9.85 |
| `_cluster_levels` | 0.3 % | 9.85 | 0.3 % | 9.85 |
| `_apply_pullback_dryup` | 0.2 % | 9.85 | 0.2 % | 9.85 |
| `score_confidence` | 0.6 % | 0.03 | 0.1 % | 0.02 |
| `liquidity_reason (E12)` | 0.2 % | 1.00 | 0.1 % | 1.00 |
| `build_scenarios` | 0.1 % | 9.85 | 0.1 % | 9.85 |
| `trendline_levels` | 0.0 % | 9.85 | 0.0 % | 9.85 |
| `_apply_headroom` | 0.0 % | 9.85 | 0.0 % | 9.85 |
| `veto_bullish_for` | 0.0 % | 9.85 | 0.0 % | 9.85 |
| `macro_aligned` | 0.0 % | 0.03 | 0.0 % | 0.02 |
| `_band_live` | 0.0 % | 9.85 | 0.0 % | 9.85 |
| `get_htf_bias` | 0.0 % | 0.03 | 0.0 % | 0.02 |
| `count_confirming_strategies` | 0.0 % | 0.06 | 0.0 % | 0.03 |
| `_trendln_fallback_levels` | 0.0 % | 0.00 | 0.0 % | 0.00 |
| `_build_requirement_checks` | 0.0 % | 0.03 | 0.0 % | 0.02 |
| `adjacent_aligned` | 0.0 % | 0.00 | 0.0 % | 0.00 |
| `_rs_pctile` | 0.0 % | 0.98 | 0.0 % | 0.98 |
| `track_record (journal)` | 0.0 % | 0.00 | 0.0 % | 0.00 |

Local cost: 0.355 s/ticker completed (23.429 s over 66 tickers), 0.353 s/ticker
forming (23.304 s). Scenarios are rare on these frames (2 scenarios over 66
tickers on the completed run, 1 on the forming run), so every per-scenario
candidate (`count_confirming_strategies`, `score_confidence`, `get_htf_bias`,
`macro_aligned`, requirements) is near zero here; the cost is per horizon, not
per scenario. Journal track record (`journal-00.json`, chunk 00's 15 tickers
with `JOURNAL_IO`): completed 4.914 s (0.328 s/ticker, no scenario, no
track-record call); forming 12.653 s (0.844 s/ticker) of which the single
`_live_track_record` call took 5.783 s (45.7 % of that run). One call is not a
rate: it includes the first database read of the process (engine and
connection set-up against the local replica), so it is an upper bound for a
cold read, not a per-scenario steady cost; production pays it per scenario
through `TradeLog.get_stats`. Not measured: `update_open_trades` /
`_check_near_close` (they write the journal, so the profiler runs `QUIET_IO`);
production pays them per ticker inside the analysis phase.

**Largest hot spot outside `CANDIDATES`.** `compute_hvn_level` ->
`compute_volume_profile` (signals.py:585, called from levels.py:360 once per
horizon) costs 8.836 s of the 23.304 s forming run: **37.9 %**, more than the
whole trendline search. Almost all of it is the Python row loop over the
`sr_lookback` window (signals.py:634): `DataFrame.iterrows()` 6.139 s over
89,050 rows plus 1.961 s of per-row `row["High"]`-style Series lookups, summed
over all 66 tickers. Its windows differ per horizon (`sr_lookback` 10..270 on
2w..9m, all distinct), so no two calls share inputs and no byte-identical fix
in this plan's sense (remove an equal-input call) applies; it is not prefix-pure
either (see Tags). A vectorised rewrite is a reformulation, outside spec § Task 0
step 4's rule, and is recorded here for a separate decision, not ranked below.

## Tags

| Candidate | Last row | `current_price` | Prefix-pure | Evidence |
|---|---|---|---|---|
| `custom_scanner_levels`, `_find_best_trendline` | y | y | split -> U1 | `n_bars = len(df)` (trendlines.py:297), `line_at_now` at `n_bars - 1` (trendlines.py:231), side gates against `current_price` (trendlines.py:235-238), `current_price <= 0` guard (trendlines.py:362); `df.tail(MAX_PIVOT_SCAN_BARS)` (trendlines.py:287) |
| `_volume_confirmed_pivots`, `zigzag_pivots` | y | n | pivots older than the confirmation window only | zigzag walks every close to `n - 1` and its last pivot is the unconfirmed running extreme (indicators.py:97-129); volume average `rolling(...)` reads to the last row (trendlines.py:169); no price argument (trendlines.py:142) |
| `_score_candidate` | y | y | n | `line_at_now` at `n_bars - 1` (trendlines.py:231), price gates (trendlines.py:235-238), slope cap `/ current_price`, `recency = last_touch_bar / (n_bars - 1)` (trendlines.py:258) |
| `trendline_levels`, `_trendln_fallback_levels` | y | y | n | `current_price <= 0` guard (trendlines.py:401), fallback reads `df.tail(window_bars)` and evaluates at `current_price` (trendlines.py:506, 520); spec table: never cached |
| `_horizon_scenarios`, `build_level_map`, `_cluster_levels`, `build_scenarios` | y | y | n | split at `current_price` (levels.py:590), scenarios built from `current_price` (levels.py:691), candidate set includes per-scan sources (`iloc[-1]` EMAs, levels.py:231) |
| `collect_candidate_levels` | y | y | n | `ema(...).iloc[-1]` (levels.py:231), rolling S/R `.iloc[-1]` (levels.py:263), floor pivots from `df.iloc[-2]` (levels.py:320), trendlines at `current_price` (levels.py:339) |
| `_fvg_candidates` | y | n | n | `find_fair_value_gaps(df, mode=mode, k=k)` (levels.py:193) takes no price; the fill check reads every bar after the gap up to the last row (fvg.py:132-135, 145-148) |
| `atr_floor_pct` | y | y | n | `atr(df, 14).iloc[-1] / current_price` (levels.py:657-660) |
| `count_confirming_strategies` | n (given `candidates`) | y | n | pure over `candidates` and `target_price` (levels.py:541); `current_price` only reaches it through `candidates` and the fallback `collect_candidate_levels` call (levels.py:538) |
| `score_confidence`, `_build_requirement_checks` | y | y | n | factors read `df` and the scenario (confidence.py:681-690); `_build_requirement_checks` takes no frame, only the scenario, confluence and confidence (requirements.py:38-40): its last-row and price dependence arrive through those inputs |
| `get_htf_bias`, `macro_aligned`, `adjacent_aligned` | y | n | n | `last_close = df["Close"].iloc[-1]` (regime.py:75); `fast_series.iloc[-1] > slow_series.iloc[-1]` (mtf.py:47) |
| `_rs_pctile`, E12 `liquidity_reason`, E16 `data_quality_issues` | y | n | n | `rs_percentile(stock, spy, ...)` over the frames' tails (analyze.py:760); `last_close = df["Close"].iloc[-1]` (universe.py:70); `df.tail(QUALITY_CHECK_LOOKBACK_BARS)` (universe.py:276) |
| `_apply_pullback_dryup`, `_band_live` | y (`now`) | `_band_live` y | n | `completed_frame(df, now or datetime.now(...))` (analyze.py:836, 873); `band_for(frame, current_price, k)` (analyze.py:877); `_band_live` returns before reading anything when `k <= 0` (analyze.py:869), the local config's value, hence 0.0 % |
| `_apply_headroom` | n | y (scenarios) | n | reads only scenarios, supports, resistances (analyze.py:824) |
| `veto_bullish_for` | y (when on) | n | n | returns before reading `df` while `DEAD_CAT_BOUNCE_VETO` is off (analyze.py:69), the local config's value, hence 0.0 %; on, `dead_cat_bounce(df, ...)` once per horizon on the same frame |
| `ema`, `atr`, `rolling_vwap`, `bollinger_bands`, `fibonacci_levels` | y | n | n | series end at the last row; `ewm`/`rolling` incremental updates are not float byte-identical (spec § Exact prefix caching table); `fibonacci_levels` takes `df.iloc[-lookback:]` (indicators.py:48) |
| `compute_hvn_level` (not in `CANDIDATES`) | y | n | n | `window = df.iloc[-lookback:]` and bin edges from that window's own Low/High (signals.py:623-627): the forming bar moves every bin edge |

Step 4 suspects, settled with the numbers (forming run, 66 tickers):

- **Two identical zigzags in the trendline search: confirmed, but small.**
  `_volume_confirmed_pivots` runs twice per ticker (1.97 calls) on the same
  `df.tail(1500)`; the side-independent part (`zigzag_pivots` 0.129 s,
  `Volume.replace` 0.030 s, the rolling volume mean 0.038 s) is about 0.2 s of
  its 1.427 s; the rest is per-pivot `iloc` lookups filtered by kind, which are
  not duplicated. Sharing it saves about 0.10 s = 0.4 % of forming time.
- **`zigzag_pivots` per horizon in `collect_candidate_levels`: refuted.**
  `h["max_risk_pct"]` is distinct on every horizon (3.0, 7.0, 8.0, 9.0, 9.3,
  9.7, 10.0, 10.3, 10.7, 11.0); 2w's 3.0 equals `PIVOT_THRESHOLD_PCT` but runs
  on the full 2515-bar frame, the trendline search on its 1500-bar tail, so no
  two calls share inputs.
- **Indicators per horizon with the same window:** `atr(df, 14)` from
  `atr_floor_pct` is called 9.85 times per ticker on the same frame (confirmed,
  8.2 %); `bollinger_bands(df, 20, 2.0)` 9.85 times (confirmed, 4.7 %);
  `rolling_vwap` windows are distinct per horizon (refuted); `ema` repeats only
  span 50 (3m `ema_slow` = 6m `ema_fast`), 1 of 19.7 calls (0.06 %).
  `_band_live` and the confidence factors did not reach `atr` here (k = 0;
  1 `keltner_channel` call in 66 tickers).
- **`count_confirming_strategies` twice per scenario:** no target-independent
  work inside it once `candidates` is passed (levels.py:539-545 is one loop
  comparing each candidate to the target); 0.03 calls per ticker, 0.0 %.
- **`get_htf_bias` / `adjacent_aligned` / `macro_aligned`:** `get_htf_bias` is
  already hoisted per horizon (analyze.py:1134); `macro_aligned` recomputes the
  same 6m `horizon_trend` per scenario and `adjacent_aligned` is off
  (`MTF_ADJACENT_GATE` false locally); both 0.0 % at 0.02 scenarios per ticker.

## Bytes per object

Per-ticker trendline entry (both sides, `trendline_prefix_estimate`):

| Measure | Median | p95 | Max |
|---|---|---|---|
| Pickled bytes | 290,705 | 600,494 | 917,947 |
| Retained bytes (tracemalloc) | 766,606 | 2,014,310 | 3,230,646 |

Largest confirmed-pivot count on one side: 102. Analysis peak: 0.57 MB. The
estimate keeps the two unstable pivots V245-8 leaves to the tail (it holds every
pivot of `df.tail(1500).iloc[:-1]` and every pair's touch tuple), so it errs high.

## Byte-identical fixes

Ranked by forming share saved; saving = measured cost x (1 - 1 / 9.85).

| Id | Hot spot | Calls/ticker now -> after | Share saved (forming) | Why byte-identical | Files |
|---|---|---|---|---|---|
| F1 | `atr(df, 14)` inside `atr_floor_pct`, once per horizon | 9.85 -> 1 | 7.3 % (1.901 s measured) | every horizon's call reads the same `df` object with period 14 (levels.py:657); the horizon only scales the result afterwards (`* h["atr_stop_multiple"] / current_price`); the removed calls return the first call's series, the same float | `swingbot/core/market/levels.py`, `swingbot/core/scanning/analyze.py` (`_horizon_scenarios`, `_scan_one`, the `rescenario` caller at analyze.py:1317) |
| F2 | `bollinger_bands(df, window=20, num_std=2.0)` in `collect_candidate_levels` | 9.85 -> 1 | 4.2 % (1.084 s measured) | constant window and width, same `df` on every horizon (levels.py:286); the hoisted upper/lower must be appended at the same list position so `_cluster_levels`' stable sort sees the same order | `swingbot/core/market/levels.py`, `swingbot/core/scanning/analyze.py` |
| F3 | Donchian `High.rolling(20).max().shift(1)` / `Low.rolling(20).min().shift(1)` in `collect_candidate_levels` | 9.85 -> 1 | 1.4 % (0.373 s measured, see below) | fixed 20-bar window on the same `df` (levels.py:302-303); same list position as F2 | `swingbot/core/market/levels.py`, `swingbot/core/scanning/analyze.py` |
| F4 | `_fvg_candidates(df, params)` in `collect_candidate_levels` | 9.85 -> 1 | 0.7 % (0.174 s measured) | inputs are `df` and the scan's `ScanParams` only, no horizon (levels.py:180-195, 349); `params` must be read once per `_scan_one` and passed in, so a SIGHUP landing between two horizons can no longer split one ticker across two configs (today each horizon reads `ScanParams.from_config()` itself, levels.py:227) | `swingbot/core/market/levels.py`, `swingbot/core/scanning/analyze.py` |
| F5 | side-independent half of `_volume_confirmed_pivots` (`zigzag_pivots` at `PIVOT_THRESHOLD_PCT`, `Volume.replace`, the rolling volume mean) | 1.97 -> 0.98 | 0.4 % (about 0.10 s) | both sides pass the same `df.tail(1500)` (trendlines.py:287-291); only the `kind` filter differs (trendlines.py:179) | `swingbot/core/market/trendlines.py` |
| F6 | `ema(close, 50)` twice per ticker (3m `ema_slow`, 6m `ema_fast`) | 2 -> 1 | 0.06 % | same series, same span | `swingbot/core/market/levels.py` |

F3's cost cannot be read from the `chunk-*-forming.prof` files: the Donchian
lines (levels.py:302-303) and the per-horizon rolling S/R lines (levels.py:263-264)
sit in the same function and call the same pandas functions, so pstats pools
them. It was measured instead by profiling exactly those two expressions, under
cProfile, on the same 66 forming frames (2515 bars plus the synthetic forming
bar, `synth_forming_bar`) for each horizon the frame's length allows: Donchian
0.379 s over 660 calls, rolling S/R 0.376 s over the same 660. Scaled to the
scan's 650 calls that is 0.373 s, 1.6 % of the 23.304 s forming run; saving
0.373 x (1 - 1 / 9.85) = 0.335 s = 1.4 %. That is still twice F4's 0.7 %, so F3
keeps its rank.

F5 and F6 save less than 1 % of forming time and are ranked last on that
ground (the plan's rule), whatever their prepared designs. F6 is not worth a
commit. Not ranked: `veto_bullish_for` (10 equal-input `dead_cat_bounce` calls
per ticker when `DEAD_CAT_BOUNCE_VETO` is on, 0 cost here because it is off) and
`_band_live` (equal input across horizons except `now`, 0 cost at k = 0); both
are worth the same hoist if production runs with those flags on.

## Prefix-pure units

| Id | Unit | Window W | Horizon-specific | Share (forming) | Verdict |
|---|---|---|---|---|---|
| U1 | trendline pair search (confirmed pivots, pair geometry and touches against confirmed pivots) | 1 bar + 2 unstable pivots (index Decision 4) | no | 27.5 % (`custom_scanner_levels`; `_score_candidate` alone 20.5 %) | build in V245-8 |
| U2 | `zigzag_pivots` state in `collect_candidate_levels` (pivot list, direction, running extreme after bar `m - 1`) | 1 bar | yes (`threshold_pct = h["max_risk_pct"]`, 10 distinct values) | 3.6 % (0.848 s, levels.py:276) | candidate for V245-11 only if Phase B runs: each step compares one close with the carried extreme (indicators.py:97-129), no accumulated float, so resuming the walk at bar `m` returns the same pivots; check it against the index's never-cache list first (not carried in this task's handoff) |

No other candidate is prefix-pure: `compute_volume_profile` (37.9 %) rebins the
whole window on the forming bar's High/Low; `rolling_vwap`, `atr`,
`bollinger_bands` and `ema` are `rolling`/`ewm` series (incremental is not
byte-identical); `_fvg_candidates`' fill check reads every later bar;
`data_quality_issues` reads a tail window.

## Cache size

- Per-entry p95 retained bytes = per-ticker p95 / 2 = 2,014,310 / 2 = 1,007,155.
- Entries that fit 150 MB = floor(150,000,000 / 1,007,155) = floor(148.93) = 148.
- Recommended `STRUCTURE_CACHE_MAX` = min(600, 148) = **148**.

148 entries hold 74 tickers' two sides at p95 size; production's 92-ticker
watchlist needs 184. At the median entry (766,606 / 2 = 383,303 bytes) 150 MB
holds 391 entries, and the estimate errs high (see Bytes per object), so the
real watchlist fits the budget in bytes; the count cap of 148 is what evicts.
V245-7 takes 148 per the rule; holding the whole watchlist needs either a
budget of 185 MB at p95 (184 x 1,007,155 bytes) or a cap of at least 184.

## What Part 2 takes

- **V245-4 takes F1** (the `atr(df, 14)` memo for `atr_floor_pct`), not its
  prepared design: the two-zigzag duplicate is F5 here at 0.4 %. F1 touches
  `swingbot/core/market/levels.py` (`atr_floor_pct` accepts a precomputed ATR14
  value) and `swingbot/core/scanning/analyze.py` (`_scan_one` computes it once
  per frame and threads it through `_horizon_scenarios`, including the
  `rescenario` caller at analyze.py:1317).
- **V245-5 takes F2 (4.2 %), F3 (1.4 %, measured) and F4 (0.7 %)**, one commit each, in that order, each proved
  against V245-1b's golden. F5 is optional (under 1 %); F6 is dropped.
- `compute_volume_profile`'s `iterrows` (37.9 %) is the largest local cost and
  no fix in this plan reaches it; whether a vectorised, separately proven
  rewrite joins v245 or a follow-on plan is the controller's call.
