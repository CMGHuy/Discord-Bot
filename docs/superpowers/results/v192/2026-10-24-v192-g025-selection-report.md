# v192 gap-reclaim report

Arms: `E:\Documents\Private\Projects\Discord-Bot\.claude\worktrees\2026-10-24-v192-gap-toward-stop-reclaim\docs\superpowers\results\v192\2026-10-24-v192-g025-selection.json`

- N: baseline 7100, component 6592
- dWR (pp, standardised): +1.85 [+1.05, +2.68] (week-cluster bootstrap)
- dExpR (R): -0.0778 [-0.1398, -0.0229] (week-cluster bootstrap)
- outcome flips: 48

## Strata

| Stratum | N | Decided | WR | ExpR | Baseline WR | Baseline ExpR |
|---|---|---|---|---|---|---|
| removed | 514 | 494 | 6.48 | -0.5973 | n/a | n/a |
| repriced | 625 | 540 | 27.78 | +0.0192 | 30.46 | +1.4439 |
| added | 6 | 5 | 20.00 | -0.3423 | n/a | n/a |
| unchanged | 5961 | 5182 | 32.27 | +0.0708 | 32.27 | +0.0708 |

## Re-priced trades in dollars

- n 625, risk $1000 per trade: baseline $384439.53, component $10423.27, delta $-374016.26

## Ambiguous-bar sensitivity

- ambiguous fills: 253; dWR as fills +1.85pp, as cancels +3.47pp

## Census

| Horizon | Direction | Market plans | Armed | Reclaimed | Ambiguous | Open through stop | Risk cap |
|---|---|---|---|---|---|---|---|
| 2m | bearish | 319 | 32 | 19 | 9 | 57 | 117 |
| 2m | bullish | 841 | 86 | 42 | 17 | 80 | 446 |
| 2w | bearish | 204 | 15 | 10 | 7 | 38 | 90 |
| 2w | bullish | 583 | 65 | 37 | 10 | 44 | 337 |
| 3m | bearish | 356 | 43 | 25 | 10 | 47 | 146 |
| 3m | bullish | 878 | 95 | 47 | 18 | 79 | 466 |
| 4m | bearish | 380 | 47 | 28 | 13 | 51 | 154 |
| 4m | bullish | 764 | 82 | 39 | 14 | 71 | 402 |
| 4w | bearish | 326 | 25 | 17 | 11 | 46 | 138 |
| 4w | bullish | 887 | 108 | 56 | 14 | 72 | 476 |
| 5m | bearish | 409 | 46 | 29 | 13 | 61 | 173 |
| 5m | bullish | 660 | 62 | 35 | 15 | 80 | 335 |
| 6m | bearish | 418 | 43 | 26 | 11 | 62 | 182 |
| 6m | bullish | 683 | 57 | 28 | 12 | 87 | 348 |
| 7m | bearish | 438 | 39 | 28 | 15 | 63 | 192 |
| 7m | bullish | 860 | 86 | 40 | 14 | 90 | 454 |
| 8m | bearish | 426 | 39 | 26 | 10 | 56 | 185 |
| 8m | bullish | 689 | 67 | 34 | 14 | 92 | 344 |
| 9m | bearish | 408 | 42 | 29 | 13 | 55 | 174 |
| 9m | bullish | 674 | 65 | 33 | 13 | 87 | 334 |

## Splits (descriptive)

### source

| Value | Base N | Comp N | dWR pp | dExpR |
|---|---|---|---|---|
| confluence | 5372 | 5179 | +1.19 | -0.0716 |
| strategy | 1728 | 1413 | +3.99 | -0.0735 |

### direction

| Value | Base N | Comp N | dWR pp | dExpR |
|---|---|---|---|---|
| bearish | 2885 | 2751 | +1.33 | -0.1138 |
| bullish | 4215 | 3841 | +2.08 | -0.0532 |

### horizon_key

| Value | Base N | Comp N | dWR pp | dExpR |
|---|---|---|---|---|
| 2m | 673 | 616 | +2.26 | -0.0990 |
| 2w | 536 | 503 | +1.41 | -0.0301 |
| 3m | 748 | 682 | +1.98 | -0.0767 |
| 4m | 716 | 656 | +2.17 | -0.0532 |
| 4w | 702 | 642 | +1.64 | -0.1384 |
| 5m | 705 | 661 | +1.66 | -0.0955 |
| 6m | 714 | 668 | +1.67 | -0.0433 |
| 7m | 782 | 729 | +1.85 | -0.0776 |
| 8m | 746 | 701 | +1.98 | -0.0949 |
| 9m | 778 | 734 | +1.78 | -0.0614 |

## Regime (descriptive)

```
{
 "bear_quiet": {
  "n_baseline": 355,
  "n_component": 342,
  "baseline_win_rate": 41.23711340206186,
  "component_win_rate": 42.805755395683455,
  "delta_win_rate_pp": 2.16566437571592,
  "delta_expectancy_r": 0.03653920599621119
 },
 "bear_volatile": {
  "n_baseline": 1926,
  "n_component": 1848,
  "baseline_win_rate": 26.71156004489338,
  "component_win_rate": 28.0466472303207,
  "delta_win_rate_pp": 1.1293333571433308,
  "delta_expectancy_r": 0.008299336826205983
 },
 "bull_quiet": {
  "n_baseline": 3042,
  "n_component": 2754,
  "baseline_win_rate": 30.44982698961938,
  "component_win_rate": 32.23175965665236,
  "delta_win_rate_pp": 1.8000315262086417,
  "delta_expectancy_r": -0.1475410290787365
 },
 "bull_volatile": {
  "n_baseline": 1777,
  "n_component": 1648,
  "baseline_win_rate": 31.167979002624673,
  "component_win_rate": 33.61823361823362,
  "delta_win_rate_pp": 2.8738227574494353,
  "delta_expectancy_r": -0.07131783174708109
 }
}
```

Earnings proximity: unavailable: the v1 replay row (ArmTrade) carries no earnings date and no as-of earnings archive exists (compression_research.py:7-13); the earnings CSVs hold final report dates, so a cut on them would be lookahead

## Next-open basis (fold-train, disclosure)

```
{
 "stage": "selection",
 "close_fill": {
  "n": 13627,
  "win_rate": 36.580882352941174,
  "expectancy_r": 0.13923849710134295
 },
 "next_open": {
  "n": 7100,
  "win_rate": 30.05808325266215,
  "expectancy_r": 0.14332239436619715
 },
 "delta_win_rate_pp": -6.896325333084743,
 "delta_expectancy_r": 0.004083897264854197,
 "note": "disclosure only; decides nothing (spec \u00a7 Replay basis)"
}
```

