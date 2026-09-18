# v93 entry-context cost measurement

**Edge:** none (integrity)  
**Window:** TRAIN, 2020-01-01..2023-12-31  
**Command:** `python scripts/backtest/run_backtest_range.py --train --strategy MACD --exit-model v2 --scale-out`

## Result

| Context | Run 1 | Run 2 | Mean |
|---|---:|---:|---:|
| off | 45.19 s | 38.47 s | 41.83 s |
| on | 38.44 s | 39.61 s | 39.02 s |

`on / off = 0.933x`, which is within the pre-registered cap of `<= 1.20x`.
The small apparent speed-up is normal run-to-run variance; it is not treated as
an optimization claim.

The context-enabled run wrote `data/v93_macd_train.jsonl`: 192 rows, with
`rs_pctile` non-null on 192/192 rows (100.0%). No precomputation follow-up is
required because the cost cap cleared.
