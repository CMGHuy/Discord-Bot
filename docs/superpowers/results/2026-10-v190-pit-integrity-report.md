# v190 PIT store integrity report

Generated: 2026-10-31T18:52:22Z

This report is frozen before any strategy result is read. Running --mode update on the store afterwards makes every v3 run stop with StaleIntegrityError.

## Counts

Tickers: 821; admitted: 754; excluded: 67; no bars: 44; aliases: 0.

## Thresholds

| Threshold | Value |
| --- | --- |
| max_missing_run | 5 |
| trailing_sessions | 60 |
| min_trailing_share | 0.95 |
| break_move | 0.5 |
| break_ratio | 10.0 |
| revert_sessions | 20 |
| gap_sessions | 20 |
| edge_sessions | 20 |

## Manifest sha256

| Timeframe | sha256 |
| --- | --- |
| 15min | 9b61d9853714051d8d87a81e0555ea49cc8649acfc5abab1466136e7d84d7ecc |
| hourly | 4f6677c76a637a9d77e0f809bc9e2aa775445dd9b4c7525eea921b08e88ba3ad |
| daily | a2b8fd240553e70c90d7a9c3be19428c9b56b462e35cd5e874601bc4a9169d41 |

## Detector sha

| Path | Blob |
| --- | --- |
| scripts/data/alpaca_history/reuse.py | 11ca528237094371aca4997cfccebf167d498d82 |
| scripts/data/alpaca_history/pit_coverage.py | 8753cea14988d07b175f53593067ac6e8848f0df |

## Excluded

| Ticker | Reason |
| --- | --- |
| ACN | identity re-derived: flagged: price-mismatch |
| ALLE | identity re-derived: flagged: price-mismatch |
| APA | identity re-derived: flagged: price-mismatch |
| APTV | identity re-derived: flagged: price-mismatch |
| ARNC | in-span break 2020-04-01 (price): resolve by hand |
| BDX | identity re-derived: flagged: price-mismatch |
| BG | identity re-derived: flagged: price-mismatch |
| BNY | identity re-derived: flagged: price-mismatch |
| CB | identity re-derived: flagged: price-mismatch |
| CBOE | identity re-derived: flagged: price-mismatch |
| CL | identity re-derived: flagged: price-mismatch |
| CRH | identity re-derived: flagged: price-mismatch |
| CTRA | in-span break 2021-10-04 (volume): resolve by hand |
| CTVA | identity re-derived: flagged: price-mismatch |
| CVS | identity re-derived: flagged: price-mismatch |
| DHR | identity re-derived: flagged: price-mismatch |
| DOC | identity re-derived: flagged: price-mismatch |
| DVN | identity re-derived: flagged: price-mismatch |
| EG | identity re-derived: flagged: price-mismatch |
| FB | identity re-derived: flagged: short-overlap |
| FDXF | no daily bars in the store window |
| FI | in-span break 2023-06-07 (price+volume): resolve by hand |
| FLEX | identity re-derived: flagged: price-mismatch |
| FRC | in-span break 2023-03-13 (volume): resolve by hand |
| FRT | identity re-derived: flagged: price-mismatch |
| FTI | identity re-derived: flagged: price-mismatch |
| FTV | identity re-derived: flagged: price-mismatch |
| HONA | no daily bars in the store window |
| HP | identity re-derived: flagged: price-mismatch |
| IBM | identity re-derived: flagged: price-mismatch |
| IP | identity re-derived: flagged: price-mismatch |
| J | identity re-derived: flagged: price-mismatch |
| JCI | identity re-derived: flagged: price-mismatch |
| JEF | identity re-derived: flagged: price-mismatch |
| KG | identity re-derived: flagged: price-mismatch |
| LEN | identity re-derived: flagged: price-mismatch |
| LH | identity re-derived: flagged: price-mismatch |
| LMT | identity re-derived: flagged: price-mismatch |
| LOW | identity re-derived: flagged: price-mismatch |
| MAA | identity re-derived: flagged: price-mismatch |
| MDT | identity re-derived: flagged: price-mismatch |
| MI | identity re-derived: flagged: price-mismatch |
| MMM | identity re-derived: flagged: price-mismatch |
| MRK | identity re-derived: flagged: price-mismatch |
| NXPI | identity re-derived: flagged: price-mismatch |
| O | identity re-derived: flagged: price-mismatch |
| PARA | identity re-derived: flagged: price-mismatch |
| PAYX | identity re-derived: flagged: price-mismatch |
| PCL | identity re-derived: flagged: short-overlap |
| PG | identity re-derived: flagged: price-mismatch |
| PRGO | identity re-derived: flagged: price-mismatch |
| PSKY | identity re-derived: flagged: short-overlap |
| SBNY | identity re-derived: flagged: short-overlap |
| SIG | identity re-derived: flagged: price-mismatch |
| SIVB | unresolved break 2023-03-09 (edge) |
| SLG | identity re-derived: flagged: price-mismatch |
| SNDK | identity re-derived: flagged: short-overlap |
| STE | identity re-derived: flagged: price-mismatch |
| SW | identity re-derived: flagged: price-mismatch |
| T | identity re-derived: flagged: price-mismatch |
| TDG | identity re-derived: flagged: price-mismatch |
| TE | identity re-derived: flagged: price-mismatch |
| TT | identity re-derived: flagged: price-mismatch |
| WDC | identity re-derived: flagged: price-mismatch |
| WTW | identity re-derived: flagged: price-mismatch |
| XEL | identity re-derived: flagged: price-mismatch |
| ZBH | identity re-derived: flagged: price-mismatch |

