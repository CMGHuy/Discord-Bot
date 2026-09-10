# v84 — VWAP rescue: PRE-REGISTRATION

**Written 2026-09-10, before the narrowed TRAIN, fold or VALIDATION runs.**

**Edge:** expectancy — removes a negative-expectancy sub-population.

## Hypothesis

VWAP's live gate (`strategy_types.py:212`, bullish + `{4w,6m,7m,8m,9m}`) was
hand-calibrated against the pre-v31 fixed reward:risk table and never
re-derived -- its own source comment cites WR=82.0, a number from the deleted
80%-floor era. Under current arithmetic the pooled row fails (44.5%) but the
failure is entirely the four long horizons: 4w alone scores **N=68, WR 52.9%,
ExpR +0.335**, while 9m sits at 11.1% (N=9, -0.519R).

Narrowing the gate to bullish + `{4w}` is a re-derivation of an existing,
admittedly-stale mask -- not a new mechanism.

## Pre-registered rule

1. **TRAIN (Task R12):** with the narrowed gate, WR>=50, ExpR>0, N>=30,
   excl<=50%.
2. **Fold stability (Task R12):** the FOLD-STABILITY RULE (>=2/3 fold years
   hold badge clauses at N>=15 each, no fold year with expectancy_r < -0.05).
3. **VALIDATION (Task R13):** one shot, only if 1-2 pass.
4. **Fallback (Task R14) -- runs ONLY if rule 1 or 2 FAILS:** the
   slope-persistence gate (spec 4.3), tested on the same 4w population. If the
   fallback's own TRAIN + fold check fails, VWAP is closed permanently with no
   VALIDATION spent.

N=68 at 4w on TRAIN is the whole sample; at VALIDATION the badge floor is
N>=15. If the narrowed TRAIN N falls below 30, rule 1 fails and the fallback
is what gets tested -- shrinking N to reach a win rate is explicitly not
allowed.

## Results

### Task R10 baseline (verbatim, full 75/77-ticker universe, current gate)

```
Strategy               Horiz      N   Win%    ExpR
VWAP                   4w        68   52.9  +0.335
VWAP                   6m        14   35.7  -0.078
VWAP                   7m        15   40.0  +0.093
VWAP                   8m        13   38.5  +0.022
VWAP                   9m         9   11.1  -0.519
```

Pooled: N=119, Win% 44.5, ExpR +0.161. FAIL (win rate). Confirms the
hypothesis exactly: the four dropped horizons (6m/7m/8m/9m, N=14/15/13/9) are
each individually sub-floor, with 9m badly negative.

(Narrowed TRAIN and fold stability by Task R12; VALIDATION by Task R13.)
