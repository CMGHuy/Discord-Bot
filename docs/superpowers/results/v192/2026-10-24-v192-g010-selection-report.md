# v192 gap-reclaim report

Arms: `E:\Documents\Private\Projects\Discord-Bot\.claude\worktrees\2026-10-24-v192-gap-toward-stop-reclaim\docs\superpowers\results\v192\2026-10-24-v192-g010-selection.json`

- N: baseline 7100, component 6219
- dWR (pp, standardised): +3.49 [+2.50, +4.50] (week-cluster bootstrap)
- dExpR (R): -0.1290 [-0.1979, -0.0644] (week-cluster bootstrap)
- outcome flips: 67

## Strata

| Stratum | N | Decided | WR | ExpR | Baseline WR | Baseline ExpR |
|---|---|---|---|---|---|---|
| removed | 889 | 852 | 5.75 | -0.6675 | n/a | n/a |
| repriced | 1695 | 1504 | 26.99 | -0.0734 | 28.39 | +0.8223 |
| added | 8 | 7 | 14.29 | -0.5068 | n/a | n/a |
| unchanged | 4516 | 3863 | 36.06 | +0.0481 | 36.06 | +0.0481 |

## Re-priced trades in dollars

- n 1695, risk $1000 per trade: baseline $694449.35, component $-132639.15, delta $-827088.49

## Ambiguous-bar sensitivity

- ambiguous fills: 754; dWR as fills +3.49pp, as cancels +9.13pp

## Census

| Horizon | Direction | Market plans | Armed | Reclaimed | Ambiguous | Open through stop | Risk cap |
|---|---|---|---|---|---|---|---|
| 2m | bearish | 319 | 88 | 60 | 26 | 57 | 117 |
| 2m | bullish | 842 | 194 | 125 | 54 | 80 | 446 |
| 2w | bearish | 204 | 40 | 29 | 15 | 38 | 90 |
| 2w | bullish | 583 | 122 | 80 | 25 | 44 | 337 |
| 3m | bearish | 356 | 97 | 66 | 29 | 47 | 146 |
| 3m | bullish | 878 | 201 | 132 | 56 | 79 | 466 |
| 4m | bearish | 380 | 98 | 61 | 32 | 51 | 154 |
| 4m | bullish | 764 | 177 | 113 | 47 | 71 | 402 |
| 4w | bearish | 326 | 83 | 59 | 33 | 46 | 138 |
| 4w | bullish | 888 | 220 | 139 | 40 | 72 | 476 |
| 5m | bearish | 409 | 109 | 70 | 34 | 61 | 173 |
| 5m | bullish | 660 | 131 | 88 | 46 | 80 | 335 |
| 6m | bearish | 418 | 104 | 66 | 35 | 62 | 182 |
| 6m | bullish | 683 | 138 | 95 | 47 | 87 | 348 |
| 7m | bearish | 438 | 104 | 69 | 40 | 63 | 192 |
| 7m | bullish | 861 | 185 | 112 | 45 | 90 | 455 |
| 8m | bearish | 426 | 106 | 71 | 33 | 56 | 185 |
| 8m | bullish | 689 | 152 | 102 | 44 | 92 | 344 |
| 9m | bearish | 408 | 102 | 72 | 36 | 55 | 174 |
| 9m | bullish | 674 | 141 | 92 | 37 | 87 | 334 |

## Splits (descriptive)

### source

| Value | Base N | Comp N | dWR pp | dExpR |
|---|---|---|---|---|
| confluence | 5372 | 4926 | +2.52 | -0.1201 |
| strategy | 1728 | 1293 | +6.64 | -0.1290 |

### direction

| Value | Base N | Comp N | dWR pp | dExpR |
|---|---|---|---|---|
| bearish | 2885 | 2577 | +3.18 | -0.1628 |
| bullish | 4215 | 3642 | +3.59 | -0.1061 |

### horizon_key

| Value | Base N | Comp N | dWR pp | dExpR |
|---|---|---|---|---|
| 2m | 673 | 577 | +4.17 | -0.1506 |
| 2w | 536 | 483 | +2.32 | -0.0834 |
| 3m | 748 | 648 | +3.29 | -0.1209 |
| 4m | 716 | 617 | +4.23 | -0.1094 |
| 4w | 702 | 598 | +3.87 | -0.1855 |
| 5m | 705 | 623 | +3.33 | -0.1222 |
| 6m | 714 | 633 | +3.05 | -0.0920 |
| 7m | 782 | 678 | +3.75 | -0.1306 |
| 8m | 746 | 662 | +3.64 | -0.1781 |
| 9m | 778 | 700 | +2.99 | -0.1085 |

## Regime (descriptive)

```
{
 "bear_quiet": {
  "n_baseline": 355,
  "n_component": 320,
  "baseline_win_rate": 41.23711340206186,
  "component_win_rate": 45.703125,
  "delta_win_rate_pp": 5.295733313266602,
  "delta_expectancy_r": 0.05009141725352112
 },
 "bear_volatile": {
  "n_baseline": 1926,
  "n_component": 1758,
  "baseline_win_rate": 26.71156004489338,
  "component_win_rate": 29.6,
  "delta_win_rate_pp": 2.685755789906505,
  "delta_expectancy_r": -0.07704179203924028
 },
 "bull_quiet": {
  "n_baseline": 3042,
  "n_component": 2580,
  "baseline_win_rate": 30.44982698961938,
  "component_win_rate": 34.181313598519885,
  "delta_win_rate_pp": 3.6000962508324577,
  "delta_expectancy_r": -0.17730184548109415
 },
 "bull_volatile": {
  "n_baseline": 1777,
  "n_component": 1561,
  "baseline_win_rate": 31.167979002624673,
  "component_win_rate": 34.78587528174305,
  "delta_win_rate_pp": 4.368941404064653,
  "delta_expectancy_r": -0.13125357394308437
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