## Trims

| Ticker | keep_from | keep_before | Reason |
| --- | --- | --- | --- |
| BBBY | None | 2025-08-29 | break after last membership end |
| CAM | None | 2025-10-06 | break after last membership end |
| CHK | None | 2021-02-10 | break after last membership end |
| CNX | None | 2017-11-29 | break after last membership end |
| DNB | None | 2020-07-01 | break after last membership end |
| DNR | None | 2016-03-04 | break after last membership end |
| DO | None | 2022-03-30 | break after last membership end |
| FL | None | 2025-05-15 | break after last membership end |
| GME | None | 2021-01-13 | break after last membership end |
| HCP | None | 2021-12-09 | break after last membership end |
| HOOD | 2021-08-04 | None | break before first membership start |
| KG | None | 2025-05-28 | break after last membership end |
| LIFE | None | 2021-09-13 | break after last membership end |
| LLL | None | 2021-10-13 | break after last membership end |
| LUMN | None | 2024-08-06 | break after last membership end |
| MI | None | 2021-03-15 | break after last membership end |
| MNK | None | 2022-10-27 | break after last membership end |
| MON | None | 2021-03-16 | break after last membership end |
| NKTR | None | 2025-06-24 | break after last membership end |
| NVLS | None | 2016-11-29 | break after last membership end |
| PLL | None | 2020-09-28 | break after last membership end |
| POM | None | 2025-10-08 | break after last membership end |
| PX | None | 2021-10-21 | break after last membership end |
| QEP | None | 2020-03-09 | break after last membership end |
| RRD | None | 2016-10-03 | break after last membership end |
| SMCI | 2020-01-14 | None | break before first membership start |
| STI | None | 2024-03-11 | break after last membership end |
| SVU | None | 2018-07-26 | break after last membership end |
| TE | None | 2024-11-06 | break after last membership end |
| WIN | None | 2019-02-19 | break after last membership end |

## Breaks

