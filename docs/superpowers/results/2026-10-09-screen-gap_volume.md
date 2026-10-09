# v140 screen: `gap_volume` -> SCREEN-FAIL

**Ledger id:** `screen-gap_volume` (instrument `screen-v1`); BH q = 1.0000 across the ledger (reported, never gating).

**Run:** 2026-10-09; window 2010-01-01..2019-12-31; events count from 2011-01-01 (earlier bars only prime the indicators); the year rule is 7 of 9 calendar years (2011-2019); `python scripts/backtest/screen_idea.py --idea gap_volume`; null K = 20, seed 42 per (idea, ticker); bootstrap 10,000 week resamples, seed 42.

**Trigger:** open >= prior close + 1.0 x prior ATR14, volume >= 2 x the 50-bar mean volume ending the prior bar, close >= open (earnings/news gap drift; volume as the news proxy); params gap_atr=1.0, atr_n=14, volume_mult=2.0, volume_window=50; time cap 20 bars; long only.

**Trade:** entry next open; stop 1.5 x ATR14; target 3.0 x ATR14; a gap through either level fills at the open; stop first on a bar touching both; costs 5.0 bps a side + 0.0200R commission.

**Spec:** `docs/superpowers/specs/implemented/2026-10-08-v140-idea-screen-design.md`

## Universe and counters

| | count |
|---|---|
| point-in-time S&P 500 members in the window | 719 |
| cached and screened | 506 |
| missing from the cache (survivorship that remains) | 213 |
| cached but empty inside the window | 14 |
| raw events | 2924 |
| `dropped_nonmember` | 817 |
| `dropped_warmup` | 141 |
| `dropped_window` | 16 |
| `skipped_overlap` | 13 |
| `dropped_no_match` | 103 |
| **kept events (N)** | **1834** |

PIT members missing from the cache: AABA, ABC, ABMD, ACS, ADS, AET, AGN, AKS, ALTR, ALXN, ANDV, ANRZQ, ANSS, ANTM, APC, APOL, ARG, ARNC, ATGE, ATVI, AVB, AVP, AYE, BBBY, BCR, BDK, BHGE, BIG, BJS, BK, BLL, BMC, BMS, BNI, BRCM, BTUUQ, BXLT, CA, CAM, CBE, CBS, CCE, CELG, CEPH, CERN, CFN, CHK, CMA, CMCSK, COG, COL, COV, CPGX, CSRA, CTL, CTXS, CVC, CVH, CXO, DF, DFS, DISCA, DISCK, DISH, DNB, DNR, DO, DRE, DTV, DWDP, EA, EKDKQ, ENDP, EQR, ESRX, ESV, ETFC, EVHC, FBHS, FDO, FII, FL, FLIR, FLT, FRC, FRX, FTR, GAS, GGP, GMCR, GPS, HAR, HBI, HCBK, HCP, HES, HFC, HNZ, HOLX, HOT, HRS, HSH, HSP, IGT, IPG, JCP, JEC, JNPR, JNS, JOY, JWN, K, KORS, KRFT, KSU, LEG, LIFE, LLL, LLTC, LM, LO, LSI, LVLT, LXK, MDP, MEE, MFE, MHS, MIL, MJN, MMC, MNK, MOLX, MON, MRO, MWV, MWW, MXIM, MYL, NBL, NFX, NLOK, NLSN, NOVL, NSM, NVLS, NYX, ODP, PBCT, PBG, PCP, PDCO, PEAK, PETM, PGN, PKI, PLL, POM, PTV, PX, PXD, Q, QEP, QLGC, RAI, RDC, RE, RHT, RRD, RSHCQ, RTN, RX, SCG, SEE, SIAL, SIVB, SNI, SPLS, SRCL, STJ, STR, SUNEQ, SVU, SWN, SWY, SYMC, TEG, TGNA, TIE, TIF, TLAB, TMK, TSS, TWC, TWTR, TWX, UTX, VAR, VIAB, VIAC, WBA, WCG, WFM, WIN, WLTW, WPX, WRK, WYND, X, XEC, XL, XLNX, XTO.

## Verdict: SCREEN-FAIL

| Clause | Measured | Rule | Holds |
|---|---|---|---|
| ΔExpR = mean(R_event − mean R_null) | -0.4639R | ≥ +0.10R | **no** |
| lower 95% bound, week-clustered bootstrap | -0.5505R (upper -0.3787R) | > 0 | **no** |
| years with mean(d) > 0 | 0 of 9 | ≥ 7 | **no** |
| kept events N | 1834 | ≥ 300 | yes |

One-sided bootstrap p (share of resamples ≤ 0): 1.0000. N < 300 is `SCREEN-UNDERPOWERED` whatever the other clauses say.

## Both arms

Mean R_event +0.1151R; mean R_null (each event's null mean, averaged) +0.5790R. Both after costs.

| Exit | event arm | null arm |
|---|---|---|
| gap_stop | 115 (6.3%) | 1590 (4.8%) |
| gap_target | 52 (2.8%) | 4316 (13.1%) |
| stop | 771 (42.0%) | 11767 (35.8%) |
| target | 407 (22.2%) | 10439 (31.8%) |
| timeout | 489 (26.7%) | 4766 (14.5%) |

## Per year

| Year | N | mean(d) |
|---|---|---|
| 2011 | 164 | -0.5879R |
| 2012 | 175 | -0.5326R |
| 2013 | 225 | -0.3082R |
| 2014 | 186 | -0.2808R |
| 2015 | 209 | -0.5574R |
| 2016 | 214 | -0.4170R |
| 2017 | 233 | -0.5426R |
| 2018 | 204 | -0.4433R |
| 2019 | 224 | -0.5226R |

## Forward drift (reported, never gating)

Mean excess forward return in ATR14 units from the signal close, event minus its matched null.

| h (bars) | events | mean excess (ATR) |
|---|---|---|
| 5 | 1834 | -0.6950 |
| 10 | 1834 | -1.2205 |
| 20 | 1834 | -1.6910 |
| 60 | 1785 | -1.8052 |

Spearman rank correlation, raw event indicator vs h-bar forward return, member and warm bars pooled across tickers per year:

| Year | h=5 | h=10 | h=20 | h=60 |
|---|---|---|---|---|
| 2011 | -0.0030 | -0.0025 | -0.0066 | -0.0015 |
| 2012 | +0.0024 | +0.0008 | -0.0019 | -0.0029 |
| 2013 | +0.0007 | +0.0010 | -0.0041 | -0.0068 |
| 2014 | -0.0017 | +0.0004 | +0.0004 | -0.0089 |
| 2015 | +0.0003 | -0.0008 | +0.0004 | -0.0006 |
| 2016 | +0.0049 | +0.0044 | +0.0041 | -0.0024 |
| 2017 | -0.0036 | -0.0023 | -0.0032 | +0.0055 |
| 2018 | -0.0019 | -0.0024 | +0.0012 | -0.0096 |
| 2019 | -0.0082 | -0.0082 | -0.0096 | -0.0118 |
