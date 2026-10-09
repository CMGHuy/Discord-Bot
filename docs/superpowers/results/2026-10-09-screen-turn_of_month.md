# v140 screen: `turn_of_month` -> SCREEN-FAIL

**Ledger id:** `screen-turn_of_month` (instrument `screen-v1`); BH q = 1.0000 across the ledger (reported, never gating).

**Run:** 2026-10-09; window 2010-01-01..2019-12-31; events count from 2011-01-01 (earlier bars only prime the indicators); the year rule is 7 of 9 calendar years (2011-2019); `python scripts/backtest/screen_idea.py --idea turn_of_month`; null K = 20, seed 42 per (idea, ticker); bootstrap 10,000 week resamples, seed 42.

**Trigger:** t is the last trading day of its calendar month (ticker's own bar dates) (Ariel (1987); Lakonishok & Smidt (1988)); params day=last trading day of the calendar month; time cap 4 bars; long only.

**Trade:** entry next open; stop 1.5 x ATR14; target 3.0 x ATR14; a gap through either level fills at the open; stop first on a bar touching both; costs 5.0 bps a side + 0.0200R commission.

**Spec:** `docs/superpowers/specs/2026-10-08-v140-idea-screen-design.md`

## Universe and counters

| | count |
|---|---|
| point-in-time S&P 500 members in the window | 719 |
| cached and screened | 506 |
| missing from the cache (survivorship that remains) | 213 |
| cached but empty inside the window | 14 |
| raw events | 55966 |
| `dropped_nonmember` | 11906 |
| `dropped_warmup` | 4106 |
| `dropped_window` | 0 |
| `skipped_overlap` | 0 |
| `dropped_no_match` | 1605 |
| **kept events (N)** | **38349** |

PIT members missing from the cache: AABA, ABC, ABMD, ACS, ADS, AET, AGN, AKS, ALTR, ALXN, ANDV, ANRZQ, ANSS, ANTM, APC, APOL, ARG, ARNC, ATGE, ATVI, AVB, AVP, AYE, BBBY, BCR, BDK, BHGE, BIG, BJS, BK, BLL, BMC, BMS, BNI, BRCM, BTUUQ, BXLT, CA, CAM, CBE, CBS, CCE, CELG, CEPH, CERN, CFN, CHK, CMA, CMCSK, COG, COL, COV, CPGX, CSRA, CTL, CTXS, CVC, CVH, CXO, DF, DFS, DISCA, DISCK, DISH, DNB, DNR, DO, DRE, DTV, DWDP, EA, EKDKQ, ENDP, EQR, ESRX, ESV, ETFC, EVHC, FBHS, FDO, FII, FL, FLIR, FLT, FRC, FRX, FTR, GAS, GGP, GMCR, GPS, HAR, HBI, HCBK, HCP, HES, HFC, HNZ, HOLX, HOT, HRS, HSH, HSP, IGT, IPG, JCP, JEC, JNPR, JNS, JOY, JWN, K, KORS, KRFT, KSU, LEG, LIFE, LLL, LLTC, LM, LO, LSI, LVLT, LXK, MDP, MEE, MFE, MHS, MIL, MJN, MMC, MNK, MOLX, MON, MRO, MWV, MWW, MXIM, MYL, NBL, NFX, NLOK, NLSN, NOVL, NSM, NVLS, NYX, ODP, PBCT, PBG, PCP, PDCO, PEAK, PETM, PGN, PKI, PLL, POM, PTV, PX, PXD, Q, QEP, QLGC, RAI, RDC, RE, RHT, RRD, RSHCQ, RTN, RX, SCG, SEE, SIAL, SIVB, SNI, SPLS, SRCL, STJ, STR, SUNEQ, SVU, SWN, SWY, SYMC, TEG, TGNA, TIE, TIF, TLAB, TMK, TSS, TWC, TWTR, TWX, UTX, VAR, VIAB, VIAC, WBA, WCG, WFM, WIN, WLTW, WPX, WRK, WYND, X, XEC, XL, XLNX, XTO.

## Verdict: SCREEN-FAIL

| Clause | Measured | Rule | Holds |
|---|---|---|---|
| ΔExpR = mean(R_event − mean R_null) | -0.0453R | ≥ +0.10R | **no** |
| lower 95% bound, week-clustered bootstrap | -0.1271R (upper +0.0362R) | > 0 | **no** |
| years with mean(d) > 0 | 1 of 9 | ≥ 7 | **no** |
| kept events N | 38349 | ≥ 300 | yes |

One-sided bootstrap p (share of resamples ≤ 0): 0.8577. N < 300 is `SCREEN-UNDERPOWERED` whatever the other clauses say.

## Both arms

Mean R_event -0.0495R; mean R_null (each event's null mean, averaged) -0.0042R. Both after costs.

| Exit | event arm | null arm |
|---|---|---|
| gap_stop | 1380 (3.6%) | 17562 (2.5%) |
| gap_target | 163 (0.4%) | 3426 (0.5%) |
| stop | 9409 (24.5%) | 134831 (19.3%) |
| target | 1217 (3.2%) | 19252 (2.8%) |
| timeout | 26180 (68.3%) | 524238 (75.0%) |

## Per year

| Year | N | mean(d) |
|---|---|---|
| 2011 | 3498 | -0.1293R |
| 2012 | 3891 | -0.0117R |
| 2013 | 4081 | -0.0329R |
| 2014 | 4064 | -0.0538R |
| 2015 | 4200 | +0.0053R |
| 2016 | 4404 | -0.0616R |
| 2017 | 4644 | -0.1320R |
| 2018 | 4721 | -0.0013R |
| 2019 | 4846 | -0.0040R |

## Forward drift (reported, never gating)

Mean excess forward return in ATR14 units from the signal close, event minus its matched null.

| h (bars) | events | mean excess (ATR) |
|---|---|---|
| 5 | 38349 | -0.0414 |
| 10 | 38349 | -0.1184 |
| 20 | 38349 | -0.0613 |
| 60 | 37528 | -0.0811 |

Spearman rank correlation, raw event indicator vs h-bar forward return, member and warm bars pooled across tickers per year:

| Year | h=5 | h=10 | h=20 | h=60 |
|---|---|---|---|---|
| 2011 | -0.0323 | -0.0445 | -0.0297 | -0.0104 |
| 2012 | +0.0013 | -0.0102 | +0.0053 | -0.0029 |
| 2013 | +0.0036 | +0.0426 | -0.0052 | -0.0034 |
| 2014 | -0.0172 | -0.0579 | +0.0023 | +0.0071 |
| 2015 | -0.0108 | -0.0006 | +0.0158 | +0.0023 |
| 2016 | +0.0131 | -0.0114 | -0.0097 | +0.0001 |
| 2017 | -0.0011 | +0.0022 | +0.0032 | -0.0089 |
| 2018 | +0.0135 | -0.0025 | -0.0075 | +0.0045 |
| 2019 | -0.0126 | -0.0009 | +0.0002 | -0.0008 |
