# v143 FVG (bullish) badge diagnostic: result

**Run:** 2026-10-09, TRAIN 2020-01-01..2023-12-31 (signal date), 75 cached tickers, ten horizons. Read-only; VALIDATION never read.
**Spec:** `docs/superpowers/specs/2026-10-09-v143-fvg-bullish-badge-diagnostic-design.md`

**Verdict: NO CANDIDATE.** FVG (bullish) stays WEAK.

9 features at 3 geometries is 27 looks. At a 5% false-positive rate one or two chance hits are expected; a candidate below has earned a spec, not a filter.

**Population N = 1278** (expected 1278). **Unidentified: 0 (0.0%)** have no bullish gap, on the window the level map was built on, within the confluence tolerance of a scenario level that carries the FVG source (target, else stop); they stay in every total and are not computable for the four gap features.

**Gap role: 680 target / 598 stop / 0 unidentified. Gap at the signal bar: 543 open / 735 filled.** A filled gap was unfilled when the replay's level map was built (up to 4 bars earlier) and is no longer returned by the finder at the signal bar. The live scan builds its level map fresh at every scan, so it would not have labelled those plans FVG.

Medians over the identified population: replay quality 56, ATR14/close 0.03723.

## Feature coverage

| Feature | Computable | Not computable | Share | Status |
|---|---|---|---|---|
| Gap age <= 20 bars | 1278 | 0 | 100.0% | tested |
| Gap height >= 0.5 ATR14 | 1278 | 0 | 100.0% | tested |
| Displacement candle (v128 definition, k = 1.5) | 1278 | 0 | 100.0% | tested |
| Stop distance >= 1.0 ATR14 | 1278 | 0 | 100.0% | tested |
| Replay quality score >= median | 1278 | 0 | 100.0% | tested |
| Trend-aligned (SMA200) | 1269 | 9 | 99.3% | tested |
| ATR14 / close <= median | 1278 | 0 | 100.0% | tested |
| Earnings distance > 5 sessions | 1241 | 37 | 97.1% | tested |
| Gap open at the signal bar | 1278 | 0 | 100.0% | tested |

## Whole population

| Geometry | N | Win rate | ExpR |
|---|---|---|---|
| live | 1278 | 29.9% | -0.100R |
| g125 | 1278 | 37.3% | -0.120R |
| g100 | 1278 | 39.5% | -0.140R |

## Candidate table

The rule, per (feature, geometry) pair, on the favourable side: N >= 150, win rate >= 50%, ExpR > 0, at least +0.10R above the unfavourable side, and ExpR > 0 in 3 of the 4 years. A feature computable for under 80% of the population is not tested.

