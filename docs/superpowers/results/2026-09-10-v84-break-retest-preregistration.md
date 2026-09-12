# v84 — Break & Retest rescue: PRE-REGISTRATION

**Written 2026-09-10, before the gated TRAIN, fold or VALIDATION runs.**

**Edge:** expectancy — removes a negative-expectancy sub-population.

## Hypothesis

Break & Retest fails pooled (TRAIN WR 48.0%, N=298) but is **bimodal by
horizon, not uniformly weak**: 2m/3m/4m clear the floor (53.1%/57.1%/51.4%,
ExpR +0.38/+0.32/+0.21) while 6m is the only negative-ExpR cell (27.8%,
-0.157) and 7m/8m/2w sit at 42.9-46.7%. The structural claim: a
breakout-retest works while the break is fresh and decays as the level ages.

Restricting to `{2m, 3m, 4m}` scores **N=105, WR 53.3%, ExpR ~+0.31** on the
population already measured.

**Genuinely new:** no closed pre-registration touches per-strategy horizon
scoping. `STRATEGY_GATES` has no `"Break & Retest"` key today — this ADDS one;
the masking machinery (`entry_filters.entries_for`, line 146) already exists
and is exercised by seven other strategies.

## The overfit risk, stated plainly

The qualifying subset was **identified from the same TRAIN table that scores
it**. The plateau check below exists precisely to catch that, and it is
disqualifying, not advisory.

## Pre-registered rule

1. **Plateau (Stage 1), computed from Task R5's ungated per-horizon table —
   no new run:** pool `{2m,3m,4m}` and its four neighbours-by-one-horizon:
   `{2m,3m}`, `{3m,4m}`, `{2m,3m,4m,5m}`, `{2m,3m,4m,4w}`. **PASS** = the
   chosen `{2m,3m,4m}` clears WR>=50 with N>=30 **and at least two of those
   four neighbours also clear WR>=50 with N>=30**. A chosen subset that is an
   isolated peak among its neighbours is a spike, not a plateau, and is
   **REJECTED here** — no gate is landed and no further run happens.
2. **Gated TRAIN (Task R8):** with the gate live, pooled WR>=50, ExpR>0,
   N>=30, excl<=50%.
3. **Fold stability (Task R8):** the FOLD-STABILITY RULE.
4. **VALIDATION (Task R9):** one shot, only if 1-3 all pass.

Any failure closes Break & Retest at that stage with no VALIDATION spent.

## Results

### Task R5 baseline (verbatim, full 77-ticker universe, 2 excluded illiquid)

```
Strategy               Horiz      N   Win%    ExpR
Break & Retest         2m        49   53.1  +0.380
Break & Retest         2w        21   42.9  +0.207
Break & Retest         3m        21   57.1  +0.316
Break & Retest         4m        35   51.4  +0.207
Break & Retest         4w        71   47.9  +0.224
Break & Retest         5m        35   48.6  +0.308
Break & Retest         6m        18   27.8  -0.157
Break & Retest         7m        16   43.8  +0.018
Break & Retest         8m        15   46.7  +0.115
Break & Retest         9m        17   47.1  +0.175
```

Pooled: N=298, Win% 48.0, ExpR +0.210. FAIL (win rate).

Note: this re-run's per-horizon numbers replaced an earlier run of this same
command that silently used a stale 3-ticker worktree watchlist stub (N=26
total) — that result was discarded before being used for anything. This table
is the corrected, full-universe measurement and matches the original
brainstorming-phase research to within rounding.

### Plateau check (Task R6)

Win counts recovered from `round(N * Win%)` on the table above (each resolves
to a whole number, confirming no rounding ambiguity): 2m=26/49, 3m=12/21,
4m=18/35, 5m=17/35, 4w=34/71.

| Subset | N | Win rate | Clears WR>=50, N>=30? |
|---|---|---|---|
| {2m,3m,4m} (chosen) | 105 | 53.3% | yes |
| {2m,3m} | 70 | 54.3% | yes |
| {3m,4m} | 56 | 53.6% | yes |
| {2m,3m,4m,5m} | 140 | 52.1% | yes |
| {2m,3m,4m,4w} | 176 | 51.1% | yes |

**Plateau verdict: PASS** — 4 of 4 neighbours also clear (stronger than the
required 2 of 4). The advantage is not an isolated peak; it degrades smoothly
as 5m or 4w is added back, which is the signature of a real horizon-decay
effect rather than a fitted spike.

### Gated TRAIN (Task R8)

75/77 tickers (2 excluded illiquid: GC=F, SI=F). Gate confirmed applied —
only 2m/3m/4m rows appear.

| N | Win rate | ExpR | excl% | Clears rule 2? |
|---|---|---|---|---|
| 105 | 53.3% | +0.308 | 23% | yes |

### Fold stability (Task R8)

| Fold year | N | Win rate | ExpR | Badge clauses hold (N>=15)? |
|---|---|---|---|---|
| 2021 | 32 | 56.2% | +0.355 | yes |
| 2022 | 14 | **14.3%** | **-0.343** | no |
| 2023 | 36 | 58.3% | +0.425 | yes |

**Verdict: FAIL.** The FOLD-STABILITY RULE has two independent conditions, and
this fails the second one even though it clears the first:

- Condition A (>=2/3 folds hold badge clauses at N>=15): **satisfied** — 2021
  and 2023 both qualify, 2/3.
- Condition B (no fold year with expectancy_r < -0.05, regardless of N):
  **violated** — 2022 scores -0.343R, a severe single-year blowup the pooled
  TRAIN number (+0.308 across all four years) and the gated-TRAIN row above
  both completely mask.

Per the rule's own text, "anything else is FAIL" — the count condition passing
does not override a fold this far below the degradation floor. This is exactly
what condition B exists to catch: a setup that looks strong pooled but blew up
badly in one specific year (2022 — plausibly the rate-hike/bear-market regime,
though this task does not investigate why).

**CLOSED before VALIDATION.** The gate stays landed: it removes a horizon
population measured negative on TRAIN (6m at -0.157R), which is worth keeping
independently of the badge outcome. The VALIDATION budget was **NOT spent**
and remains available. Reopening this specific badge question needs a
genuinely new mechanism (e.g. something that addresses the 2022-style failure
mode directly), not a re-run.
