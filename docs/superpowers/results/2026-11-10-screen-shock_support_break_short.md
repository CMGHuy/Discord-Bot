# v140 screen: `shock_support_break_short` -> SCREEN-FAIL

**Definition commit:** fb6d5a62ce9a28b938ad76a1e0a28cd616b21721

**Ledger id:** `screen-shock_support_break_short` (instrument `screen-v1`); BH q = 1.0000 across the ledger (reported, never gating).

**Run:** 2026-11-10; window 2010-01-01..2019-12-31; events count from 2011-01-01 (earlier bars only prime the indicators); the year rule is 7 of 9 calendar years (2011-2019); `python scripts/backtest/screen_idea.py --idea shock_support_break_short`; null K = 20, seed 42 per (idea, ticker); bootstrap 10,000 week resamples, seed 42.

**Trigger:** SHOCK_D on t (BREADTH_ATR1 >= 0.40 enters; <= 0.10 with ^VIX down releases) and close[t] < min(Low[t-20..t-1]), the first such close in the episode (short, next open) (v209 spec § Track 2 (frozen 2026-11-05): breadth-shock-conditioned breakdown shorts, after the 2026-11-05 session the long book lost 13.9R); params breadth=BREADTH_ATR1, vix=^VIX, enter=0.4, release=0.1, low_window=20, side=short; time cap 10 bars; short only.

**Trade:** short; entry next open (sell); stop 1.5 x ATR14 above; target 3.0 x ATR14 below; a gap through either level fills at the open; stop first on a bar touching both; borrow 0.5% a year on calendar days held; costs 5.0 bps a side + 0.0200R commission.

**Spec:** `docs/superpowers/specs/implemented/2026-10-08-v140-idea-screen-design.md`

## Universe and counters

| | count |
|---|---|
| point-in-time S&P 500 members in the window | 719 |
| cached and screened | 506 |
| missing from the cache (survivorship that remains) | 213 |
| cached but empty inside the window | 14 |
| raw events | 10946 |
| `dropped_nonmember` | 2109 |
| `dropped_warmup` | 881 |
| `dropped_window` | 0 |
| `skipped_overlap` | 911 |
| `dropped_no_match` | 500 |
| **kept events (N)** | **6545** |

PIT members missing from the cache: AABA, ABC, ABMD, ACS, ADS, AET, AGN, AKS, ALTR, ALXN, ANDV, ANRZQ, ANSS, ANTM, APC, APOL, ARG, ARNC, ATGE, ATVI, AVB, AVP, AYE, BBBY, BCR, BDK, BHGE, BIG, BJS, BK, BLL, BMC, BMS, BNI, BRCM, BTUUQ, BXLT, CA, CAM, CBE, CBS, CCE, CELG, CEPH, CERN, CFN, CHK, CMA, CMCSK, COG, COL, COV, CPGX, CSRA, CTL, CTXS, CVC, CVH, CXO, DF, DFS, DISCA, DISCK, DISH, DNB, DNR, DO, DRE, DTV, DWDP, EA, EKDKQ, ENDP, EQR, ESRX, ESV, ETFC, EVHC, FBHS, FDO, FII, FL, FLIR, FLT, FRC, FRX, FTR, GAS, GGP, GMCR, GPS, HAR, HBI, HCBK, HCP, HES, HFC, HNZ, HOLX, HOT, HRS, HSH, HSP, IGT, IPG, JCP, JEC, JNPR, JNS, JOY, JWN, K, KORS, KRFT, KSU, LEG, LIFE, LLL, LLTC, LM, LO, LSI, LVLT, LXK, MDP, MEE, MFE, MHS, MIL, MJN, MMC, MNK, MOLX, MON, MRO, MWV, MWW, MXIM, MYL, NBL, NFX, NLOK, NLSN, NOVL, NSM, NVLS, NYX, ODP, PBCT, PBG, PCP, PDCO, PEAK, PETM, PGN, PKI, PLL, POM, PTV, PX, PXD, Q, QEP, QLGC, RAI, RDC, RE, RHT, RRD, RSHCQ, RTN, RX, SCG, SEE, SIAL, SIVB, SNI, SPLS, SRCL, STJ, STR, SUNEQ, SVU, SWN, SWY, SYMC, TEG, TGNA, TIE, TIF, TLAB, TMK, TSS, TWC, TWTR, TWX, UTX, VAR, VIAB, VIAC, WBA, WCG, WFM, WIN, WLTW, WPX, WRK, WYND, X, XEC, XL, XLNX, XTO.

## Verdict: SCREEN-FAIL

| Clause | Measured | Rule | Holds |
|---|---|---|---|
| ΔExpR = mean(R_event − mean R_null) | -0.3131R | ≥ +0.10R | **no** |
| lower 95% bound, week-clustered bootstrap | -0.5259R (upper -0.0732R) | > 0 | **no** |
| years with mean(d) > 0 | 1 of 9 | ≥ 7 | **no** |
| kept events N | 6545 | ≥ 300 | yes |

One-sided bootstrap p (share of resamples ≤ 0): 0.9942. N < 300 is `SCREEN-UNDERPOWERED` whatever the other clauses say.

## Both arms