| Feature (favourable side) | Geometry | N fav | WR fav | ExpR fav | N unfav | WR unfav | ExpR unfav | Years > 0 | Not computable | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| Gap age <= 20 bars | live | 812 | 29.1% | -0.099R | 466 | 31.4% | -0.101R | 1/4 | 0 (0.0%) | win rate < 50%; expectancy <= 0; under +0.10R above the unfavourable side; positive in fewer than 3 of 4 years |
| Gap age <= 20 bars | g125 | 812 | 34.8% | -0.143R | 466 | 41.6% | -0.080R | 1/4 | 0 (0.0%) | win rate < 50%; expectancy <= 0; under +0.10R above the unfavourable side; positive in fewer than 3 of 4 years |
| Gap age <= 20 bars | g100 | 812 | 37.2% | -0.153R | 466 | 43.3% | -0.117R | 1/4 | 0 (0.0%) | win rate < 50%; expectancy <= 0; under +0.10R above the unfavourable side; positive in fewer than 3 of 4 years |
| Gap height >= 0.5 ATR14 | live | 456 | 32.1% | -0.035R | 822 | 28.8% | -0.136R | 2/4 | 0 (0.0%) | win rate < 50%; expectancy <= 0; positive in fewer than 3 of 4 years |
| Gap height >= 0.5 ATR14 | g125 | 456 | 42.1% | -0.043R | 822 | 34.6% | -0.163R | 2/4 | 0 (0.0%) | win rate < 50%; expectancy <= 0; positive in fewer than 3 of 4 years |
| Gap height >= 0.5 ATR14 | g100 | 456 | 43.5% | -0.072R | 822 | 37.3% | -0.178R | 1/4 | 0 (0.0%) | win rate < 50%; expectancy <= 0; positive in fewer than 3 of 4 years |
| Displacement candle (v128 definition, k = 1.5) | live | 63 | 17.5% | -0.412R | 1215 | 30.6% | -0.084R | 0/4 | 0 (0.0%) | N < 150; win rate < 50%; expectancy <= 0; under +0.10R above the unfavourable side; positive in fewer than 3 of 4 years |
| Displacement candle (v128 definition, k = 1.5) | g125 | 63 | 26.3% | -0.281R | 1215 | 37.9% | -0.112R | 0/4 | 0 (0.0%) | N < 150; win rate < 50%; expectancy <= 0; under +0.10R above the unfavourable side; positive in fewer than 3 of 4 years |
| Displacement candle (v128 definition, k = 1.5) | g100 | 63 | 28.8% | -0.301R | 1215 | 40.1% | -0.132R | 0/4 | 0 (0.0%) | N < 150; win rate < 50%; expectancy <= 0; under +0.10R above the unfavourable side; positive in fewer than 3 of 4 years |
| Stop distance >= 1.0 ATR14 | live | 77 | 16.7% | -0.351R | 1201 | 30.6% | -0.084R | 0/4 | 0 (0.0%) | N < 150; win rate < 50%; expectancy <= 0; under +0.10R above the unfavourable side; positive in fewer than 3 of 4 years |
| Stop distance >= 1.0 ATR14 | g125 | 77 | 21.8% | -0.339R | 1201 | 38.1% | -0.106R | 1/4 | 0 (0.0%) | N < 150; win rate < 50%; expectancy <= 0; under +0.10R above the unfavourable side; positive in fewer than 3 of 4 years |
| Stop distance >= 1.0 ATR14 | g100 | 77 | 25.9% | -0.302R | 1201 | 40.2% | -0.130R | 1/4 | 0 (0.0%) | N < 150; win rate < 50%; expectancy <= 0; under +0.10R above the unfavourable side; positive in fewer than 3 of 4 years |
| Replay quality score >= median | live | 667 | 30.0% | -0.097R | 611 | 29.9% | -0.103R | 1/4 | 0 (0.0%) | win rate < 50%; expectancy <= 0; under +0.10R above the unfavourable side; positive in fewer than 3 of 4 years |
| Replay quality score >= median | g125 | 667 | 38.8% | -0.093R | 611 | 35.8% | -0.151R | 1/4 | 0 (0.0%) | win rate < 50%; expectancy <= 0; under +0.10R above the unfavourable side; positive in fewer than 3 of 4 years |
| Replay quality score >= median | g100 | 667 | 40.9% | -0.120R | 611 | 38.0% | -0.162R | 1/4 | 0 (0.0%) | win rate < 50%; expectancy <= 0; under +0.10R above the unfavourable side; positive in fewer than 3 of 4 years |
| Trend-aligned (SMA200) | live | 595 | 28.0% | -0.121R | 674 | 32.0% | -0.076R | 2/4 | 9 (0.7%) | win rate < 50%; expectancy <= 0; under +0.10R above the unfavourable side; positive in fewer than 3 of 4 years |
| Trend-aligned (SMA200) | g125 | 595 | 34.7% | -0.152R | 674 | 40.0% | -0.088R | 2/4 | 9 (0.7%) | win rate < 50%; expectancy <= 0; under +0.10R above the unfavourable side; positive in fewer than 3 of 4 years |
| Trend-aligned (SMA200) | g100 | 595 | 36.1% | -0.186R | 674 | 42.8% | -0.095R | 2/4 | 9 (0.7%) | win rate < 50%; expectancy <= 0; under +0.10R above the unfavourable side; positive in fewer than 3 of 4 years |
| ATR14 / close <= median | live | 640 | 31.6% | -0.072R | 638 | 28.5% | -0.128R | 1/4 | 0 (0.0%) | win rate < 50%; expectancy <= 0; under +0.10R above the unfavourable side; positive in fewer than 3 of 4 years |
| ATR14 / close <= median | g125 | 640 | 42.3% | -0.037R | 638 | 33.2% | -0.204R | 1/4 | 0 (0.0%) | win rate < 50%; expectancy <= 0; positive in fewer than 3 of 4 years |
| ATR14 / close <= median | g100 | 640 | 46.5% | -0.040R | 638 | 33.6% | -0.240R | 1/4 | 0 (0.0%) | win rate < 50%; expectancy <= 0; positive in fewer than 3 of 4 years |
| Earnings distance > 5 sessions | live | 1106 | 28.9% | -0.127R | 135 | 40.6% | +0.092R | 1/4 | 37 (2.9%) | win rate < 50%; expectancy <= 0; under +0.10R above the unfavourable side; positive in fewer than 3 of 4 years |
| Earnings distance > 5 sessions | g125 | 1106 | 35.3% | -0.168R | 135 | 54.8% | +0.248R | 1/4 | 37 (2.9%) | win rate < 50%; expectancy <= 0; under +0.10R above the unfavourable side; positive in fewer than 3 of 4 years |
| Earnings distance > 5 sessions | g100 | 1106 | 37.6% | -0.185R | 135 | 55.5% | +0.189R | 1/4 | 37 (2.9%) | win rate < 50%; expectancy <= 0; under +0.10R above the unfavourable side; positive in fewer than 3 of 4 years |
| Gap open at the signal bar | live | 543 | 30.4% | -0.069R | 735 | 29.6% | -0.123R | 2/4 | 0 (0.0%) | win rate < 50%; expectancy <= 0; under +0.10R above the unfavourable side; positive in fewer than 3 of 4 years |
| Gap open at the signal bar | g125 | 543 | 40.1% | -0.048R | 735 | 35.5% | -0.174R | 2/4 | 0 (0.0%) | win rate < 50%; expectancy <= 0; positive in fewer than 3 of 4 years |
| Gap open at the signal bar | g100 | 543 | 43.4% | -0.051R | 735 | 37.0% | -0.206R | 2/4 | 0 (0.0%) | win rate < 50%; expectancy <= 0; positive in fewer than 3 of 4 years |

