| Direction | Cell | N (decided) | WR | ExpR |
|---|---|---:|---:|---:|
| bullish | baseline (v2) | 249 | 35.3% | +0.231 |
| bullish | #1 structural_only (v2) | 17 | 23.5% | +0.076 |
| bullish | #1 capped_only (v2) | 232 | 36.2% | +0.248 |
| bullish | #2 deeper_stop base (simple) | 282 | 34.8% | +0.204 |
| bullish | #2 deeper_stop arm (simple) | 341 | 36.1% | +0.168 |
| bullish | #2 deeper_stop calibrated (v2+delta) | 341 | 36.7% | +0.195 |
| bullish | #4 reclaim base (simple) | 195 | 44.6% | +0.445 |
| bullish | #4 reclaim arm (simple) | 206 | 26.7% | +0.026 |
| bullish | #4 reclaim calibrated (v2+delta) | 206 | 29.4% | +0.027 |
| bearish | baseline (v2) | 89 | 21.3% | -0.255 |
| bearish | #1 structural_only (v2) | 2 | 0.0% | -0.369 |
| bearish | #1 capped_only (v2) | 87 | 21.8% | -0.248 |
| bearish | #2 deeper_stop base (simple) | 103 | 18.4% | -0.399 |
| bearish | #2 deeper_stop arm (simple) | 105 | 20.0% | -0.365 |
| bearish | #2 deeper_stop calibrated (v2+delta) | 105 | 22.9% | -0.221 |
| bearish | #4 reclaim base (simple) | 59 | 32.2% | +0.029 |
| bearish | #4 reclaim arm (simple) | 59 | 22.0% | -0.259 |
| bearish | #4 reclaim calibrated (v2+delta) | 59 | 25.0% | -0.155 |

| Direction | cap rate | lifecycle rate | over-hard-cap rate | reclaim rate | #2 coverage | #4 coverage | stop mismatches |
|---|---:|---:|---:|---:|---:|---:|---:|
| bullish | 90.3% | 0.6% | 100.0% | 71.9% | 100.0% | 69.4% | 0 |
| bearish | 94.4% | 0.0% | 100.0% | 62.6% | 100.0% | 57.9% | 0 |

Per-horizon rows (description only; #3 is closed):

| Direction | Horizon | baseline N / WR / ExpR | #1 structural N / WR / ExpR |
|---|---|---|---|
| bullish | 2w | 43 | 37.2% | +0.213 | 2 | 50.0% | +0.605 |
| bullish | 4w | 63 | 30.2% | +0.276 | 13 | 15.4% | -0.175 |
| bullish | 2m | 35 | 34.3% | +0.120 | 2 | 50.0% | +0.542 |
| bullish | 3m | 29 | 41.4% | +0.447 | 0 | — | — |
| bullish | 4m | 20 | 35.0% | +0.096 | 0 | — | +0.991 |
| bullish | 5m | 17 | 35.3% | +0.194 | 0 | — | +0.000 |
| bullish | 6m | 15 | 40.0% | +0.252 | 0 | — | +0.000 |
| bullish | 7m | 10 | 30.0% | -0.013 | 0 | — | — |
| bullish | 8m | 8 | 37.5% | +0.057 | 0 | — | — |
| bullish | 9m | 9 | 44.4% | +0.342 | 0 | — | — |
| bearish | 2w | 19 | 47.4% | +0.612 | 1 | 0.0% | -1.000 |
| bearish | 4w | 19 | 31.6% | -0.024 | 0 | — | +0.218 |
| bearish | 2m | 8 | 25.0% | -0.095 | 0 | — | +0.139 |
| bearish | 3m | 6 | 33.3% | -0.063 | 0 | — | -0.503 |
| bearish | 4m | 6 | 0.0% | -0.607 | 0 | — | -0.066 |
| bearish | 5m | 6 | 0.0% | -0.857 | 0 | — | — |
| bearish | 6m | 7 | 0.0% | -0.875 | 0 | — | — |
| bearish | 7m | 7 | 0.0% | -0.778 | 1 | 0.0% | -1.000 |
| bearish | 8m | 6 | 0.0% | -0.750 | 0 | — | — |
| bearish | 9m | 5 | 0.0% | -0.714 | 0 | — | — |

**v93 reproduction:** exact=True observed={'before_rs': 226, 'after_rs': 107, 'n': 89, 'win_rate': 21.3, 'expectancy_r': -0.255} expected={'before_rs': 226, 'after_rs': 107, 'n': 89, 'win_rate': 21.3, 'expectancy_r': -0.255}

**Candidates** (pooled per-direction cells with WR >= 50 and N >= 30):

- none
