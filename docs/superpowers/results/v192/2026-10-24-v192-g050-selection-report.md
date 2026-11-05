# v192 gap-reclaim report

Arms: `E:\Documents\Private\Projects\Discord-Bot\.claude\worktrees\2026-10-24-v192-gap-toward-stop-reclaim\docs\superpowers\results\v192\2026-10-24-v192-g050-selection.json`

- N: baseline 7100, component 6976
- dWR (pp, standardised): +0.44 [+0.20, +0.72] (week-cluster bootstrap)
- dExpR (R): +0.0011 [-0.0167, +0.0161] (week-cluster bootstrap)
- outcome flips: 13

## Strata

| Stratum | N | Decided | WR | ExpR | Baseline WR | Baseline ExpR |
|---|---|---|---|---|---|---|
| removed | 127 | 124 | 4.03 | -0.6377 | n/a | n/a |
| repriced | 95 | 87 | 11.49 | -0.4659 | 13.16 | +0.5036 |
| added | 3 | 2 | 50.00 | +0.3950 | n/a | n/a |
| unchanged | 6878 | 5998 | 30.81 | +0.1528 | 30.81 | +0.1528 |

## Re-priced trades in dollars

- n 95, risk $1000 per trade: baseline $17535.04, component $-44889.60, delta $-62424.63

## Ambiguous-bar sensitivity

- ambiguous fills: 44; dWR as fills +0.44pp, as cancels +0.66pp

## Census

| Horizon | Direction | Market plans | Armed | Reclaimed | Ambiguous | Open through stop | Risk cap |
|---|---|---|---|---|---|---|---|
| 2m | bearish | 319 | 1 | 1 | 1 | 57 | 117 |
| 2m | bullish | 841 | 23 | 9 | 4 | 80 | 446 |
| 2w | bearish | 204 | 1 | 1 | 1 | 38 | 90 |
| 2w | bullish | 583 | 14 | 7 | 3 | 44 | 337 |
| 3m | bearish | 356 | 5 | 2 | 1 | 47 | 146 |
| 3m | bullish | 878 | 29 | 10 | 6 | 79 | 466 |
| 4m | bearish | 380 | 4 | 2 | 1 | 51 | 154 |
| 4m | bullish | 762 | 24 | 9 | 5 | 71 | 401 |
| 4w | bearish | 326 | 1 | 1 | 1 | 46 | 138 |
| 4w | bullish | 886 | 30 | 11 | 3 | 72 | 475 |
| 5m | bearish | 409 | 2 | 2 | 1 | 61 | 173 |
| 5m | bullish | 660 | 12 | 7 | 2 | 80 | 335 |
| 6m | bearish | 418 | 3 | 2 | 1 | 62 | 182 |
| 6m | bullish | 683 | 14 | 6 | 3 | 87 | 348 |
| 7m | bearish | 438 | 5 | 4 | 2 | 63 | 192 |
| 7m | bullish | 858 | 18 | 6 | 2 | 90 | 454 |
| 8m | bearish | 426 | 3 | 2 | 1 | 56 | 185 |
| 8m | bullish | 688 | 13 | 4 | 2 | 92 | 344 |
| 9m | bearish | 408 | 4 | 2 | 1 | 55 | 174 |
| 9m | bullish | 673 | 16 | 7 | 3 | 87 | 334 |

## Splits (descriptive)

### source

| Value | Base N | Comp N | dWR pp | dExpR |
|---|---|---|---|---|
| confluence | 5372 | 5346 | +0.11 | +0.0004 |
| strategy | 1728 | 1630 | +1.52 | +0.0118 |

### direction

| Value | Base N | Comp N | dWR pp | dExpR |
|---|---|---|---|---|
| bearish | 2885 | 2875 | +0.01 | -0.0027 |
| bullish | 4215 | 4101 | +0.72 | +0.0032 |

### horizon_key

| Value | Base N | Comp N | dWR pp | dExpR |
|---|---|---|---|---|
| 2m | 673 | 659 | +0.48 | -0.0035 |
| 2w | 536 | 529 | +0.35 | +0.0105 |
| 3m | 748 | 726 | +0.64 | +0.0104 |
| 4m | 716 | 700 | +0.36 | -0.0083 |
| 4w | 702 | 683 | +0.63 | -0.0412 |
| 5m | 705 | 700 | +0.19 | +0.0064 |
| 6m | 714 | 705 | +0.33 | +0.0122 |
| 7m | 782 | 771 | +0.49 | -0.0011 |
| 8m | 746 | 736 | +0.51 | +0.0159 |
| 9m | 778 | 767 | +0.43 | +0.0100 |

## Regime (descriptive)

```
{
 "bear_quiet": {
  "n_baseline": 355,
  "n_component": 355,
  "baseline_win_rate": 41.23711340206186,
  "component_win_rate": 41.23711340206186,
  "delta_win_rate_pp": 0.0,
  "delta_expectancy_r": 0.0
 },
 "bear_volatile": {
  "n_baseline": 1926,
  "n_component": 1920,
  "baseline_win_rate": 26.71156004489338,
  "component_win_rate": 26.8018018018018,
  "delta_win_rate_pp": 0.052715709281365264,
  "delta_expectancy_r": 0.0029917137201453878
 },
 "bull_quiet": {
  "n_baseline": 3042,
  "n_component": 2955,
  "baseline_win_rate": 30.44982698961938,
  "component_win_rate": 31.235154394299286,
  "delta_win_rate_pp": 0.6962581053789343,
  "delta_expectancy_r": 0.005723897249004628
 },
 "bull_volatile": {
  "n_baseline": 1777,
  "n_component": 1746,
  "baseline_win_rate": 31.167979002624673,
  "component_win_rate": 31.72690763052209,
  "delta_win_rate_pp": 0.6662377430093969,
  "delta_expectancy_r": -0.004030383460289638
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