| Ticker | Date | Kind | Resolution |
| --- | --- | --- | --- |
| APTV | 2017-12-05 | edge | unresolved |
| ARNC | 2020-04-01 | price | in_span |
| BBBY | 2025-08-29 | price+volume | trim_after |
| CAM | 2025-10-06 | volume | trim_after |
| CHK | 2021-02-10 | volume | trim_after |
| CNX | 2017-11-29 | volume | trim_after |
| CTRA | 2021-10-04 | volume | in_span |
| DNB | 2020-07-01 | volume | trim_after |
| DNR | 2016-03-04 | move | trim_after |
| DO | 2022-03-30 | volume | trim_after |
| FI | 2023-06-07 | price+volume | in_span |
| FL | 2025-05-15 | move | trim_after |
| FRC | 2023-03-13 | volume | in_span |
| GME | 2021-01-13 | move | trim_after |
| GME | 2021-01-22 | move | trim_after |
| GME | 2021-01-26 | move | trim_after |
| GME | 2021-01-27 | price | trim_after |
| GME | 2021-02-24 | move | trim_after |
| GME | 2024-05-13 | move | trim_after |
| GME | 2024-05-14 | move | trim_after |
| HCP | 2021-12-09 | volume | trim_after |
| HOOD | 2021-08-04 | edge | trim_before |
| KG | 2025-05-28 | price | trim_after |
| LIFE | 2021-09-13 | move | trim_after |
| LLL | 2021-10-13 | price+volume | trim_after |
| LUMN | 2024-08-06 | move | trim_after |
| MI | 2021-03-15 | price+volume | trim_after |
| MI | 2021-03-17 | price+volume | trim_after |
| MI | 2021-03-22 | move | trim_after |
| MNK | 2022-10-27 | price+volume | trim_after |
| MON | 2021-03-16 | price+volume | trim_after |
| NKTR | 2025-06-24 | move | trim_after |
| NVLS | 2016-11-29 | move | trim_after |
| PLL | 2020-09-28 | volume | trim_after |
| POM | 2025-10-08 | move | trim_after |
| POM | 2025-12-10 | edge | trim_after |
| PX | 2021-10-21 | price+volume | trim_after |
| QEP | 2020-03-09 | move | trim_after |
| QEP | 2020-03-13 | move | trim_after |
| RRD | 2016-10-03 | move | trim_after |
| SIVB | 2023-03-09 | edge | unresolved |
| SMCI | 2020-01-14 | volume | trim_before |
| STI | 2024-03-11 | move | trim_after |
| STI | 2024-03-18 | move | trim_after |
| STI | 2024-06-18 | move | trim_after |
| STI | 2025-10-13 | move | trim_after |
| SVU | 2018-07-26 | move | trim_after |
| TE | 2024-11-06 | move | trim_after |
| WIN | 2019-02-19 | edge | trim_after |

## Signal cuts

