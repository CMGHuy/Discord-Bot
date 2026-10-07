# v127 structure-break armed entries — Stage 1 selection

**Verdict: NO_ELIGIBLE_CELL**

Window: 2018-06-01..2020-12-31 (fold-train only).

## Pre-registered rule

A cell is eligible iff its alert-volume cut vs baseline is <= 25% (clause 4), ΔExpR >= −0.01R (clause 2's margin) and mix-standardised ΔWR > 0. Among eligible cells the greatest ΔExpR is selected; ties go to the greater ΔWR, then the smaller N. The selected cell must sit on a plateau (plateau_report, tolerance 0.03R) along N and along k with the other knobs held; any spike disqualifies. `trigger` is categorical: both trigger rows at the selected N and k are reported, not plateau-checked.

Recorded limitations: daily-bar ordering is conservative (stop before target on the same bar); the universe is today's cached tickers (survivorship).

## All 12 cells

| cell | baseline N | component N | cut % | ΔWR pp | ΔExpR R | ExpR R | eligible | reasons |
|---|---|---|---|---|---|---|---|---|
| MSB-N5-k0.25 | 2590 | 4095 | -58.11 | -1.20 | -0.1411 | +0.0568 | no | profit: dExpR below -0.01R; win rate: standardised dWR not above 0 |
| MSB-N5-k0.50 | 2590 | 4147 | -60.12 | -1.06 | -0.1366 | +0.0614 | no | profit: dExpR below -0.01R; win rate: standardised dWR not above 0 |
| MSB-N10-k0.25 | 2590 | 4376 | -68.96 | -1.21 | -0.1410 | +0.0569 | no | profit: dExpR below -0.01R; win rate: standardised dWR not above 0 |
| MSB-N10-k0.50 | 2590 | 4432 | -71.12 | -1.09 | -0.1384 | +0.0595 | no | profit: dExpR below -0.01R; win rate: standardised dWR not above 0 |
| MSB-N15-k0.25 | 2590 | 4495 | -73.55 | -1.76 | -0.1443 | +0.0536 | no | profit: dExpR below -0.01R; win rate: standardised dWR not above 0 |
| MSB-N15-k0.50 | 2590 | 4555 | -75.87 | -1.89 | -0.1426 | +0.0553 | no | profit: dExpR below -0.01R; win rate: standardised dWR not above 0 |
| HL-N5-k0.25 | 2590 | 0 | +100.00 | n/a | n/a | n/a | no | volume: cut 100.00% > 25.0%; profit: dExpR below -0.01R; win rate: standardised dWR not above 0 |
| HL-N5-k0.50 | 2590 | 0 | +100.00 | n/a | n/a | n/a | no | volume: cut 100.00% > 25.0%; profit: dExpR below -0.01R; win rate: standardised dWR not above 0 |
| HL-N10-k0.25 | 2590 | 234 | +90.97 | -3.81 | -0.1522 | +0.0457 | no | volume: cut 90.97% > 25.0%; profit: dExpR below -0.01R; win rate: standardised dWR not above 0 |
| HL-N10-k0.50 | 2590 | 227 | +91.24 | -5.26 | -0.1875 | +0.0104 | no | volume: cut 91.24% > 25.0%; profit: dExpR below -0.01R; win rate: standardised dWR not above 0 |
| HL-N15-k0.25 | 2590 | 454 | +82.47 | -6.38 | -0.1691 | +0.0289 | no | volume: cut 82.47% > 25.0%; profit: dExpR below -0.01R; win rate: standardised dWR not above 0 |
| HL-N15-k0.50 | 2590 | 460 | +82.24 | -5.89 | -0.1677 | +0.0302 | no | volume: cut 82.24% > 25.0%; profit: dExpR below -0.01R; win rate: standardised dWR not above 0 |

Rule's pick before the plateau check: none
Selected for Stage 0: none

## Population disclosure (arms opened in the selection window)

| cell | armed | issued | regated | cancelled_zone_failed | expired | unresolved | alert-volume ratio |
|---|---|---|---|---|---|---|---|
| MSB-N5-k0.25 | 24386 | 4107 | 4308 | 9487 | 6484 | 0 | 1.581 |
| MSB-N5-k0.50 | 25066 | 4159 | 4382 | 9857 | 6668 | 0 | 1.601 |
| MSB-N10-k0.25 | 23252 | 4391 | 5216 | 10561 | 3084 | 0 | 1.690 |
| MSB-N10-k0.50 | 23907 | 4447 | 5312 | 11015 | 3133 | 0 | 1.711 |
| MSB-N15-k0.25 | 22693 | 4514 | 5771 | 10938 | 1470 | 0 | 1.736 |
| MSB-N15-k0.50 | 23328 | 4573 | 5897 | 11363 | 1495 | 0 | 1.759 |
| HL-N5-k0.25 | 23186 | 0 | 0 | 10574 | 12612 | 0 | 0.000 |
| HL-N5-k0.50 | 23836 | 0 | 0 | 10972 | 12864 | 0 | 0.000 |
| HL-N10-k0.25 | 20915 | 240 | 626 | 11929 | 8120 | 0 | 0.090 |
| HL-N10-k0.50 | 21478 | 233 | 630 | 12373 | 8242 | 0 | 0.088 |
| HL-N15-k0.25 | 19480 | 465 | 1715 | 12259 | 5041 | 0 | 0.175 |
| HL-N15-k0.50 | 19987 | 470 | 1746 | 12646 | 5125 | 0 | 0.178 |
