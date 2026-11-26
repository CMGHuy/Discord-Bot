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
- Shadow mode, 2026-11-25/26: p50 **2.52 s per ticker**, which still includes
  the shadow comparison overhead.

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
2. **Same Python types.** `bin_volumes` and `bin_edges` are `list` of Python
   `float`, never numpy scalars or arrays. `poc_index` is `int`, `poc_price`
   and `poc_pct` are `float`. The return is `None` in exactly the same cases.
3. **Same arithmetic per element.** Midpoint `(High + Low) / 2` in float64.
   Bucket index `int((mid - price_min) / bin_size)`, which truncates toward
   zero, then clamped to `[0, n_bins - 1]`. Volume converted to float64 the
   same way `float(row["Volume"])` converts it, including int64 volumes and
   frames with object-dtype columns, where `iterrows` stops upcasting rows.
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
6. **Same exceptions.** A non-finite midpoint that gets past the range test
   raises the same exception type the loop raises today. A NaN midpoint
   compares false on both bounds, so it is not skipped, and `int(NaN)` raises
   `ValueError`. An infinite High or Low makes the quotient NaN (`inf / inf`
   or `nan` midpoint), so it raises `ValueError` too (checked on the current
   code 2026-11-26). Should a quotient ever be `±inf`, the new code raises
   what `int()` raises there, `OverflowError`. The vectorised code must not turn these into silent garbage indices (a
   NaN cast to int in numpy gives an arbitrary value). It must detect them
   and raise the same type.
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
  - a seeded batch of random OHLCV frames (several hundred) over a range of
    `lookback` and `n_bins` values, default and explicit ranges;
  - cases built to hit the edges: a midpoint exactly on `price_min`,
    `price_max` and every interior bin edge; the clamp at `n_bins - 1` when
    mid equals `price_max`; explicit ranges narrower than the window
    (out-of-range skips) and much wider ones (empty buckets); all-zero volume
    (`total_vol == 0` -> `n_bins // 2`); ties for the busiest bucket (first
    index wins); int64 volumes and volumes above 2**53; an extra object-dtype
    column; NaN volume on one bar and on the busiest bar; `-0.0` prices;
    `n_bins = 1`; a frame of exactly `lookback + 2` rows;
  - exception cases: a NaN High or Low inside the window, and an infinite
    High or Low, each asserting the new code raises the same exception type as the
    oracle.
- **Order proof.** One case where reordering the adds changes the result
  (for example `[1e16, 1.0, -1e16]` in one bucket), so a reordered sum fails.
- **Golden stays.** `tests/scanning/test_v245_scan_one_golden.py` (cases in
  `tests/scanning/v245_golden_cases.py`) stays byte-identical. It is never
  regenerated for this change, and a diff there is a bug in the rewrite.
- Existing `compute_volume_profile` / `compute_hvn_level` / chart panel tests
  stay green unchanged.

## Rollout

A routine deploy. The v245 shadow soak keeps running across it and stays
valid, because every output is identical. After deploy, production analysis
p50 is read with `scripts/perf/analysis_phase_report.py --since-deploy` and
recorded in the v245 results trail next to the Phase A figure. This spec has
no pass/fail threshold on time: the 0.7 s target stays v245's, judged there.

## Out of scope

- Caching the profile across scans (impossible: not prefix-pure, see § Why).
- Changing bin count, range or POC semantics.
- Any other v245 hot spot.

## Parallelisation

- **Single task.** One function in `signals.py` plus one new test module. The
  oracle test and the rewrite are written together, test first: the test
  module's reference copy has to be taken from the file before the loop is
  replaced. Nothing else in flight may edit `signals.py` lines 585-658 at the
  same time.