| Ticker | Start | end_excl | Reason |
| --- | --- | --- | --- |
| AABA | 2016-01-04 | 2017-06-19 | missing run of 367 sessions |
| AABA | 2016-01-04 | 2017-06-19 | trailing 60-session coverage under 95% |
| ADT | 2016-01-04 | 2016-05-02 | missing run of 82 sessions |
| ADT | 2016-01-04 | 2016-05-02 | trailing 60-session coverage under 95% |
| AMCR | 2019-06-07 | 2019-08-29 | trailing 60-session coverage under 95% |
| AMTM | 2024-09-30 | 2024-12-18 | trailing 60-session coverage under 95% |
| ANDV | 2016-01-04 | 2017-08-01 | missing run of 397 sessions |
| ANDV | 2016-01-04 | 2017-10-19 | trailing 60-session coverage under 95% |
| APTV | 2016-01-04 | 2017-11-17 | missing run of 474 sessions |
| APTV | 2016-01-04 | 2018-02-09 | trailing 60-session coverage under 95% |
| ARNC | 2016-01-04 | 2016-11-01 | missing run of 210 sessions |
| ARNC | 2016-01-04 | 2017-01-24 | trailing 60-session coverage under 95% |
| BBWI | 2021-08-03 | 2021-10-21 | trailing 60-session coverage under 95% |
| BHF | 2017-08-07 | 2017-10-04 | trailing 60-session coverage under 95% |
| BHGE | 2016-01-04 | 2017-07-05 | missing run of 378 sessions |
| BHGE | 2016-01-04 | 2017-09-22 | trailing 60-session coverage under 95% |
| CARR | 2020-04-03 | 2020-06-24 | trailing 60-session coverage under 95% |
| CEG | 2022-02-02 | 2022-04-25 | trailing 60-session coverage under 95% |
| CTVA | 2019-06-03 | 2019-08-21 | trailing 60-session coverage under 95% |
| DAY | 2024-02-01 | 2024-04-23 | trailing 60-session coverage under 95% |
| DOW | 2016-01-04 | 2017-09-01 | missing run of 420 sessions |
| DOW | 2016-01-04 | 2017-09-01 | trailing 60-session coverage under 95% |
| DOW | 2019-04-02 | 2019-06-10 | trailing 60-session coverage under 95% |
| DWDP | 2017-09-01 | 2017-11-21 | trailing 60-session coverage under 95% |
| DXC | 2017-04-04 | 2017-06-22 | trailing 60-session coverage under 95% |
| EMC | 2016-01-04 | 2016-09-07 | missing run of 171 sessions |
| EMC | 2016-01-04 | 2016-09-07 | trailing 60-session coverage under 95% |
| EVRG | 2018-06-05 | 2018-08-23 | trailing 60-session coverage under 95% |
| FB | 2016-01-04 | 2022-06-09 | missing run of 1620 sessions |
| FB | 2016-01-04 | 2022-06-09 | trailing 60-session coverage under 95% |
| FOX | 2016-01-04 | 2019-03-13 | missing run of 802 sessions |
| FOX | 2016-01-04 | 2019-06-03 | trailing 60-session coverage under 95% |
| FOXA | 2016-01-04 | 2019-03-12 | missing run of 801 sessions |
| FOXA | 2016-01-04 | 2019-05-31 | trailing 60-session coverage under 95% |
| FTI | 2017-01-03 | 2017-01-17 | missing run of 9 sessions |
| FTI | 2017-01-06 | 2017-04-06 | trailing 60-session coverage under 95% |
| FTV | 2016-07-05 | 2016-09-22 | trailing 60-session coverage under 95% |
| GEHC | 2023-01-04 | 2023-03-09 | trailing 60-session coverage under 95% |
| GEV | 2024-04-02 | 2024-06-21 | trailing 60-session coverage under 95% |
| HWM | 2020-04-06 | 2020-06-22 | trailing 60-session coverage under 95% |
| INFO | 2017-06-02 | 2022-03-02 | missing run of 1195 sessions |
| INFO | 2017-06-02 | 2022-03-02 | trailing 60-session coverage under 95% |
| IR | 2016-01-04 | 2017-05-12 | missing run of 342 sessions |
| IR | 2016-01-04 | 2017-08-02 | trailing 60-session coverage under 95% |
| JNPR | 2025-07-08 | 2025-07-09 | trailing 60-session coverage under 95% |
| LB | 2016-01-04 | 2021-08-03 | missing run of 1405 sessions |
| LB | 2016-01-04 | 2021-08-03 | trailing 60-session coverage under 95% |
| LIN | 2018-11-06 | 2019-01-24 | trailing 60-session coverage under 95% |
| NBL | 2020-10-08 | 2020-10-12 | trailing 60-session coverage under 95% |
| NLOK | 2019-11-05 | 2020-01-28 | trailing 60-session coverage under 95% |
| OGN | 2021-06-04 | 2021-08-23 | trailing 60-session coverage under 95% |
| OTIS | 2020-04-03 | 2020-06-24 | trailing 60-session coverage under 95% |
| PCL | 2016-01-04 | 2016-02-22 | missing run of 33 sessions |
| PCL | 2016-01-04 | 2016-02-22 | trailing 60-session coverage under 95% |
| PEAK | 2019-11-05 | 2020-01-28 | trailing 60-session coverage under 95% |
| PSKY | 2025-08-08 | 2025-10-27 | trailing 60-session coverage under 95% |
| Q | 2025-11-03 | 2026-01-01 | trailing 60-session coverage under 95% |
| RHT | 2019-07-12 | 2019-07-15 | trailing 60-session coverage under 95% |
| SBNY | 2021-12-20 | 2023-03-15 | missing run of 309 sessions |
| SBNY | 2021-12-20 | 2023-03-15 | trailing 60-session coverage under 95% |
| SE | 2016-01-04 | 2017-02-27 | missing run of 289 sessions |
| SE | 2016-01-04 | 2017-02-27 | trailing 60-session coverage under 95% |
| SNDK | 2016-01-04 | 2016-05-12 | missing run of 90 sessions |
| SNDK | 2016-01-04 | 2016-05-12 | trailing 60-session coverage under 95% |
| SOLS | 2025-10-30 | 2025-12-22 | trailing 60-session coverage under 95% |
| SOLV | 2024-04-01 | 2024-06-20 | trailing 60-session coverage under 95% |
| STI | 2016-01-04 | 2019-12-09 | missing run of 990 sessions |
| STI | 2016-01-04 | 2019-12-09 | trailing 60-session coverage under 95% |
| TE | 2016-01-04 | 2016-07-01 | missing run of 125 sessions |
| TE | 2016-01-04 | 2016-07-01 | trailing 60-session coverage under 95% |
| UA | 2016-04-08 | 2016-06-13 | trailing 60-session coverage under 95% |
| UAA | 2016-01-04 | 2016-04-08 | missing run of 66 sessions |
| UAA | 2016-01-04 | 2016-06-28 | trailing 60-session coverage under 95% |
| VIAC | 2019-12-05 | 2020-02-27 | trailing 60-session coverage under 95% |
| VLTO | 2023-10-02 | 2023-12-22 | trailing 60-session coverage under 95% |
| VNT | 2020-10-12 | 2020-12-30 | trailing 60-session coverage under 95% |
| VTRS | 2020-11-17 | 2021-02-04 | trailing 60-session coverage under 95% |
| WBD | 2022-04-11 | 2022-07-01 | trailing 60-session coverage under 95% |
| WLTW | 2016-01-05 | 2016-02-01 | trailing 60-session coverage under 95% |
| WYND | 2016-01-04 | 2018-05-31 | missing run of 606 sessions |
| WYND | 2016-01-04 | 2018-05-31 | trailing 60-session coverage under 95% |
| XLC | 2016-01-04 | 2018-06-19 | missing run of 619 sessions |
| XLC | 2016-01-04 | 2018-09-07 | trailing 60-session coverage under 95% |

## Bars dropped before the reference

| Ticker | Count |
| --- | --- |
| ADT | 515 |
| DOW | 807 |
| EMC | 1853 |
| EXE | 1285 |
| FB | 2383 |
| FOX | 802 |
| FOXA | 801 |
| INFO | 2207 |
| IR | 342 |
| LB | 2135 |
| PARA | 1287 |
| PCL | 2410 |
| S | 1382 |
| SBNY | 2168 |
| SE | 454 |
| SHLD | 1937 |
| UA | 55 |
| VLTO | 1951 |
| VRT | 650 |

## Reference sources

| Source | Count |
| --- | --- |
| backtest_cache_ext | 626 |
| none | 195 |

## No bars

ACS, ANRZQ, AYE, BDK, BJS, BMC, BNI, BTUUQ, CBE, CEPH, CFN, CMCSK, COV, CPWR, CVH, EKDKQ, FDO, GR, HCBK, HNZ, HSH, HSP, KRFT, LO, MEE, MFE, MHS, MOLX, MWV, NOVL, NYX, PBG, PETM, PGN, PTV, RSHCQ, RX, SIAL, SUNEQ, SWY, TEG, TIE, TLAB, XTO

## Aliases

none
