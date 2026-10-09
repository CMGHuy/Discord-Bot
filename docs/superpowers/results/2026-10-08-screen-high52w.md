# v140 screen: `high52w` -> SCREEN-FAIL

**Ledger id:** `screen-high52w` (instrument `screen-v1`); BH q = 1.0000 across the ledger (reported, never gating).

**Run:** 2026-10-08; window 2010-01-01..2019-12-31; events count from 2011-01-01 (earlier bars only prime the indicators); the year rule is 7 of 9 calendar years (2011-2019); `python scripts/backtest/screen_idea.py --idea high52w`; null K = 20, seed 42 per (idea, ticker); bootstrap 10,000 week resamples, seed 42.

**Trigger:** close >= 0.95 x the 252-bar high with SMA50 > SMA200; first true bar after >= 20 consecutive computable false bars (George & Hwang (2004)); params near_high=0.95, lookback=252, fast_sma=50, slow_sma=200, quiet_bars=20; time cap 60 bars; long only.

**Trade:** entry next open; stop 1.5 x ATR14; target 3.0 x ATR14; a gap through either level fills at the open; stop first on a bar touching both; costs 5.0 bps a side + 0.0200R commission.

**Spec:** `docs/superpowers/specs/2026-10-08-v140-idea-screen-design.md`

## Universe and counters

| | count |
|---|---|
| point-in-time S&P 500 members in the window | 719 |
| cached and screened | 506 |
| missing from the cache (survivorship that remains) | 213 |
| cached but empty inside the window | 14 |
| raw events | 4806 |
| `dropped_nonmember` | 997 |
| `dropped_warmup` | 0 |
| `dropped_window` | 178 |
| `skipped_overlap` | 3 |
| `dropped_no_match` | 16 |
| **kept events (N)** | **3612** |

PIT members missing from the cache: AABA, ABC, ABMD, ACS, ADS, AET, AGN, AKS, ALTR, ALXN, ANDV, ANRZQ, ANSS, ANTM, APC, APOL, ARG, ARNC, ATGE, ATVI, AVB, AVP, AYE, BBBY, BCR, BDK, BHGE, BIG, BJS, BK, BLL, BMC, BMS, BNI, BRCM, BTUUQ, BXLT, CA, CAM, CBE, CBS, CCE, CELG, CEPH, CERN, CFN, CHK, CMA, CMCSK, COG, COL, COV, CPGX, CSRA, CTL, CTXS, CVC, CVH, CXO, DF, DFS, DISCA, DISCK, DISH, DNB, DNR, DO, DRE, DTV, DWDP, EA, EKDKQ, ENDP, EQR, ESRX, ESV, ETFC, EVHC, FBHS, FDO, FII, FL, FLIR, FLT, FRC, FRX, FTR, GAS, GGP, GMCR, GPS, HAR, HBI, HCBK, HCP, HES, HFC, HNZ, HOLX, HOT, HRS, HSH, HSP, IGT, IPG, JCP, JEC, JNPR, JNS, JOY, JWN, K, KORS, KRFT, KSU, LEG, LIFE, LLL, LLTC, LM, LO, LSI, LVLT, LXK, MDP, MEE, MFE, MHS, MIL, MJN, MMC, MNK, MOLX, MON, MRO, MWV, MWW, MXIM, MYL, NBL, NFX, NLOK, NLSN, NOVL, NSM, NVLS, NYX, ODP, PBCT, PBG, PCP, PDCO, PEAK, PETM, PGN, PKI, PLL, POM, PTV, PX, PXD, Q, QEP, QLGC, RAI, RDC, RE, RHT, RRD, RSHCQ, RTN, RX, SCG, SEE, SIAL, SIVB, SNI, SPLS, SRCL, STJ, STR, SUNEQ, SVU, SWN, SWY, SYMC, TEG, TGNA, TIE, TIF, TLAB, TMK, TSS, TWC, TWTR, TWX, UTX, VAR, VIAB, VIAC, WBA, WCG, WFM, WIN, WLTW, WPX, WRK, WYND, X, XEC, XL, XLNX, XTO.

## Verdict: SCREEN-FAIL

| Clause | Measured | Rule | Holds |
|---|---|---|---|
| ΔExpR = mean(R_event − mean R_null) | -0.3660R | ≥ +0.10R | **no** |
| lower 95% bound, week-clustered bootstrap | -0.4261R (upper -0.3036R) | > 0 | **no** |
| years with mean(d) > 0 | 0 of 9 | ≥ 7 | **no** |
| kept events N | 3612 | ≥ 300 | yes |

One-sided bootstrap p (share of resamples ≤ 0): 1.0000. N < 300 is `SCREEN-UNDERPOWERED` whatever the other clauses say.

## Both arms

Mean R_event +0.0727R; mean R_null (each event's null mean, averaged) +0.4386R. Both after costs.

| Exit | event arm | null arm |
|---|---|---|
| gap_stop | 344 (9.5%) | 4587 (6.8%) |
| gap_target | 191 (5.3%) | 4398 (6.5%) |
| stop | 1884 (52.2%) | 28852 (42.8%) |
| target | 1168 (32.3%) | 29076 (43.2%) |
| timeout | 25 (0.7%) | 433 (0.6%) |

## Per year

| Year | N | mean(d) |
|---|---|---|
| 2011 | 288 | -0.4358R |
| 2012 | 406 | -0.4413R |
| 2013 | 436 | -0.4418R |
| 2014 | 434 | -0.3054R |
| 2015 | 319 | -0.2576R |
| 2016 | 440 | -0.3133R |
| 2017 | 452 | -0.2910R |
| 2018 | 441 | -0.4340R |
| 2019 | 396 | -0.3763R |

## Forward drift (reported, never gating)

Mean excess forward return in ATR14 units from the signal close, event minus its matched null.

| h (bars) | events | mean excess (ATR) |
|---|---|---|
| 5 | 3612 | -0.3876 |
| 10 | 3612 | -0.6115 |
| 20 | 3612 | -0.7790 |
| 60 | 3612 | -0.8421 |

Spearman rank correlation, raw event indicator vs h-bar forward return, member and warm bars pooled across tickers per year:

| Year | h=5 | h=10 | h=20 | h=60 |
|---|---|---|---|---|
| 2011 | -0.0036 | -0.0091 | -0.0143 | -0.0094 |
| 2012 | -0.0078 | +0.0012 | -0.0033 | -0.0084 |
| 2013 | -0.0070 | -0.0047 | -0.0104 | -0.0083 |
| 2014 | -0.0020 | -0.0029 | -0.0009 | -0.0040 |
| 2015 | -0.0088 | -0.0005 | +0.0022 | +0.0008 |
| 2016 | -0.0031 | -0.0027 | -0.0027 | -0.0035 |
| 2017 | +0.0029 | -0.0033 | -0.0013 | -0.0008 |
| 2018 | -0.0067 | -0.0116 | -0.0121 | -0.0067 |
| 2019 | +0.0022 | +0.0044 | -0.0067 | -0.0001 |
