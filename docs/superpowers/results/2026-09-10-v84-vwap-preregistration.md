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

### Task R12: narrowed TRAIN + fold stability

Narrowed gate (bullish + `{4w}`, landed R11) confirmed applied — only the `4w`
row appears in every run below; no other horizon leaked through.

**Rule 1 — narrowed TRAIN:**

| N | Win rate | ExpR | excl% | Clears rule 1 (WR>=50, ExpR>0, N>=30, excl<=50%)? |
|---|---|---|---|---|
| 68 | 52.9% | +0.335 | 31% | yes |

(Identical to the Task R10 4w-alone row above, as expected — narrowing the
gate to 4w-only does not change the 4w population itself.)

**Rule 2 — fold stability** (FOLD-STABILITY RULE: >=2/3 fold years hold badge
clauses — WR>=50, ExpR>0, N>=15 — each, AND no fold year with
expectancy_r < -0.05):

| Fold year | N | Win rate | ExpR | Badge clauses hold (N>=15, WR>=50, ExpR>0)? |
|---|---|---|---|---|
| 2021 | 24 | 41.7% | +0.137 | no — WR<50 |
| 2022 | 5 | 40.0% | +0.099 | no — N<15 (and WR<50) |
| 2023 | 24 | 62.5% | +0.474 | yes |

- Condition A (>=2/3 folds hold badge clauses at N>=15): **violated** — only
  1 of 3 (2023) qualifies.
- Condition B (no fold year with expectancy_r < -0.05): satisfied — the worst
  fold (2022) is +0.099, nowhere near a blowup; this is a thin-sample problem
  (N=5 in 2022, N=24 in 2021 with WR below floor), not a directional collapse.

**Fold-stability verdict: FAIL** (condition A alone is sufficient to fail the
conjunctive rule). Per the pre-registered rule, rule 2 failing means:
**skip R13 (VALIDATION not spent), proceed to R14 (slope-persistence
fallback).** The pooled TRAIN strength at 4w (N=68, WR 52.9%, ExpR +0.335) does
not hold up year-by-year — 2021 and 2022 are individually sub-floor (2022 on a
thin N=5 sample), only 2023 clears on its own. This is the same class of
failure as EMA Crossover's N-floor closure and Break & Retest's 2022 blowup:
pooled strength that per-year sampling does not support.
