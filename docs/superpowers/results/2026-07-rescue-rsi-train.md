# Rescue: RSI — range-regime gate — TRAIN grid (Task 96)

**Hypothesis (pre-registered, spec §11):** RSI dip-buying bleeds in trending
tape; restricting entries to range regimes (low ADX, close inside
Bollinger(20,2)) recovers the edge.

**Command:**

```
python scripts/tune_strategy.py --strategy RSI \
  --grid max_adx=20,25,30 require_bb_range=true,false \
  --exit-model v2 --scale-out
```

Window: TRAIN 2020-01-01..2023-12-31, 75 tickers, all horizons, v2 exit
model with scale-out (same economics as the validation run will use).

## Full grid output

| max_adx | require_bb_range | N | WR% | ExpR | excl% |
|---------|-----------------|-----|-------|--------|-------|
| 20 | True  | 51  | 100.0 | +0.141 | 36 |
| 20 | False | 51  | 100.0 | +0.141 | 36 |
| 25 | True  | 199 | 86.4  | +0.043 | 34 |
| 25 | False | 199 | 86.4  | +0.043 | 34 |
| 30 | True  | 312 | 91.0  | +0.133 | 32 |
| 30 | False | 312 | 91.0  | +0.133 | 32 |

6/6 configs clear the train gates (WR≥80, ExpR>0, N≥30, excl≤50%).

## Selection (pre-registered rule: max ExpR among qualifiers)

**Winner: `max_adx=20, require_bb_range=False`** (ExpR +0.141, WR 100.0, N=51).

- `require_bb_range` changed **zero** trades at every ADX level on TRAIN —
  an RSI oversold-cross entry bar is in practice always inside the bands.
  The ExpR tie between True/False is broken toward `False` (no train
  evidence the extra constraint earns anything; fewer moving parts).
- Note `max_adx=30` qualifies with 6x the sample (N=312, ExpR +0.133);
  the selection rule is ExpR, so 20 wins, but this is recorded for honesty —
  the N=51 sample is thin and 100% WR will not survive validation at face
  value.

**Adopted into `DEFAULT_PARAMS["RSI"]`:** `max_adx=20, require_bb_range=False`.

Verdict: **PASSED-ON-TRAIN** → Task 97 runs the single validation shot.
