# Confluence scenario gates — TRAIN grid (Task 39/40)

## Rule (pre-registered, quoted verbatim)

From `scripts/tune_confluence_gates.py`'s `RULE` constant and the header
printed with the grid output
(`docs/superpowers/results/2026-07-confluence-train-grid.txt`):

> per horizon: include iff WR>=80 and ExpR>0 and N>=30 and excl<=50%; global
> pair = max pooled ExpR among pairs with >=2 qualifying horizons

Restated from the grid file's own "Selection rule applied by hand" section:

> Rule: per horizon, include iff win_rate>=80 and expectancy_r>0 and N>=30
> and (scratches+timeouts)<=50% of closed trades; global pair = the
> (min_confluence, min_risk_reward) pair maximizing pooled ExpR among pairs
> with >=2 qualifying horizons.

And the plan's pre-registered fallback for a no-winner outcome (quoted from
Task 39's brief text, carried into the grid file and this doc):

> if no pair qualifies, confluence source stays WEAK everywhere and Tasks
> 41-42 record that honestly

## Setup

- TRAIN window: `2020-01-01` .. `2023-12-31`
- Universe: 25 of 75 watchlist tickers (every 3rd, alphabetical stride) —
  `AAPL, AMAT, ARM, AVGO, BKNG, CRWD, DELL, EBAY, GD, GM, HD, HPQ, INTC,
  ISRG, META, MSFT, NBIS, NOW, PANW, PLTR, QCOM, SHOP, SNPS, TSLA, V`
- Horizons tested: `4w, 2m, 3m, 4m, 6m`
- Grid: `min_confluence in {2, 3, 4} x min_risk_reward in {0.0, 0.3}` (6
  points), base gates `min_reward_pct=3.0, min_stop_distance_pct=2.0,
  max_stop_distance_pct=7.0, cooldown_bars=5` held fixed
- Methodology note (from `scripts/tune_confluence_gates.py`'s module
  docstring): the historical replay is expensive enough over the full
  75-ticker watchlist x 5 horizons x ~1900 bars that the serial loop takes
  on the order of hours per grid point. The 25-ticker sample above makes
  the full 6-point grid tractable in one sitting; a full-universe check of
  the `(confl=2, rr=0.0)` point was run separately and came back *worse*
  (N=6686, WR=56.6%, all horizons fail) — consistent with, not
  contradicting, the sampled grid's conclusion below.

## Full per-horizon + pooled results (all 6 grid points)

