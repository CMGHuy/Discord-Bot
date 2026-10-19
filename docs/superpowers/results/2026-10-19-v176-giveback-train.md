# v176 TRAIN measurement: runner give-back exit at 5%

**Plan:** [v176 index](../plans/2026-10-19-v176-runner-giveback-exit_0-index.md) (V176-13)
**Spec:** [v176 design](../specs/2026-10-19-v176-runner-giveback-exit-design.md) § Measurement
**Raw results:** `v176/train-close.json` (primary), `v176/train-high_low.json` (sensitivity), each with a `.provenance.json` sidecar
**Looks:** one. Each basis ran once; both JSONs exist, and neither can be rewritten (the script refuses).

## Frozen block (copied from `v176/train-close.json`)

| | |
|---|---|
| window | TRAIN 2020-01-01 .. 2023-12-31. VALIDATION neither run nor read |
| data source | `yfinance`, the 75-ticker local cache |
| engines | `StrategyEngine.iter_trades`, `replay_scenarios` |
| horizons | all ten (2w, 4w, 2m .. 9m), `scale_out=True`, instrument v1 |
| arms | flag off vs on at `pct = 5.0`, the same entries (from the flag-off pass) |
| frictions | slippage 5.0 bps, commission 1.0 per side on a 100.0 risk basis, in both arms |
| cells looked at | 28 |

## Primary reading (close basis): NO-LIFT

| | |
|---|---|
| paired trades `n` | 12,488 |
| ExpR, flag off | +0.0885 |
| ExpR, flag on | +0.0916 |
| **ΔExpR (on − off)** | **+0.0030R, 95% interval [−0.0124, +0.0159]** |
| `p_le_zero` | 0.3238 |
| `mde_paired` | 0.0181R |
| trades whose outcome changed | 334 (2.7% of 12,488) |

Verdict by the rule fixed before the run (PASS if the interval's low end is
above 0, FAIL if its high end is below 0, NO-LIFT if it contains 0): the
interval contains 0, so **NO-LIFT**. The point estimate is smaller than the
smallest effect this sample could reliably detect (0.0181R).

The spec's prior was a pooled effect near 0.01R and |Δ ExpR| under 0.05R, from
two earlier rules aimed at the same runner headroom (v92: +0.0091 to −0.0045R;
v123 `hl_trail`: ≤ +0.0012R). This result sits inside that: a very small
effect of undetermined sign. It neither supports nor refutes the rule as a
profit improvement.

## Tick/close sensitivity (the high/low basis)

Live trading follows the best tick, the backtest follows the best close. Taking
the best price from each bar's high/low instead of its close is the bound on
that gap:

| | close basis | high/low basis |
|---|---|---|
| ΔExpR | +0.0030R | +0.0100R |
| 95% interval | [−0.0124, +0.0159] | [−0.0071, +0.0258] |
| `p_le_zero` | 0.3238 | 0.1221 |
| `mde_paired` | 0.0181R | 0.0211R |
| give-back exits (runner trades closed by the 5% stop) | 334 | 521 |
| changed outcomes | 334 | 521 |
| exits followed by a new best price within 10 bars | 157 (47%) | 273 (52%) |
| exits filled worse than the stop level | 55 | 129 |

The tighter, tick-like basis triggers about 56% more exits and moves the point
estimate three times higher, but the interval still contains 0 on both bases.
Live, where the rule follows every tick, will act closer to the high/low column
than to the close column.

## Descriptive only (28 cells looked at; none is an effect claim)

With 28 cells, one or two apparent horizon "effects" at 5% are expected by
chance, so no horizon is read on its own.

**Per horizon, paired ΔR (close basis).** 2m −0.0033; 2w +0.0056; 3m +0.0030;
4m +0.0057; 4w +0.0009; 5m +0.0054; 6m +0.0051; 7m +0.0037; 8m +0.0012; 9m
+0.0044. Nine of ten are positive, all within 0.006R of zero.

**The 5% band in R.** 5% of the runner's best price is about 2.6R on every
horizon (median 2.63–2.70R, 10th percentile 1.7–2.2R, 90th percentile about
3.0R). The spec's worry that it could be below 1R on long horizons or above 1R
on short ones did not materialise: it is roughly 2.6R on all ten.

**Runner leg (3,951 runner trades), close basis.**

| | flag off | flag on |
|---|---|---|
| mean runner R | 2.349 | 2.369 |
| exits at the floor | 2,563 (64.9%) | 2,446 (61.9%) |
| exit mix: trail | 383 | 180 |
| exit mix: give-back | 0 | 334 |
| exit mix: runner TP2 / timeout | 941 / 64 | 939 / 52 |
| capture (fixed MFE window) | 65.4% | 66.0% |
| days from TP1 to exit, mean (90th pct) | 3.54 (9) | 3.16 (8) |

The give-back mostly replaces trailing-stop exits (383 → 180) and some floor
exits, rather than adding new exits.

**Cost of gaps.** 55 of the 334 give-back exits (16%) filled worse than the stop
level, with a mean gap cost of −0.44R (high/low basis: 129 of 521, −0.88R).

**Book, summed over the paired trades (not a portfolio-constrained equity
curve).**

| | flag off | flag on (close) | flag on (high/low) |
|---|---|---|---|
| total R | 1,105.6 | 1,143.3 | 1,230.4 |
| dollars at $100 risk per trade | 110,557 | 114,330 | 123,038 |
| max drawdown R | 532.0 | 495.4 | 447.0 |
| max drawdown dollars | 53,200 | 49,537 | 44,702 |

Higher total R and a shallower drawdown go with a ΔExpR interval that contains
0: the gain is spread thinly over many trades and is not distinguishable from
no effect at this sample size.

## What this does not license

- The rule is live on production by the partner's decision. This report does
  not change that and never flips `RUNNER_GIVEBACK_ENABLED`.
- A different percent, or an ATR-scaled `p`, is a new pre-registration: grid
  frozen before fold-train, Stage 1 `plateau_report()`, then the harvest
  gate's one-shot VALIDATION. The best cell is not read off this report.
- VALIDATION was neither run nor read, so a future pre-registered give-back
  hypothesis keeps its one shot.
- Live conclusions need at least 30 live give-back exits (`stop_source =
  "giveback"`) compared against `scripts/reports/giveback_live_counterfactual.py`.
