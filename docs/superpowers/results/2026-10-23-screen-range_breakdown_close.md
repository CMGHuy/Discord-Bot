# v140 screen: `range_breakdown_close` -> SCREEN-FAIL
n**Definition commit:** 51a1335818f76506268fc4769d09d9b42be8e978

**Ledger id:** `screen-range_breakdown_close` (instrument `screen-v1`); BH q = 1.0000 across the ledger (reported, never gating).

**Run:** 2026-10-23; window 2010-01-01..2019-12-31; events count from 2011-01-01 (earlier bars only prime the indicators); the year rule is 7 of 9 calendar years (2011-2019); `python scripts/backtest/screen_idea.py --idea range_breakdown_close`; null K = 20, seed 42 per (idea, ticker); bootstrap 10,000 week resamples, seed 42.

**Trigger:** 30-bar range (R - S <= 5 ATR14[t-1], two touches of each side >= 5 bars apart) in a falling SMA50 with the prior close below it; close[t] < S (short, next open) (Schwab, "The Ins and Outs of a Swing Trade" (2025-03-07), downswing breakout); params window=30, height_atr=5.0, touch_atr=0.25, touch_span=5, sma=50, sma_lag=10, warmup=61, trigger=close[t] < S; time cap 20 bars; short only.

**Trade:** short; entry next open (sell); stop 1.5 x ATR14 above; target 3.0 x ATR14 below; a gap through either level fills at the open; stop first on a bar touching both; borrow 0.5% a year on calendar days held; costs 5.0 bps a side + 0.0200R commission.

**Spec:** `docs/superpowers/specs/implemented/2026-10-08-v140-idea-screen-design.md`

## Universe and counters

| | count |
|---|---|
| point-in-time S&P 500 members in the window | 719 |
| cached and screened | 506 |
| missing from the cache (survivorship that remains) | 213 |
| cached but empty inside the window | 14 |
| raw events | 617 |
| `dropped_nonmember` | 117 |
| `dropped_warmup` | 26 |
| `dropped_window` | 0 |
| `skipped_overlap` | 11 |
| `dropped_no_match` | 37 |
| **kept events (N)** | **426** |

PIT members missing from the cache: AABA, ABC, ABMD, ACS, ADS, AET, AGN, AKS, ALTR, ALXN, ANDV, ANRZQ, ANSS, ANTM, APC, APOL, ARG, ARNC, ATGE, ATVI, AVB, AVP, AYE, BBBY, BCR, BDK, BHGE, BIG, BJS, BK, BLL, BMC, BMS, BNI, BRCM, BTUUQ, BXLT, CA, CAM, CBE, CBS, CCE, CELG, CEPH, CERN, CFN, CHK, CMA, CMCSK, COG, COL, COV, CPGX, CSRA, CTL, CTXS, CVC, CVH, CXO, DF, DFS, DISCA, DISCK, DISH, DNB, DNR, DO, DRE, DTV, DWDP, EA, EKDKQ, ENDP, EQR, ESRX, ESV, ETFC, EVHC, FBHS, FDO, FII, FL, FLIR, FLT, FRC, FRX, FTR, GAS, GGP, GMCR, GPS, HAR, HBI, HCBK, HCP, HES, HFC, HNZ, HOLX, HOT, HRS, HSH, HSP, IGT, IPG, JCP, JEC, JNPR, JNS, JOY, JWN, K, KORS, KRFT, KSU, LEG, LIFE, LLL, LLTC, LM, LO, LSI, LVLT, LXK, MDP, MEE, MFE, MHS, MIL, MJN, MMC, MNK, MOLX, MON, MRO, MWV, MWW, MXIM, MYL, NBL, NFX, NLOK, NLSN, NOVL, NSM, NVLS, NYX, ODP, PBCT, PBG, PCP, PDCO, PEAK, PETM, PGN, PKI, PLL, POM, PTV, PX, PXD, Q, QEP, QLGC, RAI, RDC, RE, RHT, RRD, RSHCQ, RTN, RX, SCG, SEE, SIAL, SIVB, SNI, SPLS, SRCL, STJ, STR, SUNEQ, SVU, SWN, SWY, SYMC, TEG, TGNA, TIE, TIF, TLAB, TMK, TSS, TWC, TWTR, TWX, UTX, VAR, VIAB, VIAC, WBA, WCG, WFM, WIN, WLTW, WPX, WRK, WYND, X, XEC, XL, XLNX, XTO.