Mean R_event -0.1393R; mean R_null (each event's null mean, averaged) +0.1738R. Both after costs.

| Exit | event arm | null arm |
|---|---|---|
| gap_stop | 527 (8.1%) | 6268 (5.4%) |
| gap_target | 190 (2.9%) | 4356 (3.8%) |
| stop | 3058 (46.7%) | 40142 (34.8%) |
| target | 1067 (16.3%) | 24077 (20.9%) |
| timeout | 1703 (26.0%) | 40490 (35.1%) |

## Per year

| Year | N | mean(d) |
|---|---|---|
| 2011 | 910 | +0.1623R |
| 2012 | 475 | -0.2637R |
| 2013 | 479 | -0.6921R |
| 2014 | 1136 | -0.3911R |
| 2015 | 812 | -0.4983R |
| 2016 | 755 | -0.3981R |
| 2017 | 186 | -0.7180R |
| 2018 | 1121 | -0.2444R |
| 2019 | 671 | -0.2726R |

## Forward drift (reported, never gating)

Mean excess forward return in ATR14 units from the signal close, event minus its matched null.

| h (bars) | events | mean excess (ATR) |
|---|---|---|
| 5 | 6545 | -0.6582 |
| 10 | 6545 | -0.8297 |
| 20 | 6545 | -1.2526 |
| 60 | 6542 | -1.0687 |

Spearman rank correlation, raw event indicator vs h-bar forward return, member and warm bars pooled across tickers per year:

| Year | h=5 | h=10 | h=20 | h=60 |
|---|---|---|---|---|
| 2011 | +0.0479 | +0.0565 | +0.0082 | -0.0166 |
| 2012 | -0.0310 | -0.0285 | -0.0225 | -0.0216 |
| 2013 | -0.0237 | -0.0289 | -0.0362 | -0.0251 |
| 2014 | -0.0085 | -0.0351 | -0.0725 | -0.0419 |
| 2015 | -0.0520 | -0.0359 | -0.0324 | -0.0125 |
| 2016 | +0.0007 | -0.0232 | +0.0102 | -0.0151 |
| 2017 | -0.0113 | -0.0170 | -0.0179 | -0.0092 |
| 2018 | -0.0208 | -0.0048 | -0.0363 | +0.0004 |
| 2019 | -0.0182 | -0.0152 | -0.0292 | -0.0266 |

## Short-side blocks (descriptive, never gating)

**Event overlap** with `shock_failed_bounce_short` (raw event bars on member, warm bars): 3391 of 7956 `shock_support_break_short` bars (42.6%) are also `shock_failed_bounce_short` bars; 3391 of 9805 `shock_failed_bounce_short` bars (34.6%) are also `shock_support_break_short` bars. Nested ideas are two looks at one hypothesis: read both results docs together (family of two, BH q above).

**Unconditional control** (`control_events`: the same trigger with the shock state ignored; same race, same matched null): N = 18153, ΔExpR -0.4242R, 95% week-clustered interval -0.5102R to -0.3305R. The idea's ΔExpR minus the control's: +0.1112R. A pass whose ΔExpR is not clearly above the control is not credited to the shock condition.

**SPY regime split** (SPY close vs its 200-day average at the last close before entry):

| SPY | N | ΔExpR |
|---|---|---|
| above its 200-day average | 4683 | -0.4238R |
| below its 200-day average | 1862 | -0.0344R |

Events with no SPY average before entry: 0.

## Shock read-outs (v211; descriptive, never gating)

Kept events N = 6545; skipped as overlapping an open race (`skipped_overlap`) = 911.

**Shock-day null** (K = 20 bars drawn only from this ticker's SHOCK days, no month or trend match; its own seeded stream): N = 6543, ΔExpR +0.0416R, 95% week-clustered interval -0.1884R to +0.2934R; events dropped for fewer than 5 SHOCK-day candidates: 2. The standard ΔExpR minus this one: -0.3546R. An edge that vanishes against this null is the market's drift after a shock day, not the stock trigger.

**Re-priced at 3 x slippage** (15.0 bps a side, both fills, events and standard null; shock-day spreads widen 2-5x): ΔExpR -0.3122R, 95% week-clustered interval -0.5237R to -0.0739R; change vs the base book +0.0008R. Printed, never gating.

**Gap split** (next open vs the signal close; the race fills the entry at that open, gap included, and a gap through the stop at the open):

| gap | N | mean R_event | ΔExpR (standard null) |
|---|---:|---:|---:|
| <= -1% | 716 | -0.3702R | -0.6915R |
| -1% .. +1% | 4632 | -0.1504R | -0.2983R |
| >= +1% | 1197 | +0.0419R | -0.1438R |

Events with no next open: 0.

**Day of the episode** (`peak`: the signal close is the episode's highest BREADTH_ATR1 so far, so the entry is the session after the breadth peak; `later`: any other SHOCK day of the episode):

| day | N | mean R_event | ΔExpR (standard null) |
|---|---:|---:|---:|
| peak | 5149 | -0.1361R | -0.3328R |
| later | 1396 | -0.1509R | -0.2402R |

Events on a NORMAL day: 0.

## Context series (v211 level)

Scope: a daily breadth-shock proxy (SHOCK_D: enter when BREADTH_ATR1 >= 0.40, release when BREADTH_ATR1 <= 0.10 and ^VIX closes down), not the live market-shock detector; a pass does not license the detector's labels, and a fail closes exactly this frozen definition (short only, the fixed 10-bar race) and is never re-run with a looser one.

| series | rows | first | last | SHA-256 |
|---|---:|---|---|---|
| BREADTH_ATR1 | 2666 | 2009-06-01 | 2019-12-31 | `b5bcbe2d7d4b` |
| ^VIX | 2768 | 2009-01-02 | 2019-12-31 | `e67ada509441` |

**Short-family BH q** (every short idea screened so far, `SHORT_SCREEN_IDS`, this run's row included; reported, never gating):

| ledger id | q |
|---|---:|
| `v104-b-short-mechanisms` | n/a |
| `screen-range_breakdown_close` | 0.9996 |
| `screen-shock_support_break_short` | 0.9996 |
