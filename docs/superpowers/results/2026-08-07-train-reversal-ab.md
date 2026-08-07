# TRAIN A/B — does the reversal rule do anything?

**Date:** 2026-08-07
**Window:** TRAIN, 2020-01-01 → 2023-12-31
**Data:** `data/backtest_cache/` fetched 2026-08-07, 75 tickers (same snapshot
as `2026-08-07-train-baseline-prereversal.md`)
**Command:** `python scripts/reversal_ab.py --train`
**Signals:** 1844, collected once and replayed by all three arms, so the arms
differ only in the position rule — not data, window, frictions, or exit model.

## Headline

**The reversal rule fired zero times over four years of TRAIN.** It is not
marginal or noisy — it is structurally inert on this signal set. Arm C is
byte-identical to arm B.

## Results

| Arm | Rule | Taken | Skip | ExpR | Final× | MaxDD% | Flips |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A current | several positions per ticker | 701 | 1143 | +0.1716 | 3.1929 | 9.9 | 0 |
| B one-per-ticker | at most one, opposite blocked | 689 | 1155 | +0.1442 | 2.6388 | 7.3 | 0 |
| C reversals | as B, opposite cuts short | 689 | 1155 | +0.1442 | 2.6388 | 7.3 | **0** |

vs A: both B and C give **-0.0274R expectancy**, **-0.554× final multiple**,
**-2.5pp max drawdown**.

## Why the reversal never fires

Not a guard being too strict — the guards were never reached. Measured over
the 1844 signals:

| Measure | Value |
| --- | --- |
| Median holding period | **5 days** (mean 10.8, max 107) |
| Median gap to the nearest opposite-direction signal on the same ticker | **199 days** |
| Closest opposite-direction pair, ever | 15 days |
| Opposite signals within 30 days of one another | 0.8% |
| Tickers producing **both** directions | 56 of 70 |
| Opposite signal arriving while a position is open | **0** |

A direct scan for "bearish signal inside a bullish holding window (or the
reverse)" returns zero hits across every ticker. Positions close in about a
week; the opposite setup shows up roughly two hundred days later.

This is a property of the signal generator, not of the reversal code. The
regime filter and HTF bias gate make the bot directionally persistent: while
it is long a name, it does not simultaneously produce a qualifying short on
it. A rule that only triggers on simultaneous opposing setups therefore has
nothing to act on.

An instrumented replay with the guards effectively disabled (min hold 1 day,
no cooldown, no daily cap) still produced 0 eligible flips — 561 same-ticker
collisions, every one of them same-direction.

## What this does and does not license

- **Reversal:** no measured effect over TRAIN, positive or negative. This is
  not evidence that it works; it is evidence that it does not engage. It
  currently ships **enabled by default** in live trading, adding a code path
  and four settings that this window says will essentially never execute.
- **One trade per ticker:** this one *does* bite, and it is a genuine
  trade-off, not a free win. It cost **17% of the final multiple**
  (3.19× → 2.64×) and 0.027R of expectancy, while cutting max drawdown by
  2.5pp. Twelve fewer trades were taken (701 → 689); the outsized effect on
  the multiple is compounding, so treat the exact figure as path-dependent
  rather than precise.

## Fidelity gaps (both make C flip MORE than production would)

- **No confidence-margin guard.** `BacktestTrade` carries no confidence
  score, so live's `REVERSAL_MIN_CONF_MARGIN` cannot be applied here. Every
  opposite signal was a candidate and still none qualified.
- **Guards in days, not hours.** Signals are dated, not timestamped.

Because both gaps loosen the rule, the zero-flip result is an *upper* bound
on how often reversals would fire live. Production, with the confidence
margin applied, would fire at most as often — that is, also never.

## Honest limitations

- One window, one cache snapshot, one universe. TRAIN 2020-2023 contains a
  violent regime change (2020, 2022); if opposing setups do not co-occur
  *there*, they are unlikely to elsewhere, but this is not proof.
- The portfolio-replay metric here (expectancy over taken trades, final
  multiple, max drawdown) is **not** the per-strategy acceptance gate used in
  `2026-08-07-train-baseline-prereversal.md`. The two documents answer
  different questions and their numbers are not interchangeable.
- VALIDATION was not touched. Per the methodology it is a budget spent once,
  and there is nothing here worth spending it on.

## Recommendation

Set `REVERSAL_ENABLED=false`. It is unvalidated in live trading and this run
shows it has nothing to act on, so it is pure risk surface. Revisit only if
the signal generator is ever changed to allow opposing setups to co-exist.

Decide `one_per_ticker` deliberately: it is currently live and it measurably
trades return for drawdown. That may well be the right call for a paper
account being read as a risk model — but it should be a choice, not a
side effect of a duplicate-prevention change.
