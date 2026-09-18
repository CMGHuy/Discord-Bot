# v93 bearish-arm TRAIN re-derivation

**Edge:** volume (conditional on v93 Phase 1)  
**Window:** TRAIN, 2020-01-01..2023-12-31; cached liquidity-filtered universe (88 symbols).  
**Arithmetic:** v2 exits, scale-out, TP2 levels, frictions on. Each arm was measured unmasked, then filtered by the live `rs_combined` laggard rule. No VALIDATION data was used.

## Fixed decision rule

Clear Stage 1 only with WR >= 50%, ExpR > 0, decided N >= 30, scratch+timeout share <= 50%, and at least two anchored test-year folds with N >= 15 and positive ExpR. If the current mask and all-horizon arm both fail, Stage 2 is available only when all-horizon ExpR is positive and WR is below 50%; a contiguous subset must independently clear Stage 1 and its four drop/extend neighbours must meet the plateau gate. The winner is the highest-ExpR cleared subset.

## Results

| Strategy | Before RS | After RS | Masked N | Masked WR | Masked ExpR | Decision |
|---|---:|---:|---:|---:|---:|---|
| Fibonacci | 226 | 107 | 89 | 21.3% | -0.255 | fail |
| RSI | 30 | 10 | 10 | 0.0% | -1.000 | fail |
| MA Ribbon | 145 | 76 | 61 | 42.6% | +0.171 | fail |
| VWAP | 149 | 66 | 8 | 12.5% | -0.245 | fail |
| Support/Resistance | 691 | 427 | 69 | 36.2% | +0.025 | fail |
| MACD | 368 | 157 | 19 | 52.6% | +0.200 | fail |
| Volume Profile | 918 | 362 | 12 | 25.0% | -0.238 | fail |

All seven decisions are `fail`. No direction mask changes and no registry re-emissions are authorized. MACD and Volume Profile are recorded but not enabled: their existing VALIDATED population must not be diluted by an unvalidated bearish arm.

The machine-readable evidence is retained locally as `data/v93_arms_<strategy>.json`; each file includes both Stage 1 arms, anchored-fold statistics, and every Stage 2 candidate.
