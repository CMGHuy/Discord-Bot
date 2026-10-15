# v146 Expectancy attribution: result

**Run:** 2026-10-15, live book (closed production trades, both ledgers, read from a local copy) and TRAIN confluence replay 2020-01-06..2023-12-29 (signal date), side by side and never pooled. Read-only; VALIDATION never read.
**Spec:** `docs/superpowers/specs/2026-10-09-v146-expectancy-attribution-design.md`

**Verdict: NOT PREDICTIVE.** Closes "raise the confidence floor" as a measured no; any bucket candidate stands on its own and needs its own Stage -2 screen.

Verdict of record: `{"date": "2026-10-15", "n": 6449, "verdict": "NOT PREDICTIVE"}` (`n` is the live monotonicity n plus the TRAIN monotonicity n). 113 looks in the BH family; bootstrap seed 42. The verdict was pre-registered in the spec and computed once, in this run. Later runs are descriptive and never revise it; a new verdict needs a new spec.

Rule, on the top-minus-bottom tercile ExpR and its 95% week-clustered bootstrap CI: PREDICTIVE needs a lower bound above 0 and a point estimate of at least +0.10R in both populations; WEAK is that in exactly one; NOT PREDICTIVE otherwise. A tercile with N < 30 fails its population's clause. A CI wholly below zero is reported as inverted inside NOT PREDICTIVE, not as a fourth verdict.

