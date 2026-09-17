# v90 rejection-only armed entries — Stage 1 selection

**Verdict: SPIKE**

Window: 2018-06-01..2020-12-31 (fold-train only).

## Pre-registered rule

A cell is eligible iff its alert-volume cut vs baseline is <= 25% (clause 4), ΔExpR >= −0.01R (clause 2's margin) and mix-standardised ΔWR > 0. Among eligible cells the greatest ΔExpR is selected; ties go to the greater ΔWR, then the smaller N. The selected cell must sit on a plateau (plateau_report, tolerance 0.03R) along each of N, k and b with the other knobs held; any spike disqualifies.

Recorded limitations: daily-bar ordering is conservative (stop before target on the same bar); the universe is today's cached tickers (survivorship).

## All 30 cells

| cell | baseline N | component N | cut % | ΔWR pp | ΔExpR R | ExpR R | eligible | reasons |
|---|---|---|---|---|---|---|---|---|
| N3-k0.25-b0.00 | 1928 | 1682 | +12.76 | +5.74 | +0.0537 | +0.1613 | yes |  |
| N3-k0.25-b0.05 | 1928 | 1825 | +5.34 | +7.03 | +0.0192 | +0.1268 | yes |  |
| N3-k0.25-b0.10 | 1928 | 1942 | -0.73 | +6.94 | +0.0282 | +0.1358 | yes |  |
| N3-k0.25-b0.15 | 1928 | 2048 | -6.22 | +4.52 | +0.0050 | +0.1126 | yes |  |
| N3-k0.25-b0.20 | 1928 | 2106 | -9.23 | +3.74 | +0.0053 | +0.1129 | yes |  |
| N3-k0.50-b0.00 | 1928 | 1730 | +10.27 | +5.97 | +0.0541 | +0.1617 | yes |  |
| N3-k0.50-b0.05 | 1928 | 1890 | +1.97 | +6.87 | +0.0154 | +0.1230 | yes |  |
| N3-k0.50-b0.10 | 1928 | 2007 | -4.10 | +6.82 | +0.0243 | +0.1319 | yes |  |
| N3-k0.50-b0.15 | 1928 | 2112 | -9.54 | +4.61 | +0.0052 | +0.1127 | yes |  |
| N3-k0.50-b0.20 | 1928 | 2173 | -12.71 | +3.92 | +0.0047 | +0.1123 | yes |  |
| N5-k0.25-b0.00 | 1928 | 1688 | +12.45 | +5.91 | +0.0545 | +0.1621 | yes |  |
| N5-k0.25-b0.05 | 1928 | 1830 | +5.08 | +7.10 | +0.0187 | +0.1263 | yes |  |
| N5-k0.25-b0.10 | 1928 | 1949 | -1.09 | +6.81 | +0.0259 | +0.1335 | yes |  |
| N5-k0.25-b0.15 | 1928 | 2062 | -6.95 | +4.25 | -0.0029 | +0.1047 | yes |  |
| N5-k0.25-b0.20 | 1928 | 2125 | -10.22 | +3.31 | -0.0056 | +0.1020 | yes |  |
| N5-k0.50-b0.00 | 1928 | 1743 | +9.60 | +6.03 | +0.0525 | +0.1601 | yes |  |
| N5-k0.50-b0.05 | 1928 | 1904 | +1.24 | +6.80 | +0.0122 | +0.1198 | yes |  |
| N5-k0.50-b0.10 | 1928 | 2021 | -4.82 | +6.61 | +0.0210 | +0.1286 | yes |  |
| N5-k0.50-b0.15 | 1928 | 2134 | -10.68 | +4.21 | -0.0042 | +0.1034 | yes |  |
| N5-k0.50-b0.20 | 1928 | 2202 | -14.21 | +3.44 | -0.0042 | +0.1034 | yes |  |
| N10-k0.25-b0.00 | 1928 | 1688 | +12.45 | +6.12 | +0.0588 | +0.1664 | yes |  |
| N10-k0.25-b0.05 | 1928 | 1829 | +5.13 | +7.11 | +0.0191 | +0.1267 | yes |  |
| N10-k0.25-b0.10 | 1928 | 1948 | -1.04 | +6.82 | +0.0261 | +0.1337 | yes |  |
| N10-k0.25-b0.15 | 1928 | 2063 | -7.00 | +4.23 | -0.0041 | +0.1035 | yes |  |
| N10-k0.25-b0.20 | 1928 | 2128 | -10.37 | +3.28 | -0.0068 | +0.1008 | yes |  |
| N10-k0.50-b0.00 | 1928 | 1750 | +9.23 | +6.01 | +0.0527 | +0.1602 | yes |  |
| N10-k0.50-b0.05 | 1928 | 1913 | +0.78 | +6.80 | +0.0124 | +0.1200 | yes |  |
| N10-k0.50-b0.10 | 1928 | 2031 | -5.34 | +6.68 | +0.0220 | +0.1296 | yes |  |
| N10-k0.50-b0.15 | 1928 | 2146 | -11.31 | +4.24 | -0.0047 | +0.1029 | yes |  |
| N10-k0.50-b0.20 | 1928 | 2215 | -14.89 | +3.45 | -0.0047 | +0.1029 | yes |  |

Rule's pick before the plateau check: N10-k0.25-b0.00
Selected for Stage 0: none

## Plateau reports

- ARMED_N: grid [3, 5, 10], expectancies [0.1613, 0.1621, 0.1664], adopted 10, plateau True
- ARMED_K: grid [0.25, 0.5], expectancies [0.1664, 0.1602], adopted 0.25, plateau True
- ARMED_B: grid [0.0, 0.05, 0.1, 0.15, 0.2], expectancies [0.1664, 0.1267, 0.1337, 0.1035, 0.1008], adopted 0.0, plateau False

## Overlap with v88's R1 rows (spec §3.3)

This mechanism is not a re-label of v88's R1 population: dropping the R2/R3 issuances releases arms their 5-bar cooldown suppressed, and those arms shift later ones in turn. `n/a` means v88 never ran that `b`.

| cell | n | v88 R1 n | shared | new here | only in v88 |
|---|---|---|---|---|---|
| N3-k0.25-b0.00 | 1682 | n/a | n/a | n/a | n/a |
| N3-k0.25-b0.05 | 1825 | n/a | n/a | n/a | n/a |
| N3-k0.25-b0.10 | 1942 | 5134 | 1595 | 347 | 3539 |
| N3-k0.25-b0.15 | 2048 | n/a | n/a | n/a | n/a |
| N3-k0.25-b0.20 | 2106 | n/a | n/a | n/a | n/a |
| N3-k0.50-b0.00 | 1730 | n/a | n/a | n/a | n/a |
| N3-k0.50-b0.05 | 1890 | n/a | n/a | n/a | n/a |
| N3-k0.50-b0.10 | 2007 | 5287 | 1643 | 364 | 3644 |
| N3-k0.50-b0.15 | 2112 | n/a | n/a | n/a | n/a |
| N3-k0.50-b0.20 | 2173 | n/a | n/a | n/a | n/a |
| N5-k0.25-b0.00 | 1688 | n/a | n/a | n/a | n/a |
| N5-k0.25-b0.05 | 1830 | n/a | n/a | n/a | n/a |
| N5-k0.25-b0.10 | 1949 | 5141 | 1593 | 356 | 3548 |
| N5-k0.25-b0.15 | 2062 | n/a | n/a | n/a | n/a |
| N5-k0.25-b0.20 | 2125 | n/a | n/a | n/a | n/a |
| N5-k0.50-b0.00 | 1743 | n/a | n/a | n/a | n/a |
| N5-k0.50-b0.05 | 1904 | n/a | n/a | n/a | n/a |
| N5-k0.50-b0.10 | 2021 | 5307 | 1647 | 374 | 3660 |
| N5-k0.50-b0.15 | 2134 | n/a | n/a | n/a | n/a |
| N5-k0.50-b0.20 | 2202 | n/a | n/a | n/a | n/a |
| N10-k0.25-b0.00 | 1688 | n/a | n/a | n/a | n/a |
| N10-k0.25-b0.05 | 1829 | n/a | n/a | n/a | n/a |
| N10-k0.25-b0.10 | 1948 | 5151 | 1591 | 357 | 3560 |
| N10-k0.25-b0.15 | 2063 | n/a | n/a | n/a | n/a |
| N10-k0.25-b0.20 | 2128 | n/a | n/a | n/a | n/a |
| N10-k0.50-b0.00 | 1750 | n/a | n/a | n/a | n/a |
| N10-k0.50-b0.05 | 1913 | n/a | n/a | n/a | n/a |
| N10-k0.50-b0.10 | 2031 | 5313 | 1655 | 376 | 3658 |
| N10-k0.50-b0.15 | 2146 | n/a | n/a | n/a | n/a |
| N10-k0.50-b0.20 | 2215 | n/a | n/a | n/a | n/a |
