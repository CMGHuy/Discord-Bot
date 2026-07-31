# Gatekeeper v7 — baseline census (TRAIN folds, annotate-only)

Run: `scripts/gate_fold_run.py --all` · 2026-07-31 · commit `d353bb0`
No tuning decisions live in this file — census only.

Replay universe: 78-ticker watchlist × anchored TRAIN folds (test years
2021/2022/2023, `swingbot/core/gate/folds.py:FOLDS`), fixed `horizon_key="2w"`
(the fold runner's fallback replay has no horizon parameter — see
`_default_replay`'s own docstring). `gate_eval=True`, no `gate_min_tier`
filter — every signal is taken and annotated, none is skipped.

## EMA Crossover

Pooled baseline: N=17, WR=94.1%, expectancy_r=0.213

| Decile | N | WR % | Wilson LB | expectancy_r |
|---|---|---|---|---|
| 0-9 | 0 | — | 0.0 | — |
| 10-19 | 0 | — | 0.0 | — |
| 20-29 | 0 | — | 0.0 | — |
| 30-39 | 0 | — | 0.0 | — |
| 40-49 | 0 | — | 0.0 | — |
| 50-59 | 0 | — | 0.0 | — |
| 60-69 | 1 | 100.0 | 0.0546 | 0.292 |
| 70-79 | 11 | 100.0 | 0.6785 | 0.291 |
| 80-89 | 5 | 80.0 | 0.2988 | 0.026 |
| 90-99 | 0 | — | 0.0 | — |

Flag fire-rates: rf_stop_sweep 5.9% (the only flag observed to fire for this
strategy in-sample)

Losers cluster: with only 1 loss in 17 signals the sample is too thin to
cluster anything meaningfully. All signals land in the 60-89 score band, so
this baseline says nothing about how the strategy behaves below score 60.
The single loss falls in the 80-89 decile, not the lowest band present.

## VWAP

Pooled baseline: N=0, WR=—, expectancy_r=—

No decile table — zero closed trades across all three TRAIN fold years on
this 78-ticker universe at the 2w horizon.

Flag fire-rates: no fired signals to measure.

Losers cluster: not applicable — the strategy produced no signals at all in
this replay, so there is no loser population to describe. This is a fact
about the fixed-horizon fallback replay (VWAP may fire on other horizons
this fold runner does not exercise), not a claim that the live strategy
never trades.

## Fibonacci

Pooled baseline: N=41, WR=68.3%, expectancy_r=-0.097

| Decile | N | WR % | Wilson LB | expectancy_r |
|---|---|---|---|---|
| 0-9 | 0 | — | 0.0 | — |
| 10-19 | 0 | — | 0.0 | — |
| 20-29 | 0 | — | 0.0 | — |
| 30-39 | 0 | — | 0.0 | — |
| 40-49 | 0 | — | 0.0 | — |
| 50-59 | 1 | 0.0 | 0.0 | -1.036 |
| 60-69 | 6 | 50.0 | 0.1395 | -0.348 |
| 70-79 | 26 | 76.9 | 0.5592 | 0.022 |
| 80-89 | 8 | 62.5 | 0.2589 | -0.176 |
| 90-99 | 0 | — | 0.0 | — |

Flag fire-rates: rf_stop_sweep 14.6%

Losers cluster: the bulk of losses sit below score 70 (deciles 50-59 and
60-69 have the worst WR in the table) and expectancy is negative overall
(-0.097R) despite a 68.3% win rate, meaning wins are small relative to
losses for this strategy. The 80-89 decile also underperforms the 70-79
decile immediately below it, so the top of the score range is not a clean
monotone improvement here.

## Support/Resistance

Pooled baseline: N=0, WR=—, expectancy_r=—

No decile table — zero closed trades across all three TRAIN fold years.

Flag fire-rates: no fired signals to measure.

Losers cluster: not applicable — no signals fired in this replay (fixed 2w
horizon, see the run header). Nothing to report about loser characteristics
from this census.

## RSI

Pooled baseline: N=5, WR=100.0%, expectancy_r=0.34

| Decile | N | WR % | Wilson LB | expectancy_r |
|---|---|---|---|---|
| 0-9 | 0 | — | 0.0 | — |
| 10-19 | 0 | — | 0.0 | — |
| 20-29 | 0 | — | 0.0 | — |
| 30-39 | 0 | — | 0.0 | — |
| 40-49 | 0 | — | 0.0 | — |
| 50-59 | 0 | — | 0.0 | — |
| 60-69 | 0 | — | 0.0 | — |
| 70-79 | 1 | 100.0 | 0.0546 | 0.34 |
| 80-89 | 3 | 100.0 | 0.31 | 0.34 |
| 90-99 | 1 | 100.0 | 0.0546 | 0.34 |

Flag fire-rates: rf_stop_sweep 40.0% (2 of 5 signals)

Losers cluster: N=5 is far too thin to draw any conclusion — this is
anecdote, not evidence, and the overfit sentinel (G110) would flag it as
such (pooled N < 90). There are zero losses in the sample, so there is
literally nothing to cluster. The one honest statement this table supports
is "gather more signals before trusting RSI's baseline at all."

## MACD

Pooled baseline: N=0, WR=—, expectancy_r=—

No decile table — zero closed trades across all three TRAIN fold years.

Flag fire-rates: no fired signals to measure.

Losers cluster: not applicable — no signals fired in this replay.

## Elliott Wave

Pooled baseline: N=0, WR=—, expectancy_r=—

No decile table — zero closed trades across all three TRAIN fold years.

Flag fire-rates: no fired signals to measure.

Losers cluster: not applicable — no signals fired in this replay.

## MA Ribbon

Pooled baseline: N=69, WR=75.4%, expectancy_r=-0.036

| Decile | N | WR % | Wilson LB | expectancy_r |
|---|---|---|---|---|
| 0-9 | 0 | — | 0.0 | — |
| 10-19 | 0 | — | 0.0 | — |
| 20-29 | 0 | — | 0.0 | — |
| 30-39 | 0 | — | 0.0 | — |
| 40-49 | 0 | — | 0.0 | — |
| 50-59 | 0 | — | 0.0 | — |
| 60-69 | 7 | 71.4 | 0.3026 | -0.088 |
| 70-79 | 34 | 79.4 | 0.6159 | 0.018 |
| 80-89 | 26 | 69.2 | 0.481 | -0.117 |
| 90-99 | 2 | 100.0 | 0.1979 | 0.291 |

Flag fire-rates: rf_stop_sweep 14.5%

Losers cluster: the 80-89 decile underperforms the 70-79 decile right below
it (69.2% vs 79.4% WR, expectancy flips negative), so score is not cleanly
monotone in the upper-middle band for this strategy. Overall pooled
expectancy is slightly negative (-0.036R) despite a 75%+ win rate — losses
run larger than wins on average. The only decile that clears both a strong
WR and positive expectancy is 90-99, but n=2 there is too thin to act on.

## Break & Retest

Pooled baseline: N=19, WR=78.9%, expectancy_r=0.01

| Decile | N | WR % | Wilson LB | expectancy_r |
|---|---|---|---|---|
| 0-9 | 0 | — | 0.0 | — |
| 10-19 | 0 | — | 0.0 | — |
| 20-29 | 0 | — | 0.0 | — |
| 30-39 | 0 | — | 0.0 | — |
| 40-49 | 0 | — | 0.0 | — |
| 50-59 | 2 | 50.0 | 0.0267 | -0.376 |
| 60-69 | 9 | 88.9 | 0.5067 | 0.142 |
| 70-79 | 8 | 75.0 | 0.3558 | -0.042 |
| 80-89 | 0 | — | 0.0 | — |
| 90-99 | 0 | — | 0.0 | — |

Flag fire-rates: rf_fake_breakout 26.3%, rf_stop_sweep 21.1%

Losers cluster: the worst decile by far is 50-59 (50% WR, -0.376R
expectancy), consistent with the checklist's own intent — the lowest scores
should carry the most risk. `rf_fake_breakout` is this strategy's own
namesake red flag and fires on over a quarter of signals, worth watching
against the ablation results (G99) to see whether it actually earns its
keep. N=19 pooled is thin (below the N>=30 fold-gate floor), so this
baseline is directional, not conclusive.

## RSI Divergence

Pooled baseline: N=163, WR=72.4%, expectancy_r=-0.04

| Decile | N | WR % | Wilson LB | expectancy_r |
|---|---|---|---|---|
| 0-9 | 0 | — | 0.0 | — |
| 10-19 | 0 | — | 0.0 | — |
| 20-29 | 0 | — | 0.0 | — |
| 30-39 | 0 | — | 0.0 | — |
| 40-49 | 0 | — | 0.0 | — |
| 50-59 | 1 | 100.0 | 0.0546 | 0.34 |
| 60-69 | 20 | 65.0 | 0.4095 | -0.142 |
| 70-79 | 86 | 75.6 | 0.6491 | 0.004 |
| 80-89 | 51 | 72.5 | 0.5802 | -0.038 |
| 90-99 | 5 | 40.0 | 0.0726 | -0.486 |

Flag fire-rates: rf_stop_sweep 19.0%, rf_divergence_trap 0.6%

Losers cluster: this is the strategy with the most evidence (N=163, the only
one clearing the fold-gate N>=30 floor) and the pattern is not encouraging —
the *highest* decile (90-99) has the *worst* WR (40.0%) and the most
negative expectancy (-0.486R) of any populated bucket, inverted from what a
useful score should show. Losses are concentrated at both the low end
(60-69, 65% WR) and the very top (90-99), with the healthiest band sitting
in the middle (70-79). This non-monotonicity is exactly what G100's
permutation test is designed to catch — see
`docs/superpowers/results/2026-07-gate-frontier.md` for the p-value.

## Volume Profile

Pooled baseline: N=0, WR=—, expectancy_r=—

No decile table — zero closed trades across all three TRAIN fold years.

Flag fire-rates: no fired signals to measure.

Losers cluster: not applicable — no signals fired in this replay.

## Honest summary

5 of 11 strategies (VWAP, Support/Resistance, MACD, Elliott Wave, Volume
Profile) produced **zero** closed trades against this 78-ticker/3-year/2w-
horizon replay — the fold runner's fixed-horizon fallback (see
`folds.py:_default_replay`) is a real limitation, not evidence those
strategies never fire live. Of the 6 that did produce trades, only RSI
Divergence (N=163) clears the N>=30-per-fold floor `apply_fold_gate` and the
plan's own acceptance gates require; EMA Crossover, Fibonacci, MA Ribbon,
Break & Retest and RSI are all N<70 pooled (RSI itself N=5) and should be
read as directional, not decision-grade. This baseline is a census, not a
verdict — G98's frontier run and G100's permutation test are what turn it
into anything actionable.
