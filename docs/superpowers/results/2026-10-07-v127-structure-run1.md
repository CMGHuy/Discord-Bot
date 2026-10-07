# v127 structure-break armed entries — run1 replay

Rows in the selection window 2018-06-01..2020-12-31: 30065 across 64 tickers.

Recorded limitations: daily-bar ordering is conservative (stop before target on the same bar); the universe is today's cached tickers (survivorship).

| arm | rows | armed | issued | regated | cancelled_zone_failed | expired | unresolved |
|---|---|---|---|---|---|---|---|
| baseline | 2590 | | | | | | |
| MSB-N5-k0.25 | 4095 | 24386 | 4107 | 4308 | 9487 | 6484 | 0 |
| MSB-N5-k0.50 | 4147 | 25066 | 4159 | 4382 | 9857 | 6668 | 0 |
| MSB-N10-k0.25 | 4376 | 23252 | 4391 | 5216 | 10561 | 3084 | 0 |
| MSB-N10-k0.50 | 4432 | 23907 | 4447 | 5312 | 11015 | 3133 | 0 |
| MSB-N15-k0.25 | 4495 | 22693 | 4514 | 5771 | 10938 | 1470 | 0 |
| MSB-N15-k0.50 | 4555 | 23328 | 4573 | 5897 | 11363 | 1495 | 0 |
| HL-N5-k0.25 | 0 | 23186 | 0 | 0 | 10574 | 12612 | 0 |
| HL-N5-k0.50 | 0 | 23836 | 0 | 0 | 10972 | 12864 | 0 |
| HL-N10-k0.25 | 234 | 20915 | 240 | 626 | 11929 | 8120 | 0 |
| HL-N10-k0.50 | 227 | 21478 | 233 | 630 | 12373 | 8242 | 0 |
| HL-N15-k0.25 | 454 | 19480 | 465 | 1715 | 12259 | 5041 | 0 |
| HL-N15-k0.50 | 460 | 19987 | 470 | 1746 | 12646 | 5125 | 0 |