## Notes

- **Replay quality score, not the live one.** `replay_scenarios` builds plans without quality inputs, so the diagnostic scores each plan with the live scorer (`quality.score_plan`) from what is causal on the ticker's own window: higher-timeframe bias, volume ratio, ATR percentile, trigger distance and the target confluence count (strategy families within 5% of the scenario target). Market regime, relative-strength percentile and breadth are passed as None.
- **Share of gap filled: not testable on this population.** The live gap finder drops a gap as soon as any later bar overlaps it, so every plan here sits on an untouched gap and the share is 0 by construction. Dropped before the run (partner decision, 2026-10-09); it is neither tested nor closed. "Gap open at the signal bar" is its testable form on the replay, where a level map up to 4 bars old lets a filled gap keep its label.

## Reported, never gating

### By gap role

| Value | N live | WR live | ExpR live | N g125 | WR g125 | ExpR g125 | N g100 | WR g100 | ExpR g100 |
|---|---|---|---|---|---|---|---|---|---|
| stop | 598 | 30.4% | -0.076R | 598 | 39.7% | -0.064R | 598 | 41.7% | -0.097R |
| target | 680 | 29.6% | -0.121R | 680 | 35.2% | -0.170R | 680 | 37.5% | -0.177R |

### By plan direction

| Value | N live | WR live | ExpR live | N g125 | WR g125 | ExpR g125 | N g100 | WR g100 | ExpR g100 |
|---|---|---|---|---|---|---|---|---|---|
| bearish | 794 | 30.1% | -0.131R | 794 | 37.7% | -0.144R | 794 | 40.6% | -0.145R |
| bullish | 484 | 29.7% | -0.049R | 484 | 36.8% | -0.081R | 484 | 37.7% | -0.131R |

### By horizon

| Value | N live | WR live | ExpR live | N g125 | WR g125 | ExpR g125 | N g100 | WR g100 | ExpR g100 |
|---|---|---|---|---|---|---|---|---|---|
| 2m | 98 | 27.7% | -0.127R | 98 | 35.2% | -0.149R | 98 | 36.7% | -0.178R |
| 2w | 90 | 25.6% | -0.275R | 90 | 39.3% | -0.175R | 90 | 41.2% | -0.198R |
| 3m | 130 | 29.8% | -0.091R | 130 | 35.6% | -0.139R | 130 | 38.1% | -0.121R |
| 4m | 144 | 33.9% | -0.023R | 144 | 43.0% | -0.003R | 144 | 43.0% | -0.068R |
| 4w | 92 | 27.7% | -0.241R | 92 | 31.0% | -0.302R | 92 | 32.1% | -0.320R |
| 5m | 137 | 31.1% | -0.078R | 137 | 37.4% | -0.151R | 137 | 38.2% | -0.192R |
| 6m | 138 | 30.0% | -0.059R | 138 | 37.0% | -0.086R | 138 | 39.1% | -0.104R |
| 7m | 149 | 26.0% | -0.159R | 149 | 33.6% | -0.170R | 149 | 36.8% | -0.181R |
| 8m | 164 | 34.3% | +0.016R | 164 | 42.2% | +0.001R | 164 | 45.6% | -0.014R |
| 9m | 136 | 30.0% | -0.099R | 136 | 36.4% | -0.143R | 136 | 40.7% | -0.138R |

### By year

| Value | N live | WR live | ExpR live | N g125 | WR g125 | ExpR g125 | N g100 | WR g100 | ExpR g100 |
|---|---|---|---|---|---|---|---|---|---|
| 2020 | 355 | 29.1% | -0.107R | 355 | 36.5% | -0.130R | 355 | 39.4% | -0.148R |
| 2021 | 309 | 29.2% | -0.119R | 309 | 39.4% | -0.081R | 309 | 42.7% | -0.097R |
| 2022 | 366 | 25.4% | -0.244R | 366 | 28.9% | -0.300R | 366 | 29.6% | -0.320R |
| 2023 | 248 | 39.3% | +0.147R | 248 | 50.0% | +0.111R | 248 | 51.9% | +0.083R |

### Exit mix

- **live:** breakeven_stop 166, stop 779, tp1+runner_be 201, tp1+runner_tp2 121, tp1+runner_trail 11
- **g125:** breakeven_stop 121, stop 725, tp1+runner_be 271, tp1+runner_tp2 150, tp1+runner_trail 11
- **g100:** breakeven_stop 114, stop 704, tp1+runner_be 294, tp1+runner_timeout 1, tp1+runner_tp2 154, tp1+runner_trail 11
