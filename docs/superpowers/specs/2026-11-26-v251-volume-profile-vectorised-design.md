# v251 — Volume profile without iterrows: a byte-identical vectorised loop (V245-5b)

**Version:** ui 1.50.0 · bot 2.20.0
**Bump:** bot patch
**Edge:** none (integrity)
**Screen:** exempt (integrity)
**Panel:** quant-engineer
**Status:** spec written 2026-11-26. The partner approved this work during v245 as task V245-5b (decision recorded in the v245 worktree's `.superpowers/sdd/2026-11-23-v245-exact-analysis-cache/progress.md`), but it was never planned or built. On 2026-11-26 the partner chose "build now, deploy now". It cannot join the v245 plan, which is at the 20-task cap, so per `document-conventions.md` § Splitting it is its own spec; v245's spec carries a `**Split:**` line pointing here.

`Edge: none (integrity)`: no strategy, filter, exit or alert changes; every
output value is identical to today's. It only makes analysis cheaper per
ticker, toward v245's 0.7 s target. `Bump: bot patch`: nothing a user sees
changes, only scan time.

## Why

`docs/superpowers/results/2026-11-23-v245-analysis-profile.md` measured
`swingbot/core/market/signals.py::compute_volume_profile` at **37.9 %** of
local analysis time (8.836 s of the 23.304 s forming run, 66 tickers), the
largest single cost. Almost all of it is the per-bar `window.iterrows()` loop
(signals.py:634-644), which builds one pandas Series per bar.

The v245 prefix cache cannot help here: the function is not prefix-pure.
`window = df.iloc[-lookback:]` and the bin edges come from that window's own
Low/High (signals.py:623-627), so the forming bar moves every bin edge and the
whole histogram has to be rebuilt on every scan. The only way to make it
cheaper is to make each call cheaper.

Production numbers:

- v245 Phase A (bot 2.19.8, 2026-11-25): analysis p50 **3.12 s per ticker**,
  against the 0.7 s target. Verdict MISSED.
- Shadow mode: p50 **2.516 s per ticker**, which still includes the shadow
  comparison overhead. Measured 2026-11-26 around 08:41 UTC, read-only on
  production, with
  `bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python - --since 2026-11-25T16:15:54Z" < scripts/perf/analysis_phase_report.py`.
  Conditions: bot 2.19.10, `ANALYSIS_CACHE=shadow`, 74 scans (including the
  26 Nov holiday). Results: p50 2.516 s, p90 3.333 s, prefix_p50 0.0004 s,
  cache hit rate 0.953, `rss_mb` max 739.7. This is the **baseline** that
  § Rollout compares against.

The 37.9 % is a local share, so the production saving is not promised here. It
is measured after deploy (§ Rollout).

## Callers (unchanged)

- `compute_hvn_level` (signals.py:661), called by
  `swingbot/core/market/levels.py::collect_candidate_levels` (levels.py:392)
  once per horizon on every scan. This is the hot path.
- `swingbot/core/charts/chart_geometry.py:397` (`compute_hvn_level`, chart
  overlays).
- `swingbot/core/charts/chart_volume_profile.py:73/79`: the trade chart's
  volume profile panel, the only caller that passes explicit
  `price_min`/`price_max`.
- `swingbot/admin/api_v1/market.py:178` (admin market endpoint, default range).
- `volume_profile_signal` (signals.py:686), the Volume Profile strategy,
  through `compute_hvn_level`.

None of their code changes. The function's signature, docstring contract and
return dict stay the same.

## What changes

Only the loop body at signals.py:633-644 (`bins = [0.0] * n_bins` through the
last `bins[idx] += ...`). Everything before it (the length guard, `window`,
the derived or explicit range, the flat-range `None`, `bin_size`) and
everything after it (`total_vol`, `poc_idx`, `bin_edges`, `poc_price`,
`poc_pct`, the return dict) stays as it is, byte for byte.

The loop is replaced by array work over the window's `High`, `Low` and
`Volume` columns: compute every midpoint at once, apply the same range test,
compute the bucket index with the same truncate-then-clamp rule, and
accumulate volumes per bucket. The exact numpy calls are the implementer's
choice, within the exactness rules below. Any helper this needs lives in
`signals.py` next to the function.

## Exactness rules

The new code must give the same result as the old loop for every input, not
just for typical frames.

1. **Same values.** Every element of `bin_volumes` and `bin_edges`, plus
   `poc_index`, `poc_price` and `poc_pct`, is identical to the old loop's
   when compared with `float.hex` (so `0.0` vs `-0.0` and NaN positions count
   too).
2. **Same element types as the oracle for the same inputs.** Both lists stay
   `list`, never arrays, and every element, plus `poc_index`, `poc_price` and
   `poc_pct`, has the same type the old code gives for the same inputs.
   `bin_volumes` holds Python `float`, never numpy scalars, including when no
   bar is in range (`np.bincount` would return int64 there). The tail is not
   rewritten, so its types follow the bounds: the chart caller passes
   `np.float64` bounds, and today that gives `np.float64` `bin_edges` and
   `poc_price`. That stays as it is. The return is `None` in exactly the same
   cases.
3. **Same arithmetic per element.** Midpoint `(High + Low) / 2` in float64.
   Bucket index `int((mid - price_min) / bin_size)`, which truncates toward
   zero, then clamped to `[0, n_bins - 1]`. Volume converted to float64 the
   same way `float(row["Volume"])` converts it, including int64 volumes and
   frames with object-dtype columns, where `iterrows` stops upcasting rows.
   **The old loop converts `Volume` only for in-range bars.** A `None` or
   `pd.NA` volume on an in-range bar raises `TypeError` today, and on a
   skipped bar it is never touched. Converting the whole column up front
   would turn those into NaN, or raise for bars the loop skips. The new code
   must give the same outcome in both cases: raise `TypeError` for an
   in-range bar, ignore a skipped one.
4. **Same accumulation order per bucket.** Each bucket starts at `0.0` and
   adds its bars' volumes one at a time in window row order, as the loop
   does. A pairwise or reordered sum can change the last bit and is not
   allowed. The method must accumulate sequentially in index order, and the
   oracle test below must prove it.
5. **Python reductions stay Python.** `sum(bins)`, `max(bins)` and
   `bins.index(...)` keep running over a Python list. Their float and NaN
   behaviour differs from `np.sum`/`np.max`/`np.argmax` (for example,
   Python's `max` with a NaN depends on where the NaN sits), so they are not
   swapped for numpy versions.
6. **Same outcome on non-finite prices: the same result, or the same
   exception type, as the oracle.** A NaN midpoint compares false on both
   bounds, so it is not skipped, and `int(NaN)` raises `ValueError`. Some
   infinite prices raise the same way: `+inf` High under the derived range,
   or `-inf` Low, makes the quotient NaN. Others are skipped and return
   normally: `-inf` High, `+inf` Low, or `+inf` High under a finite explicit
   range put the midpoint outside the bounds. A quotient of `±inf` would
   raise what `int()` raises there, `OverflowError`. The vectorised code must
   not turn any of these into silent garbage indices (numpy gives an
   arbitrary value when it casts NaN to int). It must detect exactly the
   midpoints that pass the range test and raise there.
7. **NaN volume propagates.** A NaN `Volume` on an in-range bar makes that
   bucket NaN, as today, and the downstream `total_vol > 0` / `max` /
   `index` behaviour follows unchanged from rule 5.
8. **Explicit-range skipping unchanged.** With explicit
   `price_min`/`price_max`, a bar whose midpoint is below `price_min` or
   above `price_max` adds nothing (strict `<` / `>`, so a midpoint exactly on
   a bound is kept and clamped as today).
9. **No other behaviour change.** No new parameters, no caching, no change to
   `compute_hvn_level` or any caller.
10. **Complexity < 15** for every function touched or added
    (`scripts/dev/complexity_gate.py`). `compute_volume_profile` must not get
    worse than its current baseline.

## Tests

- **Reference oracle.** A new test module in `tests/market/` (an existing
  suite directory, so no `suites.toml` change) keeps a verbatim copy of the
  old function, `iterrows` loop included, as `_reference_compute_volume_profile`.
  It compares the new function against it with the rule 1 `float.hex` and
  type checks, across:
  - a seeded batch of random OHLCV frames (several hundred) with
    **fractional** volumes, over a range of `lookback` and `n_bins` values,
    default and explicit ranges, explicit bounds given as Python `float` and
    as `np.float64` (the chart caller's type);
  - cases built to hit the edges: a midpoint exactly on `price_min`,
    `price_max` and every interior bin edge; the clamp at `n_bins - 1` when
    mid equals `price_max`; explicit ranges narrower than the window
    (out-of-range skips) and much wider ones (empty buckets); all-zero volume
    (`total_vol == 0` -> `n_bins // 2`); ties for the busiest bucket (first
    index wins); int64 volumes and volumes above 2**53; an extra object-dtype
    column; NaN volume on one bar and on the busiest bar; `-0.0` prices;
    `n_bins = 1`; a frame of exactly `lookback + 2` rows; an explicit range
    with **zero bars in range** (all volumes stay Python `0.0`);
  - missing volumes: an object-dtype `Volume` with `None`, and a nullable
    `Int64`/`Float64` `Volume` with `pd.NA`, each once on an in-range bar
    (expects `TypeError`, like the oracle) and once on a skipped bar (returns
    normally);
  - non-finite prices, each asserting the same outcome as the oracle (result
    or exception type): NaN High, NaN Low; `+inf` High and `-inf` Low
    (raise); `-inf` High, `+inf` Low, and `+inf` High under a finite explicit
    range (skipped, return normally).
- **Order proof.** One bucket receiving 64 or more fractional volumes. The
  test first asserts that `np.sum` of those volumes differs from the
  sequential left-to-right sum, so the case really can tell the two apart,
  then asserts the new code equals the sequential sum (and the oracle).
- **Golden stays.** `tests/scanning/test_v245_scan_one_golden.py` (cases in
  `tests/scanning/v245_golden_cases.py`) stays byte-identical. It is never
  regenerated for this change, and a diff there is a bug in the rewrite.
- Existing `compute_volume_profile` / `compute_hvn_level` / chart panel tests
  stay green unchanged.

## Rollout

A routine deploy. The v245 shadow soak keeps running across it and stays
valid. It keeps the pinned command
`bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python - --since 2026-11-25T16:15:54Z --first-full-day 2026-11-27" < scripts/perf/analysis_cache_soak_report.py`,
not `--since-deploy`. The plan fixes `docs/deploy/DEPLOY_HETZNER.md` (about
line 752), which still says `--since-deploy` for the soak. **The soak is no
parity evidence for v251:** the shadow runs the new function on both sides,
so a v251 difference cannot show up there. Parity rests on the oracle test
and the golden.

**Like-for-like timing.** After deploy, run
`scripts/perf/analysis_phase_report.py` with `--since <deploy stamp>`, in
the same cache mode as the baseline (`ANALYSIS_CACHE=shadow`). Compare its
p50 with the § Why baseline (2.516 s), and record the scan count, the
deployed commit and the bot version beside it in the v245 results trail. If
anything else ships in the same deploy (v239 may), the comparison is
confounded, and the record must say so. This spec has no pass/fail threshold
on time: the 0.7 s target stays v245's, judged there.

## Out of scope

- Caching the profile across scans (impossible: not prefix-pure, see § Why).
- Changing bin count, range or POC semantics.
- Any other v245 hot spot.
- `_vectorized_hvn` in `swingbot/core/market/entry_filters.py:1118`. It is a
  different calculation, and it is neither reused here nor unified with
  `compute_volume_profile`.

## Parallelisation

- **Single task.** One function in `signals.py` plus one new test module. The
  oracle test and the rewrite are written together, test first: the test
  module's reference copy has to be taken from the file before the loop is
  replaced. Nothing else in flight may edit `signals.py` lines 585-658 at the
  same time.

## Panel review

Run on 2026-11-26. Findings 3 and 6 were checked against the current code
before applying them.

- quant-engineer: [BLOCKING] the 2.52 s figure needed its source, and the post-deploy timing must be like-for-like (same cache mode, `--since` the deploy stamp, scan count, commit, confound noted) -- applied (§ Why baseline record, § Rollout)
- quant-engineer: the order proof was too weak; use one bucket with 64+ fractional volumes that first asserts `np.sum` differs from the sequential sum, and use fractional volumes in the random frames -- applied (§ Tests)
- quant-engineer: the old loop converts `Volume` only for in-range bars (`TypeError` on `None`/`pd.NA`); whole-column conversion changes that -- applied (rule 3, plus cases in range and skipped; confirmed: in-range `None` and `pd.NA` both raise `TypeError`)
- quant-engineer: "infinite High or Low raises `ValueError`" is not general; some infinities are skipped and return normally -- applied (rule 6 reworded to "same outcome as the oracle", with non-raising cases)
- quant-engineer: with zero bars in range `np.bincount` returns int64 -- applied (rule 2, edge case added)
- quant-engineer: the chart caller passes `np.float64` bounds, so today's tail returns `np.float64` edges and `poc_price`; rule 2 should say "same element types as the oracle" -- applied (confirmed on current code; `np.float64` bounds tested)
- quant-engineer: name the pinned soak command rather than `--since-deploy`, have the plan fix DEPLOY_HETZNER.md, and note the soak is no parity evidence for v251 -- applied (§ Rollout)
- quant-engineer: add `volume_profile_signal` to the callers; put `_vectorized_hvn` (entry_filters.py) out of scope -- applied (§ Callers, § Out of scope)