## Verdict: SCREEN-FAIL

| Clause | Measured | Rule | Holds |
|---|---|---|---|
| ΔExpR = mean(R_event − mean R_null) | -0.3210R | ≥ +0.10R | **no** |
| lower 95% bound, week-clustered bootstrap | -0.4964R (upper -0.1363R) | > 0 | **no** |
| years with mean(d) > 0 | 1 of 9 | ≥ 7 | **no** |
| kept events N | 426 | ≥ 300 | yes |

One-sided bootstrap p (share of resamples ≤ 0): 0.9996. N < 300 is `SCREEN-UNDERPOWERED` whatever the other clauses say.

## Both arms

Mean R_event -0.1158R; mean R_null (each event's null mean, averaged) +0.2052R. Both after costs.

| Exit | event arm | null arm |
|---|---|---|
| gap_stop | 39 (9.2%) | 489 (6.5%) |
| gap_target | 18 (4.2%) | 391 (5.2%) |
| stop | 222 (52.1%) | 3309 (44.2%) |
| target | 88 (20.7%) | 2277 (30.4%) |
| timeout | 59 (13.8%) | 1022 (13.6%) |

## Per year

| Year | N | mean(d) |
|---|---|---|
| 2011 | 60 | -0.4168R |
| 2012 | 35 | -0.2447R |
| 2013 | 15 | -0.5484R |
| 2014 | 45 | -0.1696R |
| 2015 | 53 | -0.2867R |
| 2016 | 58 | -0.4961R |
| 2017 | 34 | -0.3911R |
| 2018 | 89 | -0.3599R |
| 2019 | 37 | +0.0542R |

## Forward drift (reported, never gating)

Mean excess forward return in ATR14 units from the signal close, event minus its matched null.

| h (bars) | events | mean excess (ATR) |
|---|---|---|
| 5 | 426 | -0.4139 |
| 10 | 426 | -0.5744 |
| 20 | 426 | -0.8762 |
| 60 | 422 | -1.0223 |

Spearman rank correlation, raw event indicator vs h-bar forward return, member and warm bars pooled across tickers per year:

| Year | h=5 | h=10 | h=20 | h=60 |
|---|---|---|---|---|
| 2011 | -0.0027 | -0.0013 | -0.0060 | -0.0031 |
| 2012 | -0.0095 | -0.0041 | -0.0060 | -0.0082 |
| 2013 | -0.0013 | -0.0012 | -0.0026 | -0.0010 |
| 2014 | +0.0002 | +0.0040 | -0.0021 | -0.0074 |
| 2015 | -0.0059 | -0.0017 | +0.0002 | -0.0031 |
| 2016 | +0.0003 | -0.0041 | -0.0023 | -0.0053 |
| 2017 | +0.0023 | +0.0020 | +0.0046 | +0.0037 |
| 2018 | +0.0043 | -0.0014 | -0.0097 | -0.0055 |
| 2019 | +0.0032 | +0.0062 | +0.0048 | +0.0024 |

## Short-side blocks (descriptive, never gating)

**Event overlap** with `range_breakdown_stop` (raw event bars on member, warm bars): 474 of 474 `range_breakdown_close` bars (100.0%) are also `range_breakdown_stop` bars; 474 of 842 `range_breakdown_stop` bars (56.3%) are also `range_breakdown_close` bars. Nested ideas are two looks at one hypothesis: read both results docs together (family of two, BH q above).

**Trend-only control** (`control_events`: the idea's trend and first-break clauses, no range clauses; same race, same matched null): N = 7272, ΔExpR -0.4082R, 95% week-clustered interval -0.5289R to -0.2690R. The idea's ΔExpR minus the control's: +0.0872R. A pass whose ΔExpR is not clearly above the control is not credited to the range.

**SPY regime split** (SPY close vs its 200-day average at the last close before entry):

| SPY | N | ΔExpR |
|---|---|---|
| above its 200-day average | 331 | -0.3171R |
| below its 200-day average | 95 | -0.3342R |

Events with no SPY average before entry: 0.