All figures are as stored in `data/reports/expectancy-attribution.json` (floats to four decimals, the file's own key names and units). R is net of frictions; `exp_r_gross` is the gross figure beside it.

## The verdict table: confidence score against R

| population | n | spearman_rho | tercile_spread | ci_low | ci_high | p | inverted | tercile_n | rr_by_tercile | clause passes |
|---|---|---|---|---|---|---|---|---|---|---|
| Live | 891 | -0.0297 | -0.0146 | -0.1526 | 0.0814 | 0.6815 | no | [327, 275, 289] | [{"median": 1.82, "p25": 1.6, "p75": 2.14}, {"median": 1.92, "p25": 1.65, "p75": 2.295}, {"median": 1.9549669991222673, "p25": 1.65, "p75": 2.42}] | no |
| TRAIN | 5558 | 0.0515 | 0.0768 | -0.1071 | 0.2634 | 0.4290 | no | [1814, 1782, 1962] | [{"median": 2.5, "p25": 2.5, "p75": 2.5}, {"median": 2.5, "p25": 2.33, "p75": 2.5}, {"median": 2.5, "p25": 2.22, "p75": 2.5}] | no |

## Verdict table split by direction and horizon

### By direction

| population | direction | n | spearman_rho | tercile_spread | ci_low | ci_high | p | inverted | tercile_n | rr_by_tercile |
|---|---|---|---|---|---|---|---|---|---|---|
| Live | bearish | 312 | -0.0051 | 0.0403 | -0.4595 | 0.5267 | 0.8807 | no | [98, 114, 100] | [{"median": 1.7650000000000001, "p25": 1.6, "p75": 2.11}, {"median": 2.02, "p25": 1.72, "p75": 2.34}, {"median": 2.0, "p25": 1.71, "p75": 2.5}] |
| Live | bullish | 579 | -0.0440 | 0.0264 | -0.3099 | 0.2955 | 0.8751 | no | [174, 221, 184] | [{"median": 1.792858859727875, "p25": 1.59, "p75": 2.105}, {"median": 1.89, "p25": 1.64, "p75": 2.19}, {"median": 1.9393772097258082, "p25": 1.6194339881504918, "p75": 2.46}] |
| TRAIN | bearish | 2644 | 0.0243 | -0.0018 | -0.2612 | 0.2464 | 0.9987 | no | [884, 833, 927] | [{"median": 2.5, "p25": 2.5, "p75": 2.5}, {"median": 2.5, "p25": 2.32, "p75": 2.5}, {"median": 2.5, "p25": 2.215, "p75": 2.5}] |
| TRAIN | bullish | 2914 | 0.0720 | 0.0902 | -0.2237 | 0.4054 | 0.5805 | no | [990, 1007, 917] | [{"median": 2.5, "p25": 2.5, "p75": 2.5}, {"median": 2.5, "p25": 2.32, "p75": 2.5}, {"median": 2.5, "p25": 2.23, "p75": 2.5}] |

### By horizon

| population | horizon | n | spearman_rho | tercile_spread | ci_low | ci_high | p | inverted | tercile_n | rr_by_tercile |
|---|---|---|---|---|---|---|---|---|---|---|
| Live | 2m | 126 | 0.0937 | 0.2870 | -0.1190 | 0.6191 | 0.1418 | no | [47, 36, 43] | [{"median": 1.83, "p25": 1.590253425198272, "p75": 2.3049999999999997}, {"median": 1.87, "p25": 1.5875000000000001, "p75": 2.2275}, {"median": 2.1586885822087245, "p25": 1.797115083669858, "p75": 2.3930429289284136}] |
| Live | 2w | 89 | -0.0892 | 0.1642 | n/a | n/a | n/a | no | [30, 30, 29] | [{"median": 1.6949999999999998, "p25": 1.6025, "p75": 1.9124999999999999}, {"median": 1.92, "p25": 1.665, "p75": 2.3725}, {"median": 1.9183189880657059, "p25": 1.72, "p75": 2.23}] |
| Live | 3m | 129 | -0.0356 | -0.1067 | -0.4191 | 0.2735 | 0.4780 | no | [42, 42, 45] | [{"median": 1.6749999999999998, "p25": 1.5525, "p75": 2.01}, {"median": 1.880430492437513, "p25": 1.6549999999999998, "p75": 2.2175000000000002}, {"median": 1.75, "p25": 1.58, "p75": 2.499999999999993}] |
| Live | 4m | 108 | -0.0001 | 0.2202 | -0.3021 | 1.1233 | 0.4940 | no | [37, 36, 35] | [{"median": 1.82, "p25": 1.63, "p75": 2.11}, {"median": 1.8289389236729279, "p25": 1.6375, "p75": 2.0999999999999996}, {"median": 1.89, "p25": 1.65, "p75": 2.3288065541902903}] |
| Live | 4w | 142 | 0.0309 | 0.0849 | -0.3170 | 0.3173 | 0.6213 | no | [51, 36, 55] | [{"median": 1.8, "p25": 1.5950000000000002, "p75": 2.105}, {"median": 1.9940685557490543, "p25": 1.6275, "p75": 2.5}, {"median": 1.96, "p25": 1.5989023848705877, "p75": 2.415}] |
| Live | 5m | 80 | -0.1599 | -0.0587 | n/a | n/a | n/a | no | [25, 29, 26] | [{"median": 1.84, "p25": 1.63, "p75": 2.14}, {"median": 1.99, "p25": 1.62, "p75": 2.11}, {"median": 1.9692255677281099, "p25": 1.6999855854514774, "p75": 2.37}] |
| Live | 6m | 59 | -0.0144 | -0.0179 | n/a | n/a | n/a | no | [18, 20, 21] | [{"median": 2.035, "p25": 1.5725, "p75": 2.2150000000000003}, {"median": 2.0675400744638237, "p25": 1.8564294298639374, "p75": 2.3225}, {"median": 2.01, "p25": 1.74, "p75": 2.63}] |
| Live | 7m | 56 | -0.2626 | -0.6106 | n/a | n/a | n/a | no | [21, 17, 18] | [{"median": 1.87, "p25": 1.6, "p75": 2.17}, {"median": 1.9, "p25": 1.59, "p75": 2.12}, {"median": 1.9833048010645178, "p25": 1.6636036159166747, "p75": 2.235}] |
| Live | 8m | 62 | -0.1622 | -0.6392 | n/a | n/a | n/a | no | [19, 24, 19] | [{"median": 1.92, "p25": 1.6373598434056502, "p75": 2.3242464084294436}, {"median": 2.075, "p25": 1.76, "p75": 2.425}, {"median": 1.9, "p25": 1.67, "p75": 2.385}] |
| Live | 9m | 40 | 0.0210 | -0.0660 | n/a | n/a | n/a | no | [14, 12, 14] | [{"median": 1.79, "p25": 1.6524999999999999, "p75": 2.109837885912821}, {"median": 1.875, "p25": 1.64, "p75": 1.9449999999999998}, {"median": 2.4999999999999982, "p25": 2.117726901806142, "p75": 2.8175}] |
| TRAIN | 2m | 481 | 0.0243 | -0.0883 | -0.4061 | 0.2480 | 0.6015 | no | [164, 144, 173] | [{"median": 2.5, "p25": 2.435, "p75": 2.5}, {"median": 2.5, "p25": 2.3075, "p75": 2.5}, {"median": 2.5, "p25": 2.26, "p75": 2.5}] |
| TRAIN | 2w | 389 | -0.0155 | 0.1177 | -0.2525 | 0.4873 | 0.5383 | no | [129, 147, 113] | [{"median": 2.5, "p25": 2.5, "p75": 2.5}, {"median": 2.5, "p25": 2.2649999999999997, "p75": 2.5}, {"median": 2.5, "p25": 2.15, "p75": 2.5}] |
| TRAIN | 3m | 560 | 0.0453 | 0.0532 | -0.2493 | 0.3653 | 0.7315 | no | [194, 195, 171] | [{"median": 2.5, "p25": 2.425, "p75": 2.5}, {"median": 2.5, "p25": 2.255, "p75": 2.5}, {"median": 2.5, "p25": 2.215, "p75": 2.5}] |
| TRAIN | 4m | 572 | 0.0360 | 0.0014 | -0.2582 | 0.2574 | 0.9905 | no | [192, 180, 200] | [{"median": 2.5, "p25": 2.5, "p75": 2.5}, {"median": 2.5, "p25": 2.3075, "p75": 2.5}, {"median": 2.5, "p25": 2.2075, "p75": 2.5}] |
| TRAIN | 4w | 437 | 0.0123 | 0.0246 | -0.3072 | 0.3447 | 0.8837 | no | [143, 167, 127] | [{"median": 2.5, "p25": 2.465, "p75": 2.5}, {"median": 2.5, "p25": 2.1950000000000003, "p75": 2.5}, {"median": 2.5, "p25": 2.29, "p75": 2.5}] |
| TRAIN | 5m | 596 | 0.0792 | 0.1167 | -0.1256 | 0.3574 | 0.3464 | no | [202, 203, 191] | [{"median": 2.5, "p25": 2.5, "p75": 2.5}, {"median": 2.5, "p25": 2.2350000000000003, "p75": 2.5}, {"median": 2.5, "p25": 2.26, "p75": 2.5}] |
| TRAIN | 6m | 593 | 0.0856 | 0.1668 | -0.0874 | 0.4254 | 0.1960 | no | [203, 186, 204] | [{"median": 2.5, "p25": 2.5, "p75": 2.5}, {"median": 2.5, "p25": 2.3225, "p75": 2.5}, {"median": 2.5, "p25": 2.2575, "p75": 2.5}] |
| TRAIN | 7m | 659 | 0.0883 | 0.1511 | -0.1058 | 0.4120 | 0.2412 | no | [220, 214, 225] | [{"median": 2.5, "p25": 2.5, "p75": 2.5}, {"median": 2.5, "p25": 2.415, "p75": 2.5}, {"median": 2.5, "p25": 2.22, "p75": 2.5}] |
| TRAIN | 8m | 633 | 0.0955 | 0.1014 | -0.1666 | 0.3662 | 0.4660 | no | [210, 219, 204] | [{"median": 2.5, "p25": 2.5, "p75": 2.5}, {"median": 2.5, "p25": 2.5, "p75": 2.5}, {"median": 2.5, "p25": 2.23, "p75": 2.5}] |
| TRAIN | 9m | 638 | 0.0258 | -0.0510 | -0.3151 | 0.2051 | 0.6961 | no | [214, 220, 204] | [{"median": 2.5, "p25": 2.5, "p75": 2.5}, {"median": 2.5, "p25": 2.4400000000000004, "p75": 2.5}, {"median": 2.5, "p25": 2.3075, "p75": 2.5}] |

## Buckets

One row per bucket and population. `thin` buckets (N < 30) are shown and enter no verdict and no look.

### confidence_decile

| population | label | n | win_rate | exp_r | exp_r_gross | ci_low | ci_high | p | q | thin | unevaluated_n | rr |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Live | D1 (49-67) | 80 | 55.0000 | -0.0332 | 0.0269 | -0.1746 | 0.4776 | 0.3756 | 0.9987 | no | 1 | {"median": 1.68, "p25": 1.5775000000000001, "p75": 1.9561396297507279} |
| Live | D2 (68-69) | 109 | 41.2844 | -0.3627 | -0.3054 | -0.5075 | -0.0824 | 0.0018 | 0.2034 | no | 1 | {"median": 1.84, "p25": 1.5947196868113007, "p75": 2.2} |
| Live | D3 (70-70) | 64 | 64.0625 | 0.1195 | 0.1869 | -0.0441 | 0.7560 | 0.0846 | 0.8011 | no | 0 | {"median": 1.8250000000000002, "p25": 1.6075000000000002, "p75": 2.1900000000000004} |
| Live | D4 (71-72) | 130 | 47.6923 | -0.2089 | -0.1480 | -0.2473 | 0.1952 | 0.5801 | 0.9987 | no | 0 | {"median": 1.815, "p25": 1.6122967445460377, "p75": 2.1389925723041925} |
| Live | D5 (73-73) | 51 | 54.9020 | -0.1705 | -0.1124 | -0.5090 | 0.3524 | 0.9727 | 0.9987 | no | 0 | {"median": 1.84, "p25": 1.61, "p75": 2.21} |
| Live | D6 (74-76) | 105 | 47.6190 | -0.1898 | -0.1302 | -0.2427 | 0.2277 | 0.7439 | 0.9987 | no | 0 | {"median": 1.98, "p25": 1.75, "p75": 2.38} |
| Live | D7 (77-88) | 97 | 46.3918 | -0.1255 | -0.0611 | -0.1763 | 0.2439 | 0.6705 | 0.9987 | no | 0 | {"median": 1.93, "p25": 1.67, "p75": 2.499999999999996} |
| Live | D8 (89-90) | 98 | 43.8776 | -0.1802 | -0.1157 | -0.2977 | 0.2115 | 0.8181 | 0.9987 | no | 1 | {"median": 1.8849999999999998, "p25": 1.62, "p75": 2.245653304672873} |
| Live | D9 (91-92) | 78 | 42.3077 | -0.0539 | 0.0129 | -0.1779 | 0.5043 | 0.5017 | 0.9987 | no | 0 | {"median": 1.993933938055167, "p25": 1.6549445791268163, "p75": 2.338524822994782} |
| Live | D10 (93-98) | 79 | 36.7089 | -0.2501 | -0.1903 | -0.3568 | 0.1792 | 0.4480 | 0.9987 | no | 0 | {"median": 2.16, "p25": 1.7149999999999999, "p75": 2.5} |
| TRAIN | D1 (4-33) | 571 | 29.4221 | -0.0425 | 0.0314 | -0.2551 | 0.2502 | 0.9311 | 0.9987 | no | 0 | {"median": 2.5, "p25": 2.5, "p75": 2.5} |
| TRAIN | D2 (34-51) | 587 | 30.8348 | -0.0166 | 0.0593 | -0.2015 | 0.2427 | 0.8557 | 0.9987 | no | 1 | {"median": 2.5, "p25": 2.37, "p75": 2.5} |
| TRAIN | D3 (52-55) | 466 | 21.8884 | -0.2237 | -0.1559 | -0.4714 | 0.0946 | 0.1698 | 0.8721 | no | 0 | {"median": 2.5, "p25": 2.5, "p75": 2.5} |
| TRAIN | D4 (56-67) | 566 | 27.3852 | -0.0744 | -0.0013 | -0.3083 | 0.2334 | 0.7339 | 0.9987 | no | 1 | {"median": 2.5, "p25": 2.2225, "p75": 2.5} |
| TRAIN | D5 (68-73) | 604 | 29.8013 | -0.0855 | -0.0108 | -0.2406 | 0.1291 | 0.5419 | 0.9987 | no | 0 | {"median": 2.5, "p25": 2.5, "p75": 2.5} |
| TRAIN | D6 (74-87) | 496 | 34.0726 | 0.0950 | 0.1743 | -0.1300 | 0.4115 | 0.3096 | 0.9987 | no | 0 | {"median": 2.5, "p25": 2.37, "p75": 2.5} |
| TRAIN | D7 (88-89) | 637 | 31.3972 | 0.0481 | 0.1263 | -0.1697 | 0.3582 | 0.5003 | 0.9987 | no | 1 | {"median": 2.5, "p25": 2.23, "p75": 2.5} |
| TRAIN | D8 (90-91) | 624 | 21.7949 | -0.2228 | -0.1531 | -0.3946 | -0.0239 | 0.0260 | 0.8011 | no | 1 | {"median": 2.5, "p25": 2.1575, "p75": 2.5} |
| TRAIN | D9 (92-93) | 504 | 29.5635 | 0.0697 | 0.1466 | -0.1643 | 0.4427 | 0.4644 | 0.9987 | no | 0 | {"median": 2.495, "p25": 2.16, "p75": 2.5} |
| TRAIN | D10 (94-98) | 503 | 37.7734 | 0.1262 | 0.2115 | -0.1126 | 0.4655 | 0.2302 | 0.9633 | no | 0 | {"median": 2.5, "p25": 2.38, "p75": 2.5} |

### confidence_level

| population | label | n | win_rate | exp_r | exp_r_gross | ci_low | ci_high | p | q | thin |
|---|---|---|---|---|---|---|---|---|---|---|
| Live | 3 | 2 | 50.0000 | 0.1705 | 0.2450 | n/a | n/a | n/a | n/a | yes |
| Live | 4 | 556 | 50.5396 | -0.1632 | -0.1029 | -0.1204 | 0.1009 | 0.9763 | 0.9987 | no |
| Live | 5 | 333 | 41.4414 | -0.1614 | -0.0973 | -0.1030 | 0.1190 | 0.9295 | 0.9987 | no |
| TRAIN | 1 | 46 | 19.5652 | -0.4450 | -0.3803 | -1.0187 | 0.4905 | 0.2918 | 0.9987 | no |
| TRAIN | 2 | 576 | 29.3403 | -0.0362 | 0.0376 | -0.2529 | 0.2606 | 0.9725 | 0.9987 | no |
| TRAIN | 3 | 1156 | 26.9031 | -0.1135 | -0.0422 | -0.2756 | 0.0865 | 0.3062 | 0.9987 | no |
| TRAIN | 4 | 1282 | 31.5913 | -0.0007 | 0.0763 | -0.1116 | 0.2000 | 0.5881 | 0.9987 | no |
| TRAIN | 5 | 2498 | 29.4636 | -0.0085 | 0.0685 | -0.0998 | 0.1962 | 0.5013 | 0.9987 | no |

### confluence

| population | label | n | win_rate | exp_r | exp_r_gross | ci_low | ci_high | p | q | thin |
|---|---|---|---|---|---|---|---|---|---|---|
| Live | 3 | 6 | 33.3333 | -0.1978 | -0.1188 | n/a | n/a | n/a | n/a | yes |
| Live | 4 | 19 | 21.0526 | -0.2506 | -0.1859 | n/a | n/a | n/a | n/a | yes |
| Live | 5 | 32 | 28.1250 | -0.0207 | 0.0594 | -0.4694 | 0.6964 | 0.6446 | 0.9987 | no |
| Live | 6 | 29 | 27.5862 | 0.0378 | 0.1166 | n/a | n/a | n/a | n/a | yes |
| Live | 7 | 13 | 38.4615 | 0.0983 | 0.1791 | n/a | n/a | n/a | n/a | yes |
| Live | 8 | 9 | 44.4444 | 0.5067 | 0.6021 | n/a | n/a | n/a | n/a | yes |
| Live | 9 | 2 | 50.0000 | -0.0238 | 0.0816 | n/a | n/a | n/a | n/a | yes |
| Live | 10 | 4 | 25.0000 | 0.5763 | 0.6774 | n/a | n/a | n/a | n/a | yes |
| Live | 11 | 1 | 0.0000 | -0.4743 | -0.3772 | n/a | n/a | n/a | n/a | yes |
| Live | unknown | 797 | 49.1844 | -0.1943 | -0.1357 | -0.4190 | 0.0403 | 0.0974 | 0.8011 | no |
| TRAIN | 2 | 865 | 27.3988 | -0.0853 | -0.0144 | -0.2774 | 0.1782 | 0.5961 | 0.9987 | no |
| TRAIN | 3 | 1024 | 29.7852 | -0.0516 | 0.0228 | -0.1981 | 0.1713 | 0.8277 | 0.9987 | no |
| TRAIN | 4 | 930 | 32.9032 | -0.0426 | 0.0311 | -0.1794 | 0.1596 | 0.8951 | 0.9987 | no |
| TRAIN | 5 | 829 | 25.5730 | -0.1297 | -0.0558 | -0.2706 | 0.0445 | 0.1618 | 0.8706 | no |
| TRAIN | 6 | 817 | 30.8446 | 0.0162 | 0.0958 | -0.1023 | 0.2211 | 0.4750 | 0.9987 | no |
| TRAIN | 7 | 624 | 26.4423 | -0.0097 | 0.0675 | -0.1769 | 0.2413 | 0.7897 | 0.9987 | no |
| TRAIN | 8 | 274 | 32.8467 | 0.1848 | 0.2680 | -0.0644 | 0.5480 | 0.1270 | 0.8011 | no |
| TRAIN | 9 | 105 | 34.2857 | 0.1538 | 0.2342 | -0.1790 | 0.5577 | 0.3076 | 0.9987 | no |
| TRAIN | 10 | 58 | 32.7586 | 0.1729 | 0.2545 | -0.2256 | 0.7001 | 0.3498 | 0.9987 | no |
| TRAIN | 11 | 25 | 24.0000 | -0.1560 | -0.0842 | n/a | n/a | n/a | n/a | yes |
| TRAIN | 12 | 7 | 28.5714 | -0.1198 | -0.0457 | n/a | n/a | n/a | n/a | yes |

### regime2_state

| population | label | n | win_rate | exp_r | exp_r_gross | ci_low | ci_high | p | q | thin |
|---|---|---|---|---|---|---|---|---|---|---|
| Live | bull_quiet | 111 | 29.7297 | 0.0346 | 0.1149 | -0.0868 | 0.4600 | 0.1359 | 0.8011 | no |
| Live | unknown | 801 | 49.0637 | -0.1955 | -0.1369 | -0.4600 | 0.0868 | 0.1359 | 0.8011 | no |
| TRAIN | bear_quiet | 425 | 29.8824 | -0.0339 | 0.0398 | -0.2222 | 0.2490 | 0.9789 | 0.9987 | no |
| TRAIN | bear_volatile | 1761 | 28.6769 | -0.1011 | -0.0263 | -0.2703 | 0.0721 | 0.2518 | 0.9811 | no |
| TRAIN | bull_quiet | 2438 | 29.5734 | 0.0105 | 0.0871 | -0.0830 | 0.2495 | 0.3418 | 0.9987 | no |
| TRAIN | bull_volatile | 934 | 29.6574 | -0.0296 | 0.0443 | -0.2068 | 0.2120 | 0.9743 | 0.9987 | no |

### rs_quintile

| population | label | n | win_rate | exp_r | exp_r_gross | ci_low | ci_high | p | q | thin |
|---|---|---|---|---|---|---|---|---|---|---|
| Live | Q1 | 45 | 26.6667 | -0.0380 | 0.0398 | -0.4210 | 0.4535 | 0.5782 | 0.9987 | no |
| Live | Q2 | 17 | 29.4118 | 0.2171 | 0.3013 | n/a | n/a | n/a | n/a | yes |
| Live | Q3 | 14 | 28.5714 | 0.1435 | 0.2304 | n/a | n/a | n/a | n/a | yes |
| Live | Q4 | 16 | 43.7500 | 0.1648 | 0.2538 | n/a | n/a | n/a | n/a | yes |
| Live | Q5 | 14 | 28.5714 | -0.0663 | 0.0125 | n/a | n/a | n/a | n/a | yes |
| Live | unknown | 806 | 48.8834 | -0.1966 | -0.1381 | -0.5116 | 0.0138 | 0.0599 | 0.8011 | no |
| TRAIN | Q1 | 1635 | 26.7278 | -0.1574 | -0.0851 | -0.3415 | -0.0030 | 0.0468 | 0.8011 | no |
| TRAIN | Q2 | 833 | 30.6122 | -0.0275 | 0.0467 | -0.1918 | 0.1991 | 0.9421 | 0.9987 | no |
| TRAIN | Q3 | 713 | 29.8738 | 0.0127 | 0.0892 | -0.1566 | 0.2626 | 0.6095 | 0.9987 | no |
| TRAIN | Q4 | 740 | 27.1622 | -0.1137 | -0.0423 | -0.2976 | 0.1085 | 0.3756 | 0.9987 | no |
| TRAIN | Q5 | 1626 | 32.0418 | 0.0994 | 0.1798 | -0.0138 | 0.3949 | 0.0666 | 0.8011 | no |
| TRAIN | unknown | 11 | 27.2727 | -0.0927 | -0.0202 | n/a | n/a | n/a | n/a | yes |

### direction

| population | label | n | win_rate | exp_r | exp_r_gross | ci_low | ci_high | p | q | thin |
|---|---|---|---|---|---|---|---|---|---|---|
| Live | bearish | 323 | 49.8452 | -0.1716 | -0.1112 | -0.2034 | 0.2589 | 0.9953 | 0.9987 | no |
| Live | bullish | 589 | 44.9915 | -0.1653 | -0.1035 | -0.2589 | 0.2034 | 0.9953 | 0.9987 | no |
| TRAIN | bearish | 2644 | 26.8911 | -0.1389 | -0.0663 | -0.3884 | -0.0068 | 0.0416 | 0.8011 | no |
| TRAIN | bullish | 2914 | 31.5374 | 0.0593 | 0.1372 | 0.0068 | 0.3884 | 0.0416 | 0.8011 | no |

### horizon

| population | label | n | win_rate | exp_r | exp_r_gross | ci_low | ci_high | p | q | thin |
|---|---|---|---|---|---|---|---|---|---|---|
| Live | 2m | 129 | 50.3876 | -0.0546 | 0.0132 | -0.1428 | 0.3792 | 0.3228 | 0.9987 | no |
| Live | 2w | 89 | 39.3258 | -0.3242 | -0.2612 | -0.4203 | 0.0633 | 0.1346 | 0.8011 | no |
| Live | 3m | 130 | 41.5385 | -0.2510 | -0.1918 | -0.3127 | 0.1347 | 0.3966 | 0.9987 | no |
| Live | 4m | 111 | 47.7477 | -0.1899 | -0.1322 | -0.2345 | 0.2713 | 0.7847 | 0.9987 | no |
| Live | 4w | 145 | 47.5862 | -0.0531 | 0.0145 | -0.0604 | 0.4329 | 0.2122 | 0.9222 | no |
| Live | 5m | 82 | 46.3415 | -0.3191 | -0.2613 | -0.5334 | 0.3041 | 0.4626 | 0.9987 | no |
| Live | 6m | 60 | 46.6667 | -0.0904 | -0.0285 | -0.3890 | 0.4726 | 0.7157 | 0.9987 | no |
| Live | 7m | 62 | 45.1613 | -0.2022 | -0.1532 | -0.2070 | 0.2545 | 0.7069 | 0.9987 | no |
| Live | 8m | 64 | 50.0000 | -0.2280 | -0.1733 | -0.3892 | 0.1302 | 0.5411 | 0.9987 | no |
| Live | 9m | 40 | 60.0000 | 0.0805 | 0.1470 | -0.0700 | 0.6707 | 0.1096 | 0.8011 | no |
| TRAIN | 2m | 481 | 28.6902 | -0.0544 | 0.0221 | -0.1193 | 0.0829 | 0.6875 | 0.9987 | no |
| TRAIN | 2w | 389 | 29.0488 | -0.0378 | 0.0368 | -0.1498 | 0.1520 | 0.9753 | 0.9987 | no |
| TRAIN | 3m | 560 | 30.3571 | -0.0130 | 0.0643 | -0.0531 | 0.1043 | 0.5443 | 0.9987 | no |
| TRAIN | 4m | 572 | 29.1958 | -0.0240 | 0.0552 | -0.0767 | 0.1002 | 0.7919 | 0.9987 | no |
| TRAIN | 4w | 437 | 28.3753 | -0.0911 | -0.0190 | -0.1685 | 0.0510 | 0.2790 | 0.9987 | no |
| TRAIN | 5m | 596 | 29.1946 | -0.0423 | 0.0322 | -0.0834 | 0.0638 | 0.8079 | 0.9987 | no |
| TRAIN | 6m | 593 | 29.8482 | -0.0148 | 0.0602 | -0.0465 | 0.0898 | 0.5221 | 0.9987 | no |
| TRAIN | 7m | 659 | 29.1351 | -0.0275 | 0.0476 | -0.0654 | 0.0832 | 0.8201 | 0.9987 | no |
| TRAIN | 8m | 633 | 29.3839 | -0.0240 | 0.0508 | -0.0706 | 0.0943 | 0.7803 | 0.9987 | no |
| TRAIN | 9m | 638 | 29.6238 | -0.0402 | 0.0342 | -0.0993 | 0.0876 | 0.9063 | 0.9987 | no |

### earnings

| population | label | n | win_rate | exp_r | exp_r_gross | ci_low | ci_high | p | q | thin |
|---|---|---|---|---|---|---|---|---|---|---|
| Live | unknown | 912 | 46.7105 | -0.1675 | -0.1062 | n/a | n/a | n/a | n/a | no |
| TRAIN | 0-5 | 608 | 28.7829 | -0.0345 | 0.0404 | -0.2513 | 0.2672 | 0.9925 | 0.9987 | no |
| TRAIN | 6-10 | 402 | 25.1244 | -0.1372 | -0.0652 | -0.3564 | 0.1644 | 0.3960 | 0.9987 | no |
| TRAIN | 11-20 | 857 | 30.5718 | 0.0696 | 0.1464 | -0.1420 | 0.3966 | 0.3718 | 0.9987 | no |
| TRAIN | >20 | 3691 | 29.5855 | -0.0483 | 0.0273 | -0.2316 | 0.1479 | 0.6929 | 0.9987 | no |

### earnings_in_hold

| population | label | n | win_rate | exp_r | exp_r_gross | ci_low | ci_high | p | q | thin |
|---|---|---|---|---|---|---|---|---|---|---|
| Live | unknown | 912 | 46.7105 | -0.1675 | -0.1062 | n/a | n/a | n/a | n/a | no |
| TRAIN | yes | 4932 | 29.5418 | -0.0239 | 0.0519 | -0.0261 | 0.2190 | 0.1122 | 0.8011 | no |
| TRAIN | no | 626 | 27.6358 | -0.1225 | -0.0503 | -0.2190 | 0.0261 | 0.1122 | 0.8011 | no |

## Per-factor ExpR delta

ExpR where the factor scored, minus ExpR where it scored 0; rows where the factor was unevaluated are excluded. Live history before v146 carries points from the backfill below.

| population | key | n | n_pos | n_zero | delta | ci_low | ci_high | p | q |
|---|---|---|---|---|---|---|---|---|---|
| Live | ADX trend strength | 888 | 444 | 444 | -0.0277 | -0.2406 | 0.1933 | 0.8653 | 0.9987 |
| Live | Candlestick pattern | 891 | 159 | 732 | -0.2161 | -0.4580 | 0.0539 | 0.1260 | 0.8011 |
| Live | MACD momentum | 891 | 432 | 459 | -0.1197 | -0.2530 | 0.0725 | 0.2004 | 0.9075 |
| Live | Market regime alignment | 891 | 593 | 298 | 0.0380 | -0.2479 | 0.2674 | 0.8501 | 0.9987 |
| Live | RSI trend alignment | 891 | 641 | 250 | -0.1715 | -0.3350 | 0.0692 | 0.1408 | 0.8011 |
| Live | Stop level confluence | 891 | 891 | 0 | n/a | n/a | n/a | n/a | n/a |
| Live | TTM Squeeze + volume breakout | 891 | 88 | 803 | -0.2567 | -0.4334 | -0.0240 | 0.0338 | 0.8011 |
| Live | Target distance quality | 891 | 891 | 0 | n/a | n/a | n/a | n/a | n/a |
| Live | Tight stop penalty | 891 | 867 | 24 | -0.1036 | n/a | n/a | n/a | n/a |
| TRAIN | ADX trend strength | 5554 | 3906 | 1648 | 0.1093 | -0.0887 | 0.3031 | 0.2760 | 0.9987 |
| TRAIN | Candlestick pattern | 5558 | 740 | 4818 | -0.1483 | -0.3690 | 0.0849 | 0.2008 | 0.9075 |
| TRAIN | MACD momentum | 5558 | 3076 | 2482 | -0.0394 | -0.2410 | 0.1592 | 0.7099 | 0.9987 |
| TRAIN | Market regime alignment | 5558 | 2942 | 2616 | -0.0352 | -0.2282 | 0.1608 | 0.7263 | 0.9987 |
| TRAIN | RSI trend alignment | 5558 | 3539 | 2019 | -0.0248 | -0.2328 | 0.1847 | 0.8199 | 0.9987 |
| TRAIN | Stop level confluence | 5558 | 5553 | 5 | 1.0132 | n/a | n/a | n/a | n/a |
| TRAIN | TTM Squeeze + volume breakout | 5558 | 167 | 5391 | -0.0643 | -0.4830 | 0.4455 | 0.7451 | 0.9987 |
| TRAIN | Target distance quality | 5558 | 5558 | 0 | n/a | n/a | n/a | n/a | n/a |
| TRAIN | Tight stop penalty | 5558 | 5558 | 0 | n/a | n/a | n/a | n/a | n/a |

## Screen candidates (BH q < 0.10 over all looks)

A row here has earned a Stage -2 screen of its own, never a filter.

None. No bucket and no factor has a BH q-value below 0.10 over all looks.

## Frictions

Live fills are not friction-adjusted (`LIVE_FILLS_INCLUDE_FRICTIONS = False`): the study applies the same `apply_frictions` + `commission_r` model to live rows as to TRAIN rows. TRAIN rows: the confluence replay's exit simulation applies no frictions, so the study re-applies them.

## Backfill: `v146_001` on the copy of the production rows

Production was at `v144_001`; 917 closed rows were exported at 2026-10-15T08:22:21Z and 896 were stamped with `confidence_points`. An unparsed line is counted and left out of the points.

| breakdown key | parsed | skipped | unparsed |
|---|---|---|---|
| ADX trend strength | 896 | 0 | 0 |
| Candlestick pattern | 896 | 0 | 0 |
| Level adjustment | 0 | 491 | 0 |
| MACD momentum | 896 | 0 | 0 |
| Market regime alignment | 896 | 0 | 0 |
| Quality score | 0 | 896 | 0 |
| RSI trend alignment | 896 | 0 | 0 |
| Stop level confluence | 896 | 0 | 0 |
| Strategies confirmed (base level) | 0 | 896 | 0 |
| TTM Squeeze + volume breakout | 896 | 0 | 0 |
| Target distance quality | 896 | 0 | 0 |
| Tight stop penalty | 872 | 0 | 0 |
| Track record (expectancy) | 0 | 896 | 0 |
| htf_counter_trend_penalty | 0 | 0 | 174 |

Live rows left out by the study (`load_live_rows` warning in the verdict-run log): 5 of 917 closed trades have no usable R (no `metrics.r_multiple`, no entry week, or a leg with no exit price to net). Of the 912 live rows kept, 21 carry no `confidence_score` and enter the buckets but not the monotonicity n (891).

## Provenance

- Code: branch `2026-10-09-v146-expectancy-attribution` at `8b4d71be`.
- Report: `data/reports/expectancy-attribution.json`, generated_at 2026-10-15T08:24:58.284671+00:00; provenance `{"earnings": {"calendar": "v82 earnings_calendar.sessions_to_reaction (NYSE sessions to the next earnings reaction session)", "directory": "E:\\Documents\\Private\\Projects\\Discord-Bot\\.claude\\worktrees\\2026-10-09-v146-expectancy-attribution\\market_data\\earnings", "files": 76, "newest_report_date": "2026-12-09", "sha256": "3eeb801204606318450cdb3774ff6c893a36538e5db2f46cc713433ae8d759a4"}, "frictions": {"commission_r": 0.02, "slippage_bps": 5.0}, "live_fills_include_frictions": false, "n_resamples": 10000, "train_rows": {"path": "E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-09-v146-expectancy-attribution/data/reports/v146-train-scenarios.jsonl", "rows": 5558, "sha256": "3447cad5785f442878b5cf6848a159de969500bc4fe1bfe096fb09a983e20ed7"}}`.
- Live: scratch copy of the production `trades` table (closed rows only), export sha256 `9e7528bba3696ee111921d7816081bccd5ac0c7e20cbfafa8a832e1d483351c0`, row fingerprint `94e718554937375d9087cdef423d7731` equal on production and on the copy; the scratch database was dropped after the run. Production was never written.
- TRAIN: `data/reports/v146-train-scenarios.jsonl`, 5558 rows, sha256 `3447cad5785f442878b5cf6848a159de969500bc4fe1bfe096fb09a983e20ed7`, 72/77 tickers, watchlist sha256 `4ba1e0942f66b5aafea49fa53d46ab9956577e639d07d0f5118350f41ec3212c`, run 2026-10-15T07:26:50Z..2026-10-15T08:20:30Z; by horizon `{"2m": 481, "2w": 389, "3m": 560, "4m": 572, "4w": 437, "5m": 596, "6m": 593, "7m": 659, "8m": 633, "9m": 638}`.
- Live window `{"first_week": "2026-07-06", "last_week": "2026-10-12"}`, n 912; notes `["Closed trades from the trades table, both ledgers. Confidence analyses use rows with a non-null confidence_score.", "Range-restricted: only trades at or above MIN_ALERT_CONFIDENCE_LEVEL were ever paper-traded, which attenuates any score-R slope; a weaker live slope is the expected shape, not by itself a contradiction.", "confidence_score is level-major (the quality score is repositioned inside the final level's band), so deciles read close to level, then quality.", "Earnings: risk_features.days_to_earnings, a provider point-in-time estimate in NYSE sessions; unknown for every trade opened before v146 I2 shipped."]`.
- TRAIN window `{"first_week": "2020-01-06", "last_week": "2023-12-25"}`, n 5558; notes `["TRAIN confluence replay (--scenarios --train --exit-model v2 --scale-out), not level-gated; VALIDATION is never read.", "The TRAIN score is computed with the expectancy level adjustment neutralised; the R:R distribution per tercile shows any residual effect.", "R net: the replay's exit_sim applies no frictions, so slippage and commission are re-applied here; exp_r_gross is the replay's own r_total.", "Earnings: actual report dates (CsvSource). Buckets >20 and none are ex-post, 11-20 partly; report timing is ex-post and can move a row across the 0-5 edge. Never merged with the live estimate.", "Backtest and live differ in their gap-fill model (exit_sim.py:541-548)."]`.
- Earnings: the `market_data/earnings/` file set named in the report provenance above, on the v82 earnings calendar (`swingbot/core/market/earnings_calendar.py`).

## Caveats

- **The score is level-major.** The legacy scorer repositions the quality score inside the final level's band, so score order is level order first and quality order within a level. The deciles are close to "level, then quality". Stated, not corrected.
- **The live book is range-restricted.** Only trades at or above the alert level were ever paper-traded, which attenuates any score-R slope live; the TRAIN replay is not level-gated. A weaker live slope is the expected shape, not by itself a contradiction. The per-level table is there so a live NOT PREDICTIVE is not misread as "score useless" when the alert gate already took the edge.
- **The TRAIN score neutralises the expectancy adjustment** (`scenario_rows.TRAIN_NEUTRAL_EXPECTANCY`, frozen before the run): the replay has no track record, and the adjustment is not neutral without one. R:R is reported per tercile beside the spread.
- **Earnings definitions differ and are never merged.** Live is a provider point-in-time estimate, `unknown` for every trade before v146 shipped. TRAIN uses actual report dates: `0-5` and `6-10` are mostly knowable at the signal, `11-20` partly, `>20` and `none` are ex-post. Report timing (before open / after close) is ex-post and can move a row across the `0-5` edge. Any earnings screen candidate needs a point-in-time re-check before its Stage -2 screen.
- **Fill models differ.** The backtest and the live tracker do not model gap fills identically (`swingbot/core/backtesting/exit_sim.py:541-548`), so R is comparable in sign and order, not to the last hundredth.
- **Multiple comparisons.** 113 looks; a bucket or factor is a screen candidate only at BH q < 0.10 over all of them. No threshold is chosen from these tables.
- **The live rows overlap v2's sealed holdout.** The live book's 2026 trades fall inside the v2 instrument's sealed holdout (2026-01-01 onward). Any follow-on filter screened from these tables has seen that period, so it cannot use that holdout as unseen data.
- **Instrument:** TRAIN replay run without an `--instrument` flag (none was offered).
- **Populations are never pooled.** No figure in this document combines live and TRAIN.

## What this licenses

Closes "raise the confidence floor" as a measured no; any bucket candidate stands on its own and needs its own Stage -2 screen.
Any bucket that looks bad (a regime, an RS quintile, an earnings bucket, a factor with a negative delta) is a screen candidate, never a filter.
