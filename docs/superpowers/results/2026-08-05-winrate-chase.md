# Chasing a >=70% win rate (human-partner directive, 2026-08-05)

**Directive:** get the win rate above 70% for all strategies, trying every
possibility, tuning against the historical data. Recorded because both axes
used here were previously gated — `MAX_LOSS_PCT` by the V19/V51 note
("pre-registration + explicit human approval, or not at all") and the payoff
structure generally by V10, which raised targets deliberately. The directive
is that approval.

Harness `scripts/winrate_grid.py`. Raw output
`2026-08-05-winrate-grid.json` (main grid) and
`2026-08-05-winrate-laggards.json` (follow-up). 67 tickers x 10 horizons,
TRAIN 1999-2023, exit v2, frictions on, gates as shipped.

## Which knob actually sets win rate

A trade wins when TP1 is hit before the stop, and all four sizing builders
price `TP1 = entry ± risk_distance * rr` with the stop at `risk_distance`. So
the *ratio* of target distance to stop distance is `rr`, and that ratio is the
hit rate.

- **`MAX_LOSS_PCT` is not a win-rate knob.** `cap_risk_distance` runs *before*
  the target is derived, so widening the cap scales target and stop together
  and leaves the ratio — hence the hit rate — essentially unchanged. It was
  not swept here for that reason.
- **`MIN_TARGET_PCT` is the dominant knob**, as a spoiler: `apply_target_floor`
  pushes TP1 back out to the floor, which is exactly why the shipped 2.5%
  floor sits at ~46% win rate. Lowering it out of the way is what raises the
  hit rate.
- **`rr` matters much less than expected.** `_sr_plan` and `_fibonacci_plan`
  derive targets from *structure*, not from `rr`, so the override only reaches
  the ATR-based builders. At floors 1.0 and 1.5 all three rr values return
  **bit-identical** results.

## Result: 5 of 11 strategies clear 70%, pooled 69.9%

Best configuration: `rr = 0.15`, target floor **0%** (floor disabled),
scale-out **on**, TP2 `levels`.

| strategy | N | Win% | WilsonLB | ExpR |
|---|---|---|---|---|
| **Break & Retest** | 2,369 | **80.2** | 78.6 | +0.112 |
| **VWAP** | 998 | **76.8** | 74.0 | +0.178 |
| **MA Ribbon** | 1,770 | **75.8** | 73.8 | +0.118 |
| **Volume Profile** | 645 | **75.5** | 72.0 | +0.129 |
| **MACD** | 1,089 | **75.2** | 72.6 | +0.067 |
| Fibonacci | 1,698 | 70.0 | 67.7 | +0.072 |
| RSI Divergence | 9,870 | 66.5 | 65.5 | −0.031 |
| Support/Resistance | 2,206 | 66.2 | 64.2 | −0.035 |
| EMA Crossover | 278 | 65.1 | 59.3 | −0.029 |
| RSI | 170 | 64.7 | 57.3 | −0.227 |
| Elliott Wave | 614 | 59.9 | 56.0 | −0.090 |

Pooled across all strategies: **69.9% (LB 69.3), N = 21,707**, against the
shipped configuration's 46.1%.

The floor is the whole effect. Pooled win rate by floor, at rr=0.15:
0% → 69.9, 0.5% → 67.2, 1.0% → 60.7, 1.5% → 55.2, and (from the earlier
sweep) 2.5% → 46.1.

## The six that fell short do not respond to the exit model

Re-run with `--no-scale-out --tp2 none`, which makes a win purely "TP1 hit
first" — the most favourable possible labelling:

| strategy | Win% scale-out ON | Win% OFF | ExpR ON | ExpR OFF |
|---|---|---|---|---|
| Fibonacci | 70.0 | 69.9 | +0.072 | −0.188 |
| RSI Divergence | 66.5 | 66.6 | −0.031 | −0.227 |
| Support/Resistance | 66.2 | 66.1 | −0.035 | −0.232 |
| EMA Crossover | 65.1 | 65.1 | −0.029 | −0.248 |
| RSI | 64.7 | 64.7 | −0.227 | −0.256 |
| Elliott Wave | 59.9 | 59.8 | −0.090 | −0.306 |

Win rate moves by **at most 0.1 points** — the labelling was already
TP1-based, so removing the runner changes nothing about the hit rate. What it
does change is expectancy, which collapses to −0.188…−0.306 (pooled −0.227,
max drawdown −100.0%). That is a useful side finding in its own right: **the
runner leg was carrying all of the earnings** in these six.

So `>=70% for all eleven` is not reachable with these levers. Elliott Wave
tops out near 60%, and four others sit in the 64-67% band regardless of exit
model.

## What the win rate costs, measured

- **Max drawdown is −99.9%** at the top configurations, against −95.9% at a
  1.5% floor and −94.4% at the shipped 2.5%. Whatever the hit rate, that is
  the equity path.
- **Expectancy is positive but tiny**: +0.021R pooled at the best-win-rate
  cell, versus +0.168R at the shipped floor. Raising win rate 46% → 70%
  *lowered* pooled expectancy by ~0.15R. Six of eleven strategies go
  outright negative.
- **Every expectancy here is under V51's +0.318R daily-bar overstatement**, so
  none of them is distinguishable from zero on the standard this plan applied
  to V53, V54 and the target-floor sweep.

## A metric in this harness is wrong — do not trust its break-even column

`_breakeven_wr` computes `1/(1+rr)`, which assumes a win banks exactly `rr`.
That is false under scale-out: the runner leg can earn well beyond TP1. It is
why cells show 80% observed win rate against an "87% break-even" and *still*
measure positive expectancy, and why the harness's
"beats its own break-even: NONE" line is meaningless as printed. **The
measured `ExpR` is the trustworthy figure; the BE-WR column is not.** Left in
the output rather than silently deleted, so this note explains numbers a
reader will otherwise see and believe.

## Status

**Nothing applied live.** `MIN_TARGET_PCT` remains 2.5 and
`STRATEGY_RR_OVERRIDE` is untouched. Adopting the 70% configuration would
reverse V10 — which raised targets precisely because the pre-V10 book had a
0.85% median target against a 2.19% stop and lost money — and is a decision
for the human partner with the drawdown and expectancy figures above in hand.
