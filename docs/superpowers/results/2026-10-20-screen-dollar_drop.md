# v140 screen: `dollar_drop` -> SCREEN-FAIL

**Ledger id:** `screen-dollar_drop` (instrument `screen-v1`); BH q = 0.3499 across the ledger (reported, never gating).

**Run:** 2026-10-20; window 2010-01-01..2019-12-31; events count from 2011-01-01 (earlier bars only prime the indicators); the year rule is 7 of 9 calendar years (2011-2019); `python scripts/backtest/screen_idea.py --idea dollar_drop`; null K = 20, seed 42 per (idea, ticker); bootstrap 10,000 week resamples, seed 42.

**Trigger:** UUP 5-day return z <= -2.0 vs its trailing 252 values (Murphy (2004), Intermarket Analysis — shock proxy, see v174 § What the two shots can and cannot say); params series=UUP, lookback=5, window=252, z=-2.0, side=long; time cap 10 bars; long only.

**Trade:** entry next open; stop 1.5 x ATR14; target 3.0 x ATR14; a gap through either level fills at the open; stop first on a bar touching both; costs 5.0 bps a side + 0.0200R commission.

**Spec:** `docs/superpowers/specs/implemented/2026-10-08-v140-idea-screen-design.md`

## Universe and counters

| | count |
|---|---|
| point-in-time S&P 500 members in the window | 719 |
| cached and screened | 506 |
| missing from the cache (survivorship that remains) | 213 |
| cached but empty inside the window | 14 |
| raw events | 26783 |
| `dropped_nonmember` | 5837 |
| `dropped_warmup` | 2361 |
| `dropped_window` | 0 |
| `skipped_overlap` | 8324 |
| `dropped_no_match` | 366 |
| **kept events (N)** | **9895** |

PIT members missing from the cache: AABA, ABC, ABMD, ACS, ADS, AET, AGN, AKS, ALTR, ALXN, ANDV, ANRZQ, ANSS, ANTM, APC, APOL, ARG, ARNC, ATGE, ATVI, AVB, AVP, AYE, BBBY, BCR, BDK, BHGE, BIG, BJS, BK, BLL, BMC, BMS, BNI, BRCM, BTUUQ, BXLT, CA, CAM, CBE, CBS, CCE, CELG, CEPH, CERN, CFN, CHK, CMA, CMCSK, COG, COL, COV, CPGX, CSRA, CTL, CTXS, CVC, CVH, CXO, DF, DFS, DISCA, DISCK, DISH, DNB, DNR, DO, DRE, DTV, DWDP, EA, EKDKQ, ENDP, EQR, ESRX, ESV, ETFC, EVHC, FBHS, FDO, FII, FL, FLIR, FLT, FRC, FRX, FTR, GAS, GGP, GMCR, GPS, HAR, HBI, HCBK, HCP, HES, HFC, HNZ, HOLX, HOT, HRS, HSH, HSP, IGT, IPG, JCP, JEC, JNPR, JNS, JOY, JWN, K, KORS, KRFT, KSU, LEG, LIFE, LLL, LLTC, LM, LO, LSI, LVLT, LXK, MDP, MEE, MFE, MHS, MIL, MJN, MMC, MNK, MOLX, MON, MRO, MWV, MWW, MXIM, MYL, NBL, NFX, NLOK, NLSN, NOVL, NSM, NVLS, NYX, ODP, PBCT, PBG, PCP, PDCO, PEAK, PETM, PGN, PKI, PLL, POM, PTV, PX, PXD, Q, QEP, QLGC, RAI, RDC, RE, RHT, RRD, RSHCQ, RTN, RX, SCG, SEE, SIAL, SIVB, SNI, SPLS, SRCL, STJ, STR, SUNEQ, SVU, SWN, SWY, SYMC, TEG, TGNA, TIE, TIF, TLAB, TMK, TSS, TWC, TWTR, TWX, UTX, VAR, VIAB, VIAC, WBA, WCG, WFM, WIN, WLTW, WPX, WRK, WYND, X, XEC, XL, XLNX, XTO.

## Verdict: SCREEN-FAIL

