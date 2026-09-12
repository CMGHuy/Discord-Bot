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

### Task R14: slope-persistence fallback gate

Added `DEFAULT_PARAMS["VWAP"]["min_vwap_slope_atr"]` (default `None`, gate
off — byte-identical to shipped behavior unless set), and a slope-persistence
filter in `vwap_entries` (`swingbot/core/market/entry_filters.py`) requiring
VWAP's own 8-bar rise (in ATR units) to clear a threshold before a reclaim
counts, in addition to the existing direction-only 3-bar check. TDD (commit
`20ffc201`): 29/29 tests green, reviewed clean.

**TRAIN grid** (`--grid min_vwap_slope_atr=0.15,0.25,0.35`, on the already-4w-narrowed
gate from R11):

| `min_vwap_slope_atr` | N | Win rate | ExpR | excl% | Clears WR>=50, ExpR>0, N>=30, excl<=50%? |
|---|---|---|---|---|---|
| 0.15 | 55 | 54.5% | +0.363 | 29% | yes |
| 0.25 | 51 | 58.8% | +0.449 | 29% | yes |
| 0.35 | 45 | 57.8% | +0.411 | 32% | yes |

**Trap note:** `tune_strategy.py` prints its own gate verdict using a
hardcoded `WR>=80` floor (`scripts/backtest/tune_strategy.py`'s
`report_gate`/`qualifying` filter — the script exposes no `--pass-wr` flag at
all, unlike `run_backtest_range.py`). Its raw run printed "0/3 configs
qualify (WR>=80, ...)" — that verdict is stale-threshold noise and was
**not used**. All three rows above clear the correct, pre-registered
WR>=50 bar; scored by hand from the printed per-config N/WR/ExpR/excl%.

**Plateau verdict: PASS** — 3 of 3 grid points clear (stronger than the
required 2 of 3); not a spike.

**Winning config: `min_vwap_slope_atr=0.25`** — both the value used in R14's
own TDD tests and the grid's best performer (highest WR and ExpR of the
three).

**Fold stability on the winning config** (0.25, measured via a scratch runner
that reuses `run_backtest_range.py`'s own pooling/date-window/STRATEGY_GATES
logic directly, since neither shipped CLI script supports a custom param
override on a custom date range simultaneously — not a new/parallel scoring
implementation):

| Fold year | N | Win rate | ExpR | Badge clauses hold (N>=15, WR>=50, ExpR>0)? |
|---|---|---|---|---|
| 2021 | 17 | 35.3% | +0.007 | no — WR<50 |
| 2022 | 5 | 40.0% | +0.116 | no — N<15 (and WR<50) |
| 2023 | 20 | 70.0% | +0.619 | yes |

- Condition A (>=2/3 folds hold at N>=15): **violated** — only 1 of 3 (2023).
- Condition B (no fold ExpR < -0.05): satisfied — worst is 2021 at +0.007, no
  blowup; same thin-sample signature as R12, not a directional collapse.

**Fold-stability verdict: FAIL.**

**CLOSED.** Neither the 4w re-gate (R12) nor the slope-persistence fallback
(R14) cleared its free stages. VWAP stays `WEAK`; its VALIDATION budget was
never spent and remains available. Reopening needs a genuinely new
mechanism. The `min_vwap_slope_atr` gate itself ships inert (default `None`)
— it is dead code pending a future mechanism, not a live behavior change.
