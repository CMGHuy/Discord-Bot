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

(To be appended after Step 2's measurement runs — flag off and flag on,
verbatim, per the pre-registered rule above.)
