# v140 screen: `uptrend_pullback` -> SCREEN-PASS

**Ledger id:** `screen-uptrend_pullback` (instrument `screen-v1`); BH q = 0.0000 across the ledger (reported, never gating).

**Run:** 2026-10-08; window 2010-01-01..2019-12-31; events count from 2011-01-01 (earlier bars only prime the indicators); the year rule is 7 of 9 calendar years (2011-2019); `python scripts/backtest/screen_idea.py --idea uptrend_pullback`; null K = 20, seed 42 per (idea, ticker); bootstrap 10,000 week resamples, seed 42.

**Trigger:** close > SMA200 and Wilder RSI(2) < 10 (Connors & Alvarez (2008)); params trend_sma=200, rsi_n=2, rsi_below=10; time cap 10 bars; long only.

**Trade:** entry next open; stop 1.5 x ATR14; target 3.0 x ATR14; a gap through either level fills at the open; stop first on a bar touching both; costs 5.0 bps a side + 0.0200R commission.

**Spec:** `docs/superpowers/specs/implemented/2026-10-08-v140-idea-screen-design.md`

## Universe and counters

| | count |
|---|---|
| point-in-time S&P 500 members in the window | 719 |
| cached and screened | 506 |
| missing from the cache (survivorship that remains) | 213 |
| cached but empty inside the window | 14 |
| raw events | 63147 |
| `dropped_nonmember` | 13718 |
| `dropped_warmup` | 940 |
| `dropped_window` | 132 |
| `skipped_overlap` | 21043 |
| `dropped_no_match` | 402 |
| **kept events (N)** | **26912** |

PIT members missing from the cache: AABA, ABC, ABMD, ACS, ADS, AET, AGN, AKS, ALTR, ALXN, ANDV, ANRZQ, ANSS, ANTM, APC, APOL, ARG, ARNC, ATGE, ATVI, AVB, AVP, AYE, BBBY, BCR, BDK, BHGE, BIG, BJS, BK, BLL, BMC, BMS, BNI, BRCM, BTUUQ, BXLT, CA, CAM, CBE, CBS, CCE, CELG, CEPH, CERN, CFN, CHK, CMA, CMCSK, COG, COL, COV, CPGX, CSRA, CTL, CTXS, CVC, CVH, CXO, DF, DFS, DISCA, DISCK, DISH, DNB, DNR, DO, DRE, DTV, DWDP, EA, EKDKQ, ENDP, EQR, ESRX, ESV, ETFC, EVHC, FBHS, FDO, FII, FL, FLIR, FLT, FRC, FRX, FTR, GAS, GGP, GMCR, GPS, HAR, HBI, HCBK, HCP, HES, HFC, HNZ, HOLX, HOT, HRS, HSH, HSP, IGT, IPG, JCP, JEC, JNPR, JNS, JOY, JWN, K, KORS, KRFT, KSU, LEG, LIFE, LLL, LLTC, LM, LO, LSI, LVLT, LXK, MDP, MEE, MFE, MHS, MIL, MJN, MMC, MNK, MOLX, MON, MRO, MWV, MWW, MXIM, MYL, NBL, NFX, NLOK, NLSN, NOVL, NSM, NVLS, NYX, ODP, PBCT, PBG, PCP, PDCO, PEAK, PETM, PGN, PKI, PLL, POM, PTV, PX, PXD, Q, QEP, QLGC, RAI, RDC, RE, RHT, RRD, RSHCQ, RTN, RX, SCG, SEE, SIAL, SIVB, SNI, SPLS, SRCL, STJ, STR, SUNEQ, SVU, SWN, SWY, SYMC, TEG, TGNA, TIE, TIF, TLAB, TMK, TSS, TWC, TWTR, TWX, UTX, VAR, VIAB, VIAC, WBA, WCG, WFM, WIN, WLTW, WPX, WRK, WYND, X, XEC, XL, XLNX, XTO.

## Verdict: SCREEN-PASS

| Clause | Measured | Rule | Holds |
|---|---|---|---|
| ΔExpR = mean(R_event − mean R_null) | +0.3672R | ≥ +0.10R | yes |
| lower 95% bound, week-clustered bootstrap | +0.3107R (upper +0.4261R) | > 0 | yes |
| years with mean(d) > 0 | 9 of 9 | ≥ 7 | yes |
| kept events N | 26912 | ≥ 300 | yes |

One-sided bootstrap p (share of resamples ≤ 0): 0.0000. N < 300 is `SCREEN-UNDERPOWERED` whatever the other clauses say.

## Both arms

Mean R_event +0.0780R; mean R_null (each event's null mean, averaged) -0.2892R. Both after costs.

| Exit | event arm | null arm |
|---|---|---|
| gap_stop | 1302 (4.8%) | 30167 (6.6%) |
| gap_target | 713 (2.6%) | 6856 (1.5%) |
| stop | 10281 (38.2%) | 219994 (47.9%) |
| target | 4187 (15.6%) | 44799 (9.8%) |
| timeout | 10429 (38.8%) | 157542 (34.3%) |

## Per year

| Year | N | mean(d) |
|---|---|---|
| 2011 | 2642 | +0.3579R |
| 2012 | 3048 | +0.4039R |
| 2013 | 3249 | +0.3628R |
| 2014 | 3321 | +0.3754R |
| 2015 | 2735 | +0.3796R |
| 2016 | 2691 | +0.3718R |
| 2017 | 3222 | +0.3853R |
| 2018 | 3199 | +0.2663R |
| 2019 | 2805 | +0.4090R |

## Forward drift (reported, never gating)

Mean excess forward return in ATR14 units from the signal close, event minus its matched null.

| h (bars) | events | mean excess (ATR) |
|---|---|---|
| 5 | 26912 | +0.5399 |
| 10 | 26912 | +0.7920 |
| 20 | 26740 | +1.0791 |
| 60 | 26282 | +1.0855 |

Spearman rank correlation, raw event indicator vs h-bar forward return, member and warm bars pooled across tickers per year:

| Year | h=5 | h=10 | h=20 | h=60 |
|---|---|---|---|---|
| 2011 | +0.0068 | +0.0221 | +0.0083 | -0.0280 |
| 2012 | +0.0452 | -0.0146 | -0.0105 | -0.0014 |
| 2013 | +0.0116 | -0.0027 | +0.0115 | +0.0159 |
| 2014 | +0.0136 | -0.0012 | -0.0004 | +0.0118 |
| 2015 | +0.0365 | +0.0467 | +0.0347 | +0.0309 |
| 2016 | -0.0009 | -0.0170 | +0.0018 | +0.0016 |
| 2017 | +0.0012 | +0.0021 | +0.0044 | +0.0145 |
| 2018 | -0.0200 | +0.0003 | +0.0137 | -0.0067 |
| 2019 | +0.0139 | -0.0000 | -0.0025 | +0.0098 |
