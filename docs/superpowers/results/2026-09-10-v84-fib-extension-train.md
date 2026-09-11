# v84 — Fibonacci 1.0 extension rescue: TRAIN measurement

**Written 2026-09-10, before any number below exists. Task R33.**

**Edge:** expectancy — adds a strictly-closer target candidate to a
strategy whose targets currently jump >3x in distance past the swing high.

## Pre-registered rule (spec §4.7, verbatim)

*TRAIN win_rate >= 50%, `expectancy_r > 0`, N >= 30, excl <= 50% with the
1.0 candidate added and nothing else changed.*

## Gate declaration (required by methodology)

Adding a target candidate moves geometry by construction, so this change is
**NOT eligible for the six-clause acceptance funnel** — clause 3 (geometry
lock: median planned RR and mean win R may not fall more than 2%) would
reject it by design, and rightly so. **This measurement is judged on the
badge threshold instead** (`win_rate >= 50`, `expectancy_r > 0`, `N >= 30`
train / `N >= 15` validation, scratches+timeouts <= 50%) — a strategy-cell
measurement of Fibonacci's own population, not a feature-vs-baseline effect
scored by `validate_component.py`'s funnel. Expected trade: win rate up,
some ExpR spent. The +0.232 baseline cushion is what funds it, and
`expectancy_r > 0` is the hard floor that stops the trade from going too
far.

## Baseline (flag off, current shipped behavior)

**N=246, WR=35.4%, ExpR=+0.232.**

## Results

| Flag | N | Win rate | ExpR | excl% | Clears WR>=50, ExpR>0, N>=30, excl<=50%? |
|---|---|---|---|---|---|
| off (baseline, verbatim) | 246 | 35.4% | +0.232 | 30% | no — WR 35.4 < 50 |
| on (1.0 extension added) | 245 | 35.5% | +0.233 | 31% | no — WR 35.5 < 50 |

Flag-off reproduces the pre-registered baseline exactly (N=246, WR=35.4%,
ExpR=+0.232), confirming the measurement is apples-to-apples.

## Observation

The 1.0 extension candidate had almost no effect on this population: N moved
by exactly 1 trade (246 -> 245), win rate by 0.1pp, ExpR by 0.001. This is
not the "win rate up, some ExpR spent" trade the pre-registration anticipated
— it's essentially a null result. `select_structural_target` picks the
nearest qualifying candidate, so the 1.0 extension only changes a trade's
outcome when price actually lands in the gap between `swing_high` and the
1.272 extension *and* that changes which level ends up nearest-qualifying
within the RR band; apparently very few TRAIN trades in this population's
entry geometry actually fall there. The hypothesis (a >3x candidate-distance
gap exists) was correct, but very few live trades are positioned to be
affected by filling it.

Both flag-off and flag-on miss the WR>=50 floor by roughly the same, large
margin (14.6pp / 14.5pp) — consistent with the Tier 3 introduction's own
framing ("Fibonacci is 14.6pp short of the floor"): this component was never
going to close a 14-point gap, and the TRAIN measurement confirms it does
not.

## Verdict

**FAIL — flag-on does not clear the badge threshold** (WR 35.5% vs the 50%
floor, missing by 14.5pp). Per the pre-registered branch: **stop here.**
Fibonacci is **CLOSED**. R34 (Stage 2 walkforward) and R35 (VALIDATION) do
not run. The negative result carries into R42/R45 (closed-pre-registration
rows). The VALIDATION shot stays unspent. Per Global Constraints ("Record
failures as-is"), this is a finished measurement, not a stub — the 1.0
extension candidate remains in the codebase, gated off by
`FIB_TARGET_1_0_EXTENSION` (default `False`), permanently inert unless a
genuinely new mechanism reopens the question.