| Clause | Measured | Rule | Holds |
|---|---|---|---|
| ΔExpR = mean(R_event − mean R_null) | +0.0937R | ≥ +0.10R | **no** |
| lower 95% bound, week-clustered bootstrap | -0.0751R (upper +0.2543R) | > 0 | **no** |
| years with mean(d) > 0 | 5 of 9 | ≥ 7 | **no** |
| kept events N | 9895 | ≥ 300 | yes |

One-sided bootstrap p (share of resamples ≤ 0): 0.1312. N < 300 is `SCREEN-UNDERPOWERED` whatever the other clauses say.

## Both arms

Mean R_event +0.1697R; mean R_null (each event's null mean, averaged) +0.0760R. Both after costs.

| Exit | event arm | null arm |
|---|---|---|
| gap_stop | 501 (5.1%) | 9299 (5.4%) |
| gap_target | 220 (2.2%) | 3772 (2.2%) |
| stop | 3087 (31.2%) | 60630 (35.5%) |
| target | 1277 (12.9%) | 23240 (13.6%) |
| timeout | 4810 (48.6%) | 73771 (43.2%) |

## Per year

| Year | N | mean(d) |
|---|---|---|
| 2011 | 943 | -0.1948R |
| 2012 | 333 | -0.6053R |
| 2013 | 1168 | +0.1365R |
| 2014 | 344 | +0.8605R |
| 2015 | 2923 | +0.1501R |
| 2016 | 440 | -0.2736R |
| 2017 | 1196 | +0.4823R |
| 2018 | 1245 | +0.1369R |
| 2019 | 1303 | -0.1602R |

## Forward drift (reported, never gating)

Mean excess forward return in ATR14 units from the signal close, event minus its matched null.

| h (bars) | events | mean excess (ATR) |
|---|---|---|
| 5 | 9895 | +0.2415 |
| 10 | 9895 | +0.3649 |
| 20 | 9895 | +0.0664 |
| 60 | 9470 | +0.1066 |

Spearman rank correlation, raw event indicator vs h-bar forward return, member and warm bars pooled across tickers per year:

| Year | h=5 | h=10 | h=20 | h=60 |
|---|---|---|---|---|
| 2011 | +0.0078 | +0.0511 | +0.0244 | +0.0436 |
| 2012 | -0.0193 | -0.0363 | -0.0334 | -0.0230 |
| 2013 | +0.0347 | -0.0349 | -0.0092 | -0.0703 |
| 2014 | +0.0660 | +0.0680 | +0.0052 | +0.0044 |
| 2015 | +0.0062 | +0.0494 | +0.0380 | +0.0252 |
| 2016 | +0.0187 | +0.0479 | +0.0655 | +0.0364 |
| 2017 | +0.0410 | +0.0425 | +0.0202 | -0.0019 |
| 2018 | +0.0750 | +0.0162 | -0.0300 | -0.0508 |
| 2019 | +0.0171 | +0.0239 | +0.0183 | +0.0100 |

## Intermarket diagnostics (printed, never gating)

None of these lines is a clause of the verdict above; the verdict is computed exactly as for every other screen.

**Context data** (v174 spec `2026-10-18-v174-intermarket-shock-screens-design.md`): context series loaded from 2009-06-01 for the z warm-up; the stock window starts 2010-01-01. Adjusted closes, the bytes pinned by SHA-256 in `docs/superpowers/results/2026-10-18-v174-context-hashes.json`.

| Series | rows | first bar | last bar | fetched | SHA-256 |
|---|---|---|---|---|---|
| TLT | 2666 | 2009-06-01 | 2019-12-31 | 2026-10-18 | `8af29e82e4870f485b46c36c940fda767f2d1d8d0d6f25fd9ccb6f8a229a7525` |
| UUP | 2666 | 2009-06-01 | 2019-12-31 | 2026-10-18 | `c88659a0015a07109e3be7290b2914c07e137fd23e7f7e1da17b7ff81a21c690` |

### 1. Effective sample

Kept ticker events N = 9895, from 50 shock days in 25 episodes (runs more than 5 sessions apart) over 32 distinct ISO entry weeks. One shock day fires every member with a bar, so the screen tests the episodes, not N, and the N >= 300 clause cannot see that. The week-clustered percentile bootstrap undercovers with this few clusters, so the lower bound is looser than nominal.

| Year | shock days | kept events |
|---|---|---|
| 2011 | 5 | 943 |
| 2012 | 1 | 333 |
| 2013 | 9 | 1168 |
| 2014 | 1 | 344 |
| 2015 | 18 | 2923 |
| 2016 | 2 | 440 |
| 2017 | 4 | 1196 |
| 2018 | 5 | 1245 |
| 2019 | 5 | 1303 |

### 2. Null overlap

Official ΔExpR +0.0937R over N = 9895. With the null pool restricted to bars at least 10 sessions from any shock day (same seed, K and cap; an event left with fewer than 5 candidates drops out): ΔExpR +0.2357R, 95% week-clustered interval -0.0402R to +0.5257R, N = 3875. The gap shows how far pre-shock and post-shock null races moved the official figure.

### 3. SPY selloff split

SPY's own 5-day return on the shock days: 21 below 0, 29 at or above 0, mean +0.46%.

| SPY 5-day return at the signal day | N | ΔExpR | 95% interval |
|---|---|---|---|
| < 0 | 4111 | +0.3237R | +0.1204R to +0.5615R |
| >= 0 | 5784 | -0.0697R | -0.2917R to +0.1387R |

Kept events with no SPY 5-day return at their signal day: 0. A pass carried by the < 0 half is a mean-reversion effect, not an intermarket one.

### 4. Concentration by shock episode

Each episode's contribution to ΔExpR = (sum of its d) / N, largest first. ΔExpR +0.0937R; the two largest episodes add +0.0705R.

| Episode (signal days) | kept events | contribution to ΔExpR |
|---|---|---|
| 2017-05-17..2017-05-19 | 408 | +0.0406R |
| 2014-12-12 | 344 | +0.0299R |
| 2018-01-16..2018-01-18 | 436 | +0.0231R |
| 2013-04-30..2013-05-01 | 358 | +0.0229R |
| 2015-08-24..2015-08-25 | 462 | +0.0145R |
| 2011-10-10..2011-10-14 | 338 | +0.0139R |
| 2015-06-03..2015-06-08 | 442 | +0.0135R |
| 2015-04-28..2015-05-01 | 379 | +0.0101R |
| 2015-02-05 | 352 | +0.0098R |
| 2017-06-29 | 392 | +0.0090R |
| 2017-03-21 | 396 | +0.0087R |
| 2015-12-09 | 367 | +0.0064R |
| 2011-01-19 | 326 | +0.0051R |
| 2018-08-22 | 409 | +0.0030R |
| 2013-06-04..2013-06-12 | 447 | +0.0030R |
| 2015-04-16..2015-04-20 | 381 | -0.0002R |
| 2019-01-09 | 413 | -0.0021R |
| 2019-10-21 | 425 | -0.0056R |
| 2018-02-15 | 400 | -0.0089R |
| 2015-03-18..2015-03-26 | 540 | -0.0097R |
| 2013-07-12..2013-07-16 | 363 | -0.0097R |
| 2016-02-05..2016-02-09 | 440 | -0.0122R |
| 2019-06-21..2019-06-25 | 465 | -0.0134R |
| 2012-09-13 | 333 | -0.0204R |
| 2011-10-27 | 278 | -0.0376R |

Kept events whose signal day is no shock day (a gap in the stock's own calendar): 1.

### 5. Multiple comparisons

BH q = 0.2624 across the `screen-v1` family (this idea plus every earlier screen row); the head line's q runs across the whole ledger. Reported, never gating.

### 6. Scope

Scope: a shock proxy, not Murphy's intermarket claim itself; a fail closes exactly this frozen definition (UUP 5-day return z <= -2.0 vs its trailing 252 values, long only, the fixed 10-bar race) and nothing broader: not intermarket analysis, not a slow-regime test, not a bearish or longer-horizon variant.
