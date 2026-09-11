# v84 — RSI Divergence rescue: TRAIN grid result

**Written 2026-09-10, Task R17.**

**Edge:** expectancy — attempted removal of a negative-expectancy sub-population
via a stricter reclaim-persistence requirement.

## Pre-registered rule (spec §4.4, verbatim)

TRAIN grid `min_consecutive_rsi_turn ∈ {2, 3, 4}`; a config qualifies at
WR>=50, ExpR>0, N>=30, excl<=50%, and must show a plateau across adjacent
values, not a lone spike. 0/3 qualifying => REJECTED-ON-TRAIN, permanently
WEAK, no VALIDATION spent.

Baseline to beat (K=1, current shipped behavior): **N=1534, WR 48.0%,
ExpR +0.257**.

## Grid route

Env-var route (`RSI_DIV_MIN_CONSECUTIVE_TURN=<K> python scripts/backtest/run_backtest_range.py ...`)
was used. Confirmed it reaches `config` at import: `swingbot/config.py`'s
`_apply_env()` (called at module import, line 1012) reads
`os.getenv(f.key, f.default)` for every `FIELDS` entry — this reads the live
process environment, and `RSI_DIV_MIN_CONSECUTIVE_TURN` is a brand-new field
(added Task R16) with no entry in `.env`, so `load_dotenv(override=True)`
never touches it and the shell-exported value passes through untouched.

## Results

| K (`min_consecutive_rsi_turn`) | N | Win rate | ExpR | excl% | Clears WR>=50, ExpR>0, N>=30, excl<=50%? |
|---|---|---|---|---|---|
| 2 | 473 | 49.0% | +0.269 | 29% | no — WR 49.0 < 50 (misses by 1.0pp) |
| 3 | 70 | 28.6% | -0.262 | 22% | no — WR and ExpR both fail |
| 4 | 10 | 10.0% | -0.326 | 50% | no — WR, ExpR, and N (10 < 30) all fail |

All three cells report distinct N (473 / 70 / 10, all <= the K=1 baseline's
1534), confirming the override actually took effect at each grid point — not
three identical runs of K=1.

**0/3 qualify.**

## Plateau check (sanctioned instrument, `backtest_wf.plateau_report`)

Computed for completeness per Step 3, even though the absolute-threshold gate
above already rejects the campaign on its own:

```
plateau_report("min_consecutive_rsi_turn", grid=[2,3,4],
                expectancies=[+0.269, -0.262, -0.326], adopted=2)
-> {'neighbors': {3: -0.262}, 'is_plateau': False}
```

`PLATEAU_TOLERANCE_R = 0.03`; the gap between K=2 (+0.269) and its only
in-grid neighbor K=3 (-0.262) is 0.531 — over 17x the tolerance.
**`is_plateau: False`.** The best-looking cell (K=2) is an isolated spike,
not a stable regime — reinforcing, independently of the WR miss, that K=2
is not a config to adopt.

## Observations

The direction of this result is the opposite of what the hypothesis
predicted: persistence (K=2) does not clearly improve on baseline (WR 49.0%
vs baseline 48.0% — statistically indistinguishable, +1.0pp on N=473), and
further persistence (K=3, K=4) makes the population **dramatically worse**,
not just smaller. K=4's 10% win rate on N=10 and K=3's 28.6% on N=70 suggest
that requiring RSI to move for 3-4 *consecutive* bars selects for a
qualitatively different (and worse) kind of setup than the single-uptick
reclaim this strategy is built around — plausibly late-stage/exhausted moves
rather than fresh reclaims, though this task does not investigate the
mechanism. This is a real, informative negative result, not a bug: N differs
cleanly across all three cells (ruling out a stuck override), and the
direction is consistent and monotonic (worse as K increases), not noisy.

## Verdict

**REJECTED-ON-TRAIN.** 0/3 grid cells qualify, and the best cell is
independently confirmed to be a spike (`is_plateau: False`), not a plateau.
RSI Divergence's `min_consecutive_rsi_turn` gate stays permanently WEAK
(shipped at its default `1` = off, byte-identical to pre-R16 behavior — see
`docs/superpowers/results/...` R16 test coverage). **No VALIDATION spent; no
Stage 2 walkforward (R18) runs for this strategy.** Per the plan's Global
Constraints ("Record failures as-is. An empty results table is a finished
measurement, not a stub"), this closes the RSI Divergence rescue line here.
