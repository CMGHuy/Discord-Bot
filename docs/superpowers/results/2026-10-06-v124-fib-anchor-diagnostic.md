# v124 Fibonacci impulse-leg / anchor diagnostic -- results (2026-10-06)

Spec `2026-10-02-v124-fib-impulse-leg-diagnostic-design.md`; plan `..._0-index.md`. Instrument merged as `3b798c7d`;
witness hardening `b62e9e4f`; reproduction note `2026-10-06-v124-reproduction-note.md` (`94a83f73`).
Stage: read-only diagnostic. It gates nothing, spends no VALIDATION budget (v103 already spent Fibonacci's 2024-25 shot)
and keeps 2026 as the holdout. Entries 2015-01-01..2025-12-31, universe 74 (77 watchlist names, 3 filtered),
extended cache refreshed 2026-09-28, AVWAP_LEVELS_ENABLED = true. Raw JSON: `2026-10-06-v124-fib-{bullish,bearish}.json`,
`2026-10-06-v124-confluence-{0..11}.json` (12 disjoint chunks, 74 tickers), `2026-10-06-v124-fib-anchor-report.json`.
Arm 4 identification: 0 unidentified of 10,670 confluence trades (8,352 with a Fibonacci-family source), so arm 4 is measurable.

## Baseline reproduction -- recorded mismatch

The v103 `b=0` bullish reference did NOT reproduce (880 / 37.16% / +0.2483 / 74 vs 815 / 36.81% / +0.2219 / 73). The cause is
commit `a356c7f2` (v104, level-lifecycle stop widening capped at the 2% ceiling) plus the 2026-09-28 cache re-fetch; see the
reproduction note. Everything below is a within-instrument comparison on today's replay, not comparable to v103 absolutes.

## Verdicts (bullish only; exit rule quoted verbatim below)

- **Arm 1 anchored entry: does not pass.** The favourable bucket has a lower WR and lower ExpR than rest at every divisor (d=4/6/8).
- **Arm 2 zone + confluence: does not pass.** Favourable has lower WR and lower ExpR than rest at every divisor.
- **Arm 3 confirmation (`Close[t] > High[t-1]`): primary split passes** -- favourable WR 38.95% vs 34.10%, ExpR +0.293 vs +0.225,
  N 439 / 437 (both >= 30). It has earned a spec and nothing more: this diagnostic applies no significance test (+4.85 pp WR on
  N=876 is about 1.5 standard errors unpaired), tests four arms, and any follow-on faces Stage -1 to Stage 3 under its own
  pre-registration and its own holdout.
- **Arm 4 confluence with a Fibonacci candidate: does not pass.** Favourable WR 33.52% vs 38.54% (d=4), ExpR +0.031 vs +0.170; the
  same sign at d=6 and d=8.

Bearish rows are description only. The bearish arm 4 split points the other way (favourable +0.114R vs rest -0.106R at d=4); under
the pre-registered rule that selects nothing and starts no follow-on.

Diagnostic window 2015-01-01..2025-12-31 (entries and features; 2026 is the holdout). AVWAP_LEVELS_ENABLED: [True].

## Exit rule (fixed in the spec)

> An arm proceeds to its own spec only if, on the bullish side, the favourable bucket has a higher win rate and an ExpR no lower than the rest, with N >= 30 in each bucket. Arms 1, 2 and 4 must also keep the win-rate sign at two of the three divisors.

## Baseline reproduction (v103 reference arm, b=0, on 2010-01-01..2023-12-31)

| direction | N | WR | ExpR | universe | reference N / WR / ExpR / universe | matches |
|---|---|---|---|---|---|---|
| bullish | 880 | 37.16% | +0.2483 | 74 | 815 / 36.81% / +0.2219 / 73 | False |
| bearish | 161 | 33.54% | +0.0600 | 74 | 169 / 23.67% / -0.1269 / 73 | False |

## Verdicts (bullish only)

| arm | primary passes | WR-sign divisors | proceeds |
|---|---|---|---|
| arm1 | False | 0 | False |
| arm2 | False | 0 | False |
| arm3 | True | - | True |
| arm4 | False | 0 | False |

## Fibonacci bullish

#### Arm 1 anchored entry -- primary split

| bucket | N | WR | ExpR |
|---|---|---|---|
| d=4 favourable | 373 | 36.19% | +0.229 |
| d=4 rest | 503 | 36.78% | +0.279 |
| d=6 favourable | 282 | 35.11% | +0.151 |
| d=6 rest | 594 | 37.21% | +0.309 |
| d=8 favourable | 177 | 35.59% | +0.149 |
| d=8 rest | 699 | 36.77% | +0.287 |

#### Arm 1 anchored entry -- described: rolling_origin_is_fractal

| bucket | N | WR | ExpR |
|---|---|---|---|
| False | 186 | 34.95% | +0.264 |
| True | 690 | 36.96% | +0.257 |

#### Arm 1 anchored entry -- described: broke_structure

| bucket | N | WR | ExpR |
|---|---|---|---|
| False | 226 | 33.19% | +0.210 |
| None | 165 | 39.39% | +0.438 |
| True | 485 | 37.11% | +0.219 |

#### Arm 1 anchored entry -- described: leg_atr_quintile

| bucket | N | WR | ExpR |
|---|---|---|---|
| Q1 | 129 | 34.11% | +0.184 |
| Q2 | 138 | 28.99% | +0.018 |
| Q3 | 146 | 34.25% | +0.135 |
| Q4 | 141 | 40.43% | +0.474 |
| Q5 | 157 | 40.76% | +0.270 |
| no leg | 165 | 39.39% | +0.438 |

#### Arm 2 zone + confluence -- primary split

| bucket | N | WR | ExpR |
|---|---|---|---|
| d=4 favourable | 611 | 36.33% | +0.227 |
| d=4 rest | 265 | 36.98% | +0.333 |
| d=6 favourable | 591 | 35.03% | +0.195 |
| d=6 rest | 285 | 39.65% | +0.391 |
| d=8 favourable | 557 | 34.47% | +0.167 |
| d=8 rest | 319 | 40.13% | +0.417 |

#### Arm 2 zone + confluence -- described: zone_touch

| bucket | N | WR | ExpR |
|---|---|---|---|
| False | 355 | 39.44% | +0.353 |
| None | 165 | 39.39% | +0.438 |
| True | 356 | 32.30% | +0.085 |

#### Arm 2 zone + confluence -- described: close_in_zone

| bucket | N | WR | ExpR |
|---|---|---|---|
| False | 769 | 36.28% | +0.260 |
| True | 107 | 38.32% | +0.248 |

#### Arm 2 zone + confluence -- described: tested_ratio

| bucket | N | WR | ExpR |
|---|---|---|---|
| 0.382 | 586 | 37.37% | +0.308 |
| 0.5 | 233 | 33.05% | +0.121 |
| 0.618 | 57 | 42.11% | +0.339 |

#### Arm 2 zone + confluence -- described: rolling_level_confluence

| bucket | N | WR | ExpR |
|---|---|---|---|
| False | 234 | 32.48% | +0.111 |
| True | 642 | 38.01% | +0.313 |

#### Arm 3 confirmation -- primary split

| bucket | N | WR | ExpR |
|---|---|---|---|
| favourable | 439 | 38.95% | +0.293 |
| rest | 437 | 34.10% | +0.225 |

#### Arm 3 confirmation -- described: rejection_wick_half_range

| bucket | N | WR | ExpR |
|---|---|---|---|
| False | 683 | 36.90% | +0.257 |
| True | 193 | 35.23% | +0.264 |

## Fibonacci bearish (description only)

#### Arm 1 anchored entry -- primary split

| bucket | N | WR | ExpR |
|---|---|---|---|
| d=4 favourable | 60 | 38.33% | +0.119 |
| d=4 rest | 106 | 37.74% | +0.204 |
| d=6 favourable | 36 | 36.11% | +0.073 |
| d=6 rest | 130 | 38.46% | +0.201 |
| d=8 favourable | 18 | 33.33% | +0.117 |
| d=8 rest | 148 | 38.51% | +0.176 |

#### Arm 1 anchored entry -- described: rolling_origin_is_fractal

| bucket | N | WR | ExpR |
|---|---|---|---|
| False | 25 | 36.00% | +0.154 |
| True | 141 | 38.30% | +0.169 |

#### Arm 1 anchored entry -- described: broke_structure

| bucket | N | WR | ExpR |
|---|---|---|---|
| False | 65 | 41.54% | +0.199 |
| None | 36 | 36.11% | +0.205 |
| True | 65 | 35.38% | +0.124 |

#### Arm 1 anchored entry -- described: leg_atr_quintile

| bucket | N | WR | ExpR |
|---|---|---|---|
| Q1 | 25 | 36.00% | +0.227 |
| Q2 | 30 | 46.67% | +0.260 |
| Q3 | 29 | 41.38% | +0.384 |
| Q4 | 27 | 33.33% | -0.058 |
| Q5 | 19 | 31.58% | -0.013 |
| no leg | 36 | 36.11% | +0.205 |

#### Arm 2 zone + confluence -- primary split

| bucket | N | WR | ExpR |
|---|---|---|---|
| d=4 favourable | 112 | 34.82% | +0.118 |
| d=4 rest | 54 | 44.44% | +0.270 |
| d=6 favourable | 94 | 35.11% | +0.121 |
| d=6 rest | 72 | 41.67% | +0.235 |
| d=8 favourable | 90 | 35.56% | +0.129 |
| d=8 rest | 76 | 40.79% | +0.223 |

#### Arm 2 zone + confluence -- described: zone_touch

| bucket | N | WR | ExpR |
|---|---|---|---|
| False | 80 | 50.00% | +0.410 |
| None | 36 | 36.11% | +0.205 |
| True | 50 | 20.00% | -0.176 |

#### Arm 2 zone + confluence -- described: close_in_zone

| bucket | N | WR | ExpR |
|---|---|---|---|
| False | 148 | 41.22% | +0.247 |
| True | 18 | 11.11% | -0.578 |

#### Arm 2 zone + confluence -- described: tested_ratio

| bucket | N | WR | ExpR |
|---|---|---|---|
| 0.382 | 96 | 41.67% | +0.257 |
| 0.5 | 53 | 33.96% | +0.047 |
| 0.618 | 17 | 29.41% | -0.062 |

#### Arm 2 zone + confluence -- described: rolling_level_confluence

| bucket | N | WR | ExpR |
|---|---|---|---|
| False | 45 | 37.78% | +0.407 |
| True | 121 | 38.02% | +0.099 |

#### Arm 3 confirmation -- primary split

| bucket | N | WR | ExpR |
|---|---|---|---|
| favourable | 87 | 33.33% | -0.009 |
| rest | 79 | 43.04% | +0.364 |

#### Arm 3 confirmation -- described: rejection_wick_half_range

| bucket | N | WR | ExpR |
|---|---|---|---|
| False | 137 | 37.23% | +0.160 |
| True | 29 | 41.38% | +0.203 |

## Confluence (arm 4)

#### Whole confluence population (described)

| bucket | N | WR | ExpR |
|---|---|---|---|
| bullish | 5539 | 36.07% | +0.119 |
| bearish | 5131 | 29.90% | -0.072 |

Unidentified trades: 0. Trades with a Fibonacci-family source: 8352.

#### Arm 4 bullish -- primary split

| bucket | N | WR | ExpR |
|---|---|---|---|
| d=4 favourable | 916 | 33.52% | +0.031 |
| d=4 rest | 2758 | 38.54% | +0.170 |
| d=6 favourable | 821 | 32.16% | -0.006 |
| d=6 rest | 2853 | 38.77% | +0.176 |
| d=8 favourable | 721 | 30.93% | -0.028 |
| d=8 rest | 2953 | 38.84% | +0.176 |

#### Arm 4 bearish -- primary split

| bucket | N | WR | ExpR |
|---|---|---|---|
| d=4 favourable | 485 | 34.64% | +0.114 |
| d=4 rest | 3046 | 29.88% | -0.106 |
| d=6 favourable | 473 | 34.67% | +0.113 |
| d=6 rest | 3058 | 29.89% | -0.105 |
| d=8 favourable | 450 | 34.44% | +0.115 |
| d=8 rest | 3081 | 29.96% | -0.104 |

