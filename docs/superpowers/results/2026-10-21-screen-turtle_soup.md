# v140 screen: `turtle_soup` -> SCREEN-PASS

**Ledger id:** `screen-turtle_soup` (instrument `screen-v1`); BH q = 0.0000 across the ledger (reported, never gating).

**Run:** 2026-10-21; window 2010-01-01..2019-12-31; events count from 2011-01-01 (earlier bars only prime the indicators); the year rule is 7 of 9 calendar years (2011-2019); `python scripts/backtest/screen_idea.py --idea turtle_soup`; null K = 20, seed 42 per (idea, ticker); bootstrap 10,000 week resamples, seed 42.

**Trigger:** low < the prior 20-bar low, that low set >= 4 bars before t, close > that low (close-confirmed reclaim) (Connors & Raschke, Street Smarts (1995), Turtle Soup); params channel=20, min_age=4; time cap 10 bars; long only.

**Trade:** entry next open; stop 1.5 x ATR14; target 3.0 x ATR14; a gap through either level fills at the open; stop first on a bar touching both; costs 5.0 bps a side + 0.0200R commission.

**Spec:** `docs/superpowers/specs/implemented/2026-10-08-v140-idea-screen-design.md`

## Universe and counters

| | count |
|---|---|
| point-in-time S&P 500 members in the window | 719 |
| cached and screened | 506 |
| missing from the cache (survivorship that remains) | 213 |
| cached but empty inside the window | 14 |
| raw events | 16119 |
| `dropped_nonmember` | 3379 |
| `dropped_warmup` | 1125 |
| `dropped_window` | 15 |
| `skipped_overlap` | 804 |
| `dropped_no_match` | 358 |
| **kept events (N)** | **10438** |

PIT members missing from the cache: AABA, ABC, ABMD, ACS, ADS, AET, AGN, AKS, ALTR, ALXN, ANDV, ANRZQ, ANSS, ANTM, APC, APOL, ARG, ARNC, ATGE, ATVI, AVB, AVP, AYE, BBBY, BCR, BDK, BHGE, BIG, BJS, BK, BLL, BMC, BMS, BNI, BRCM, BTUUQ, BXLT, CA, CAM, CBE, CBS, CCE, CELG, CEPH, CERN, CFN, CHK, CMA, CMCSK, COG, COL, COV, CPGX, CSRA, CTL, CTXS, CVC, CVH, CXO, DF, DFS, DISCA, DISCK, DISH, DNB, DNR, DO, DRE, DTV, DWDP, EA, EKDKQ, ENDP, EQR, ESRX, ESV, ETFC, EVHC, FBHS, FDO, FII, FL, FLIR, FLT, FRC, FRX, FTR, GAS, GGP, GMCR, GPS, HAR, HBI, HCBK, HCP, HES, HFC, HNZ, HOLX, HOT, HRS, HSH, HSP, IGT, IPG, JCP, JEC, JNPR, JNS, JOY, JWN, K, KORS, KRFT, KSU, LEG, LIFE, LLL, LLTC, LM, LO, LSI, LVLT, LXK, MDP, MEE, MFE, MHS, MIL, MJN, MMC, MNK, MOLX, MON, MRO, MWV, MWW, MXIM, MYL, NBL, NFX, NLOK, NLSN, NOVL, NSM, NVLS, NYX, ODP, PBCT, PBG, PCP, PDCO, PEAK, PETM, PGN, PKI, PLL, POM, PTV, PX, PXD, Q, QEP, QLGC, RAI, RDC, RE, RHT, RRD, RSHCQ, RTN, RX, SCG, SEE, SIAL, SIVB, SNI, SPLS, SRCL, STJ, STR, SUNEQ, SVU, SWN, SWY, SYMC, TEG, TGNA, TIE, TIF, TLAB, TMK, TSS, TWC, TWTR, TWX, UTX, VAR, VIAB, VIAC, WBA, WCG, WFM, WIN, WLTW, WPX, WRK, WYND, X, XEC, XL, XLNX, XTO.

## Verdict: SCREEN-PASS

| Clause | Measured | Rule | Holds |
|---|---|---|---|
| ΔExpR = mean(R_event − mean R_null) | +0.3155R | ≥ +0.10R | yes |
| lower 95% bound, week-clustered bootstrap | +0.2536R (upper +0.3805R) | > 0 | yes |
| years with mean(d) > 0 | 9 of 9 | ≥ 7 | yes |
| kept events N | 10438 | ≥ 300 | yes |

One-sided bootstrap p (share of resamples ≤ 0): 0.0000. N < 300 is `SCREEN-UNDERPOWERED` whatever the other clauses say.

## Both arms

Mean R_event +0.0699R; mean R_null (each event's null mean, averaged) -0.2456R. Both after costs.

| Exit | event arm | null arm |
|---|---|---|
| gap_stop | 535 (5.1%) | 13597 (7.3%) |
| gap_target | 240 (2.3%) | 2868 (1.5%) |
| stop | 3969 (38.0%) | 87658 (46.8%) |
| target | 1602 (15.3%) | 17651 (9.4%) |
| timeout | 4092 (39.2%) | 65462 (35.0%) |

## Per year

| Year | N | mean(d) |
|---|---|---|
| 2011 | 1143 | +0.4422R |
| 2012 | 1011 | +0.3876R |
| 2013 | 932 | +0.3766R |
| 2014 | 1008 | +0.2382R |
| 2015 | 1310 | +0.3309R |
| 2016 | 1276 | +0.2501R |
| 2017 | 1213 | +0.3362R |
| 2018 | 1440 | +0.1636R |
| 2019 | 1105 | +0.3701R |

## Forward drift (reported, never gating)

Mean excess forward return in ATR14 units from the signal close, event minus its matched null.

| h (bars) | events | mean excess (ATR) |
|---|---|---|
| 5 | 10438 | +0.3583 |
| 10 | 10438 | +0.5477 |
| 20 | 10360 | +0.6902 |
| 60 | 10213 | +0.6447 |

Spearman rank correlation, raw event indicator vs h-bar forward return, member and warm bars pooled across tickers per year:

| Year | h=5 | h=10 | h=20 | h=60 |
|---|---|---|---|---|
| 2011 | +0.0199 | +0.0159 | +0.0165 | -0.0014 |
| 2012 | +0.0083 | -0.0030 | -0.0055 | +0.0072 |
| 2013 | +0.0106 | +0.0051 | +0.0149 | +0.0079 |
| 2014 | -0.0095 | -0.0025 | +0.0093 | +0.0033 |
| 2015 | +0.0235 | +0.0192 | +0.0068 | +0.0025 |
| 2016 | +0.0025 | -0.0014 | +0.0045 | +0.0109 |
| 2017 | -0.0042 | +0.0015 | -0.0003 | -0.0065 |
| 2018 | -0.0092 | +0.0020 | +0.0062 | +0.0061 |
| 2019 | +0.0042 | +0.0031 | +0.0023 | -0.0042 |
