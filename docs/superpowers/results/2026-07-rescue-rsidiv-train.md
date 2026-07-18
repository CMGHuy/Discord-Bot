# Rescue: RSI Divergence — confirmation-quality gate — TRAIN grid (Tasks 99–100)

**Hypothesis (pre-registered, spec §11):** divergence reclaim bars with real
volume behind them and meaningful reclaimed ground filter out the weak
signals dragging WR under 80.

**Command:**

```
python scripts/tune_strategy.py --strategy "RSI Divergence" \
  --grid min_volume_ratio=1.0,1.2,1.5 min_reclaim_strength=0.3,0.5,0.7 \
  --exit-model v2 --scale-out
```

Window: TRAIN 2020-01-01..2023-12-31, 75 tickers, all horizons, v2 exits +
scale-out. (Implementation note: the detector is a rolling formulation, so
reclaim strength is measured from the rolling 20-bar swing low toward the
20-bar range midpoint — see the Task 98 commit message.)

## Full grid output

| min_volume_ratio | min_reclaim_strength | N | WR% | ExpR | excl% |
|------------------|---------------------|------|------|--------|-------|
| 1.0 | 0.3 | 1068 | 76.1 | +0.190 | 23 |
| 1.0 | 0.5 | 733  | 73.4 | +0.172 | 25 |
| 1.0 | 0.7 | 404  | 75.0 | +0.152 | 24 |
| 1.2 | 0.3 | 552  | 75.7 | +0.212 | 24 |
| 1.2 | 0.5 | 437  | 74.1 | +0.221 | 22 |
| 1.2 | 0.7 | 225  | 72.0 | +0.118 | 25 |
| 1.5 | 0.3 | 245  | 74.3 | +0.081 | 18 |
| 1.5 | 0.5 | 194  | 68.0 | +0.016 | 19 |
| 1.5 | 0.7 | 114  | 63.2 | +0.057 | 24 |

**0/9 configs qualify** (WR≥80, ExpR>0, N≥30, excl≤50%). Best WR is 76.1%
(the least restrictive config) — tightening either knob only *lowers* WR
while shrinking N, the opposite of the hypothesis. Expectancy stays positive
everywhere (the strategy is not a loser, just under the 80% WR bar).

## Verdict (pre-registered rule)

**REJECTED-ON-TRAIN.** No parameter adopted — `DEFAULT_PARAMS["RSI
Divergence"]` keeps the gate off (`min_volume_ratio=None,
min_reclaim_strength=None`). Task 100's validation run is **skipped** (the
validation window is a budget; a config that fails train never gets a shot
at it). The registry record stays WEAK (75.8% / N=1101 from round 1).

The confirmation-quality hypothesis is falsified on train: divergence
quality, as measured by reclaim volume and depth, does not separate winners
from losers for this rolling detector.