| confl | rr | horizon | N | WR% | ExpR | excl% | result |
|---|---|---|---|---|---|---|---|
| 2 | 0.0 | 4w | 249 | 58.6 | -0.156 | 5.3% | fail |
| 2 | 0.0 | 2m | 301 | 54.8 | -0.208 | 5.6% | fail |
| 2 | 0.0 | 3m | 352 | 65.1 | -0.060 | 5.6% | fail |
| 2 | 0.0 | 4m | 383 | 64.8 | -0.081 | 5.9% | fail |
| 2 | 0.0 | 6m | 415 | 61.7 | -0.118 | 7.0% | fail |
| 2 | 0.0 | **POOLED** | 1700 | 61.4 | -0.119 | — | qualifying_horizons=[] |
| 2 | 0.3 | 4w | 249 | 58.6 | -0.156 | 5.3% | fail |
| 2 | 0.3 | 2m | 301 | 54.8 | -0.208 | 5.6% | fail |
| 2 | 0.3 | 3m | 352 | 65.1 | -0.060 | 5.6% | fail |
| 2 | 0.3 | 4m | 383 | 64.8 | -0.081 | 5.9% | fail |
| 2 | 0.3 | 6m | 415 | 61.7 | -0.118 | 7.0% | fail |
| 2 | 0.3 | **POOLED** | 1700 | 61.4 | -0.119 | — | qualifying_horizons=[] |
| 3 | 0.0 | 4w | 226 | 58.4 | -0.158 | 6.2% | fail |
| 3 | 0.0 | 2m | 272 | 54.8 | -0.204 | 6.2% | fail |
| 3 | 0.0 | 3m | 324 | 65.4 | -0.066 | 5.5% | fail |
| 3 | 0.0 | 4m | 336 | 64.9 | -0.096 | 5.6% | fail |
| 3 | 0.0 | 6m | 353 | 60.6 | -0.138 | 7.6% | fail |
| 3 | 0.0 | **POOLED** | 1511 | 61.2 | -0.128 | — | qualifying_horizons=[] |
| 3 | 0.3 | 4w | 226 | 58.4 | -0.158 | 6.2% | fail |
| 3 | 0.3 | 2m | 272 | 54.8 | -0.204 | 6.2% | fail |
| 3 | 0.3 | 3m | 324 | 65.4 | -0.066 | 5.5% | fail |
| 3 | 0.3 | 4m | 336 | 64.9 | -0.096 | 5.6% | fail |
| 3 | 0.3 | 6m | 353 | 60.6 | -0.138 | 7.6% | fail |
| 3 | 0.3 | **POOLED** | 1511 | 61.2 | -0.128 | — | qualifying_horizons=[] |
| 4 | 0.0 | 4w | 193 | 61.7 | -0.124 | 7.2% | fail |
| 4 | 0.0 | 2m | 230 | 54.8 | -0.219 | 7.3% | fail |
| 4 | 0.0 | 3m | 276 | 65.6 | -0.076 | 6.4% | fail |
| 4 | 0.0 | 4m | 283 | 66.4 | -0.081 | 6.3% | fail |
| 4 | 0.0 | 6m | 271 | 64.2 | -0.090 | 9.7% | fail |
| 4 | 0.0 | **POOLED** | 1253 | 62.9 | -0.114 | — | qualifying_horizons=[] |
| 4 | 0.3 | 4w | 193 | 61.7 | -0.124 | 7.2% | fail |
| 4 | 0.3 | 2m | 230 | 54.8 | -0.219 | 7.3% | fail |
| 4 | 0.3 | 3m | 276 | 65.6 | -0.076 | 6.4% | fail |
| 4 | 0.3 | 4m | 283 | 66.4 | -0.081 | 6.3% | fail |
| 4 | 0.3 | 6m | 271 | 64.2 | -0.090 | 9.7% | fail |
| 4 | 0.3 | **POOLED** | 1253 | 62.9 | -0.114 | — | qualifying_horizons=[] |

(Table transcribed directly from
`docs/superpowers/results/2026-07-confluence-train-grid.txt`; that file is
the source of record.)

## Conclusion

No horizon, at any of the 6 `(min_confluence, min_risk_reward)` grid
points, meets the `win_rate>=80` bar (best observed win_rate is 66.4%, most
are 55-65%) or has `expectancy_r>0` (every single cell is negative, -0.06 to
-0.22). Zero qualifying horizons at every grid point — there is no pair to
even rank by pooled ExpR. **No config qualifies under the pre-registered
rule.**

Per the plan's pre-registered fallback quoted above, no grid point is
adopted as a validated winner. `CONFLUENCE_GATES` in
`swingbot/core/backtest_scenarios.py` is set to safe, previously-used
defaults — `min_reward_pct/min_stop_distance_pct/max_stop_distance_pct/
min_risk_reward` mirror `scripts/run_backtest_range.py`'s pre-existing
`SCENARIO_GATES` (the closest existing precedent, itself never
grid-validated), `min_confluence=2` is the least restrictive value the grid
tested, and `horizons` lists the grid's coverage — not a "qualifying"
subset, since none qualified. **The confluence source stays WEAK across all
horizons; Tasks 41-42 must record this outcome honestly rather than treat
any grid point as validated.**

## Open discrepancy (not resolved here — out of scope)

The Task 40 brief's example code comment claims "The live scan (Task 43)
and the validation run (Task 41) BOTH read this constant." As implemented
and already reviewed/approved (commits `9303ad3`, `346e489`), Task 43's
`attach_plan_v2` does not import or reference `CONFLUENCE_GATES` at all — it
builds a v2 plan from an already-constructed scenario and does not perform
scenario-admission gating. This is a discrepancy between the plan's
aspirational comment and what was actually built; it is flagged here for
visibility and intentionally not "fixed" by retrofitting Task 43's
already-closed code, which is out of this task's scope.
