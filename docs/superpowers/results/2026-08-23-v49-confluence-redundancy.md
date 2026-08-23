# v49 — Inter-family confluence redundancy: measurement result

**Plan:** `docs/superpowers/plans/2026-08-22-v49-effective-confluence.md`
**Spec:** `docs/superpowers/specs/2026-08-22-v49-effective-confluence-design.md`
**Measured:** 2026-08-23, commit `4e04251`, TRAIN 2020-01-01…2023-12-31
**Instrument:** `scripts/backtest/measure_confluence_redundancy.py`
**Outcome: the component is DEGENERATE. Phase 3 wiring and the Phase 4
pre-registration were not run. See "Verdict".**

## What was measured

78-ticker watchlist × {4w, 2m, 3m, 4m, 6m}, every 20th bar inside TRAIN. For
every candidate price emitted by `levels.collect_candidate_levels`, the set of
strategy families landing within `CONFLUENCE_DEVIATION_PCT` (5.0%) of it was
recorded, giving

    C[i][i] = candidate prices family i landed on
    C[i][j] = of those, how many family j also landed on
    R[i][j] = (C[i][j]/C[i][i] + C[j][i]/C[j][j]) / 2

- **707,655** candidate prices tallied
- **75 of 78** tickers contributed (`CRWV`, `SNDK`, `SPCX` have no cached
  history). `ARM`, `GEV` and `NBIS` had data but produced `pairs=0` across all
  five horizons — short listing history, so no bar cleared the warmup inside
  TRAIN.
- Wall clock: ~3m25s

## Per-family landing counts (the N behind each row)

| Family | Prices landed on |
|---|---|
| EMA | 349,621 |
| VWAP | 263,184 |
| AVWAP | 481,463 |
| Fibonacci | 626,254 |
| Rolling S/R | 258,183 |
| Zigzag Pivot | 551,636 |
| Bollinger Bands | 365,506 |
| Donchian Channel | 372,175 |
| Floor Pivot | 412,457 |
| Trendline | 279,301 |
| FVG | 383,790 |
| Volume Profile | 239,852 |

## The matrix

Frozen verbatim into `swingbot/core/edge/confluence.py` as `REDUNDANCY`, under
a `# measured-on: 4e04251` provenance comment.
`tests/edge/test_confluence_matrix.py` asserts shape, symmetry, unit diagonal,
unit-interval entries and element-for-element family order.

Off-diagonal distribution: **mean 0.628, median 0.643, min 0.235, max 0.887**.

The spec's hypothesis about *which* families are redundant is confirmed:

- **Bollinger Bands ↔ Donchian Channel = 0.887** — the strongest pair. Both are
  rolling extremes of the same window.
- **Fibonacci ↔ Zigzag Pivot = 0.838** — both derive from the same swing
  extremes, as predicted.
- **EMA ↔ AVWAP = 0.827**, **AVWAP ↔ Floor Pivot = 0.809**, **EMA ↔ VWAP = 0.794**
  — the moving-window-over-closes cluster, also as predicted.
- **Rolling S/R** is the one genuine outlier, and the only family that looks
  close to independent of the moving-average cluster: 0.235 against VWAP,
  0.288 against Volume Profile, 0.311 against EMA.

The premise that families are redundant is **not** in doubt. Task 4 Step 5's
near-identity stop condition (every off-diagonal < 0.15) did not trigger, and
nothing here is close to it.

## Verdict: degenerate at the integer floor

The reduction saturates far below the gate. Enumerating **all 4,095 non-empty
subsets** of the 12 families through the frozen matrix:

| N (raw count) | mean N_eff | max N_eff | `effective_count_int` | subsets with int ≥ 2 |
|---|---|---|---|---|
| 2 | 1.237 | 1.619 | 1 | 0 / 66 |
| 3 | 1.339 | 1.691 | 1 | 0 / 220 |
| 4 | 1.395 | 1.744 | 1 | 0 / 495 |
| 5 | 1.430 | 1.746 | 1 | 0 / 792 |
| 6 | 1.455 | 1.712 | 1 | 0 / 924 |
| 12 | 1.518 | 1.518 | 1 | 0 / 1 |

**`effective_count_int` returns 1 for every possible subset. Not one of the
4,095 reaches 2.** The maximum `N_eff` achievable by any combination of all
twelve families is 1.746, and the FLOOR rule the plan pre-registered takes that
to 1.

The consequences are arithmetic, not empirical:

1. With `EFFECTIVE_CONFLUENCE_ENABLED = true`, `count_confirming_strategies`
   returns `1` for every scenario.
2. `MIN_TARGET_CONFLUENCE_COUNT` defaults to **2**, so **every scenario fails
   the gate**. The alert stream goes to zero.
3. The Phase 4 TRAIN grid is `MIN ∈ {2, 3}` × `enabled = true`. **Both cells
   produce zero alerts.** There is no viable cell in the pre-registered grid.
4. VALIDATION clause 4 — "alert-count reduction ≤ 25% vs the `false` arm" —
   fails by construction at a 100% reduction. Clause 3 (`N >= 15`) fails too,
   at `N = 0`.

Phase 4 was therefore not run. It could only have spent the one-shot
VALIDATION budget to confirm arithmetic that is already determined. Phase 3
wiring was not done either: shipping a flag whose sole effect, if ever enabled,
is to silence every alert is a footgun, not a dark launch.

This is the same class of outcome as the near-identity stop the plan already
anticipates, at the opposite tail. The plan's Task 4 Step 5 wrote the stop
condition for "no redundancy to discount"; this is "the discount consumes
everything". **A finished measurement, not a failed task.**

## What was NOT done, and why it must not be done casually

Every obvious rescue is a re-opened pre-registration, and the methodology doc
forbids that:

- **Round or ceil instead of floor.** The plan pre-registered FLOOR explicitly
  ("the gate fails closed, so a scenario at 2.9 effective votes has not earned
  a 3"). `round` would make almost every subset 1 anyway — the mean N_eff is
  1.24–1.52, so rounding gives 1 below 1.5 and 2 above; `ceil` would make
  almost every subset 2 and turn the gate into a near-no-op in the opposite
  direction. Neither is a tuning choice; both are a different hypothesis.
- **Rescaling or thresholding the matrix.** Fitting the discount until it
  produces a survivable alert count is fitting to the outcome.
- **Lowering `MIN_TARGET_CONFLUENCE_COUNT` to 1.** Outside the frozen grid, and
  it makes the confluence gate vacuous rather than sharper.

Any of these needs a **new spec with a new pre-registered hypothesis**, written
knowing this result — not an edit to this one.

## An honest caveat on the instrument

The tally counts co-occurrence over **every candidate price**
`collect_candidate_levels` emits, which is what the plan's Task 3 specifies.
Production only ever counts families at an actual *scenario target* price,
which is a much smaller and non-uniformly-sampled subset. A target-price-only
measurement would plausibly give somewhat lower off-diagonals.

It would not change the verdict. To get any subset to `int ≥ 2`, the average
pairwise redundancy would have to fall from 0.63 to below roughly 0.33 — the
denominator `sum(R[i][j])` must drop by half. The observed spread (median
0.643, and only one family below 0.35 against anything) leaves no room for that
under a different sampling of the same detectors. If a future spec wants to
re-measure at target prices only, that is a legitimate new hypothesis; it is
not a correction to this one.
