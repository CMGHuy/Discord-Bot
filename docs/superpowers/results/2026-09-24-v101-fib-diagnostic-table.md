| Direction | Cell | N (decided) | WR | ExpR |
|---|---|---:|---:|---:|
| bullish | baseline (v2) | 288 | 28.8% | +0.039 |
| bullish | #1 structural_only (v2) | 0 | — | — |
| bullish | #1 capped_only (v2) | 288 | 28.8% | +0.039 |
| bullish | #2 deeper_stop base (simple) | 367 | 27.8% | -0.081 |
| bullish | #2 deeper_stop arm (simple) | 368 | 27.7% | -0.087 |
| bullish | #2 deeper_stop calibrated (v2+delta) | 368 | 28.7% | +0.034 |
| bullish | #4 reclaim base (simple) | 214 | 45.8% | +0.475 |
| bullish | #4 reclaim arm (simple) | 218 | 25.7% | -0.142 |
| bullish | #4 reclaim calibrated (v2+delta) | 218 | 35.9% | +0.013 |
| bearish | baseline (v2) | 94 | 25.5% | -0.091 |
| bearish | #1 structural_only (v2) | 0 | — | — |
| bearish | #1 capped_only (v2) | 94 | 25.5% | -0.091 |
| bearish | #2 deeper_stop base (simple) | 119 | 22.7% | -0.268 |
| bearish | #2 deeper_stop arm (simple) | 119 | 22.7% | -0.265 |
| bearish | #2 deeper_stop calibrated (v2+delta) | 119 | 25.5% | -0.088 |
| bearish | #4 reclaim base (simple) | 61 | 44.3% | +0.426 |
| bearish | #4 reclaim arm (simple) | 60 | 26.7% | -0.085 |
| bearish | #4 reclaim calibrated (v2+delta) | 60 | 49.1% | +0.246 |

| Direction | cap rate | lifecycle rate | over-hard-cap rate | reclaim rate | #2 coverage | #4 coverage | stop mismatches |
|---|---:|---:|---:|---:|---:|---:|---:|
| bullish | 100.0% | 41.3% | 41.3% | 72.5% | 100.0% | 58.4% | 0 |
| bearish | 100.0% | 32.2% | 32.2% | 65.3% | 100.0% | 51.2% | 0 |

Per-horizon rows (description only; #3 is closed):

| Direction | Horizon | baseline N / WR / ExpR | #1 structural N / WR / ExpR |
|---|---|---|---|
| bullish | 2w | 42 | 31.0% | +0.076 | 0 | — | — |
| bullish | 4w | 92 | 29.3% | +0.057 | 0 | — | — |
| bullish | 2m | 42 | 26.2% | +0.041 | 0 | — | — |
| bullish | 3m | 32 | 40.6% | +0.454 | 0 | — | — |
| bullish | 4m | 22 | 31.8% | -0.023 | 0 | — | — |
| bullish | 5m | 16 | 31.2% | +0.142 | 0 | — | — |
| bullish | 6m | 15 | 13.3% | -0.475 | 0 | — | — |
| bullish | 7m | 10 | 10.0% | -0.415 | 0 | — | — |
| bullish | 8m | 8 | 0.0% | -0.889 | 0 | — | — |
| bullish | 9m | 9 | 44.4% | +0.271 | 0 | — | — |
| bearish | 2w | 18 | 44.4% | +0.833 | 0 | — | — |
| bearish | 4w | 19 | 31.6% | +0.024 | 0 | — | — |
| bearish | 2m | 6 | 66.7% | +0.567 | 0 | — | — |
| bearish | 3m | 5 | 0.0% | -0.625 | 0 | — | — |
| bearish | 4m | 8 | 12.5% | -0.410 | 0 | — | — |
| bearish | 5m | 6 | 16.7% | -0.324 | 0 | — | — |
| bearish | 6m | 8 | 12.5% | -0.492 | 0 | — | — |
| bearish | 7m | 9 | 11.1% | -0.544 | 0 | — | — |
| bearish | 8m | 8 | 12.5% | -0.492 | 0 | — | — |
| bearish | 9m | 7 | 14.3% | -0.435 | 0 | — | — |

**v93 reproduction:** exact=False observed={'before_rs': 246, 'after_rs': 121, 'n': 94, 'win_rate': 25.5, 'expectancy_r': -0.091} expected={'before_rs': 226, 'after_rs': 107, 'n': 89, 'win_rate': 21.3, 'expectancy_r': -0.255}

**Candidates** (pooled per-direction cells with WR >= 50 and N >= 30):

- none
