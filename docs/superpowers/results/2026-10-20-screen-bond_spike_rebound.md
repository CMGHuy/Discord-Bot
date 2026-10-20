# v140 screen: `bond_spike_rebound` -> SCREEN-FAIL

**Ledger id:** `screen-bond_spike_rebound` (instrument `screen-v1`); BH q = 0.3808 across the ledger (reported, never gating).

**Run:** 2026-10-20; window 2010-01-01..2019-12-31; events count from 2011-01-01 (earlier bars only prime the indicators); the year rule is 7 of 9 calendar years (2011-2019); `python scripts/backtest/screen_idea.py --idea bond_spike_rebound`; null K = 20, seed 42 per (idea, ticker); bootstrap 10,000 week resamples, seed 42.

**Trigger:** TLT 5-day return z >= +2.0 vs its trailing 252 values (Murphy (2004), Intermarket Analysis — shock proxy, see v174 § What the two shots can and cannot say); params series=TLT, lookback=5, window=252, z=2.0, side=long; time cap 10 bars; long only.

**Trade:** entry next open; stop 1.5 x ATR14; target 3.0 x ATR14; a gap through either level fills at the open; stop first on a bar touching both; costs 5.0 bps a side + 0.0200R commission.

**Spec:** `docs/superpowers/specs/implemented/2026-10-08-v140-idea-screen-design.md`

## Universe and counters

| | count |
|---|---|
| point-in-time S&P 500 members in the window | 719 |
| cached and screened | 506 |
| missing from the cache (survivorship that remains) | 213 |
| cached but empty inside the window | 14 |
| raw events | 30301 |
| `dropped_nonmember` | 5897 |
| `dropped_warmup` | 1095 |
| `dropped_window` | 0 |
| `skipped_overlap` | 13469 |
| `dropped_no_match` | 722 |
| **kept events (N)** | **9118** |

PIT members missing from the cache: AABA, ABC, ABMD, ACS, ADS, AET, AGN, AKS, ALTR, ALXN, ANDV, ANRZQ, ANSS, ANTM, APC, APOL, ARG, ARNC, ATGE, ATVI, AVB, AVP, AYE, BBBY, BCR, BDK, BHGE, BIG, BJS, BK, BLL, BMC, BMS, BNI, BRCM, BTUUQ, BXLT, CA, CAM, CBE, CBS, CCE, CELG, CEPH, CERN, CFN, CHK, CMA, CMCSK, COG, COL, COV, CPGX, CSRA, CTL, CTXS, CVC, CVH, CXO, DF, DFS, DISCA, DISCK, DISH, DNB, DNR, DO, DRE, DTV, DWDP, EA, EKDKQ, ENDP, EQR, ESRX, ESV, ETFC, EVHC, FBHS, FDO, FII, FL, FLIR, FLT, FRC, FRX, FTR, GAS, GGP, GMCR, GPS, HAR, HBI, HCBK, HCP, HES, HFC, HNZ, HOLX, HOT, HRS, HSH, HSP, IGT, IPG, JCP, JEC, JNPR, JNS, JOY, JWN, K, KORS, KRFT, KSU, LEG, LIFE, LLL, LLTC, LM, LO, LSI, LVLT, LXK, MDP, MEE, MFE, MHS, MIL, MJN, MMC, MNK, MOLX, MON, MRO, MWV, MWW, MXIM, MYL, NBL, NFX, NLOK, NLSN, NOVL, NSM, NVLS, NYX, ODP, PBCT, PBG, PCP, PDCO, PEAK, PETM, PGN, PKI, PLL, POM, PTV, PX, PXD, Q, QEP, QLGC, RAI, RDC, RE, RHT, RRD, RSHCQ, RTN, RX, SCG, SEE, SIAL, SIVB, SNI, SPLS, SRCL, STJ, STR, SUNEQ, SVU, SWN, SWY, SYMC, TEG, TGNA, TIE, TIF, TLAB, TMK, TSS, TWC, TWTR, TWX, UTX, VAR, VIAB, VIAC, WBA, WCG, WFM, WIN, WLTW, WPX, WRK, WYND, X, XEC, XL, XLNX, XTO.

## Verdict: SCREEN-FAIL

| Clause | Measured | Rule | Holds |
|---|---|---|---|
| ΔExpR = mean(R_event − mean R_null) | +0.1731R | ≥ +0.10R | yes |
| lower 95% bound, week-clustered bootstrap | -0.0946R (upper +0.4576R) | > 0 | **no** |
| years with mean(d) > 0 | 7 of 9 | ≥ 7 | yes |
| kept events N | 9118 | ≥ 300 | yes |

One-sided bootstrap p (share of resamples ≤ 0): 0.1088. N < 300 is `SCREEN-UNDERPOWERED` whatever the other clauses say.

## Both arms

Mean R_event +0.1318R; mean R_null (each event's null mean, averaged) -0.0413R. Both after costs.

| Exit | event arm | null arm |
|---|---|---|
| gap_stop | 401 (4.4%) | 11690 (8.3%) |
| gap_target | 237 (2.6%) | 2439 (1.7%) |
| stop | 3540 (38.8%) | 55067 (39.2%) |
| target | 1520 (16.7%) | 17784 (12.7%) |
| timeout | 3420 (37.5%) | 53380 (38.0%) |

## Per year

| Year | N | mean(d) |
|---|---|---|
| 2011 | 2329 | +0.0455R |
| 2012 | 307 | +0.9115R |
| 2013 | 345 | +0.0252R |
| 2014 | 776 | +0.2825R |
| 2015 | 591 | +0.1364R |
| 2016 | 846 | +1.0186R |
| 2017 | 0 | n/aR |
| 2018 | 1302 | -0.3169R |
| 2019 | 2622 | +0.1658R |

## Forward drift (reported, never gating)

Mean excess forward return in ATR14 units from the signal close, event minus its matched null.

| h (bars) | events | mean excess (ATR) |
|---|---|---|
| 5 | 9118 | +0.4463 |
| 10 | 9118 | -0.0044 |
| 20 | 9118 | +0.1338 |
| 60 | 9118 | +0.4535 |

Spearman rank correlation, raw event indicator vs h-bar forward return, member and warm bars pooled across tickers per year:

| Year | h=5 | h=10 | h=20 | h=60 |
|---|---|---|---|---|
| 2011 | -0.0054 | -0.0419 | +0.0368 | +0.0860 |
| 2012 | +0.0669 | +0.0577 | +0.0483 | +0.0285 |
| 2013 | +0.0507 | -0.0095 | +0.0306 | -0.0048 |
| 2014 | +0.1058 | +0.0421 | +0.0179 | +0.0380 |
| 2015 | +0.0379 | +0.0295 | +0.0665 | +0.0656 |
| 2016 | +0.1312 | +0.1571 | +0.1281 | +0.0302 |
| 2017 | n/a | n/a | n/a | n/a |
| 2018 | -0.0366 | -0.0838 | -0.0202 | +0.0938 |
| 2019 | +0.0939 | +0.0754 | +0.0907 | +0.0430 |

## Intermarket diagnostics (printed, never gating)

None of these lines is a clause of the verdict above; the verdict is computed exactly as for every other screen.

**Context data** (v174 spec `2026-10-18-v174-intermarket-shock-screens-design.md`): context series loaded from 2009-06-01 for the z warm-up; the stock window starts 2010-01-01. Adjusted closes, the bytes pinned by SHA-256 in `docs/superpowers/results/2026-10-18-v174-context-hashes.json`.

| Series | rows | first bar | last bar | fetched | SHA-256 |
|---|---|---|---|---|---|
| TLT | 2666 | 2009-06-01 | 2019-12-31 | 2026-10-18 | `8af29e82e4870f485b46c36c940fda767f2d1d8d0d6f25fd9ccb6f8a229a7525` |
| UUP | 2666 | 2009-06-01 | 2019-12-31 | 2026-10-18 | `c88659a0015a07109e3be7290b2914c07e137fd23e7f7e1da17b7ff81a21c690` |

### 1. Effective sample

Kept ticker events N = 9118, from 61 shock days in 21 episodes (runs more than 5 sessions apart) over 30 distinct ISO entry weeks. One shock day fires every member with a bar, so the screen tests the episodes, not N, and the N >= 300 clause cannot see that. The week-clustered percentile bootstrap undercovers with this few clusters, so the lower bound is looser than nominal.

| Year | shock days | kept events |
|---|---|---|
| 2011 | 16 | 2329 |
| 2012 | 1 | 307 |
| 2013 | 1 | 345 |
| 2014 | 3 | 776 |
| 2015 | 4 | 591 |
| 2016 | 8 | 846 |
| 2017 | 0 | 0 |
| 2018 | 9 | 1302 |
| 2019 | 19 | 2622 |

### 2. Null overlap

Official ΔExpR +0.1731R over N = 9118. With the null pool restricted to bars at least 10 sessions from any shock day (same seed, K and cap; an event left with fewer than 5 candidates drops out): ΔExpR +0.3238R, 95% week-clustered interval -0.3241R to +0.8931R, N = 3077. The gap shows how far pre-shock and post-shock null races moved the official figure.

### 3. SPY selloff split

SPY's own 5-day return on the shock days: 58 below 0, 3 at or above 0, mean -3.19%.

| SPY 5-day return at the signal day | N | ΔExpR | 95% interval |
|---|---|---|---|
| < 0 | 8706 | +0.2089R | -0.0618R to +0.5044R |
| >= 0 | 412 | -0.5846R | -0.7680R to +2.1453R |

Kept events with no SPY 5-day return at their signal day: 0. A pass carried by the < 0 half is a mean-reversion effect, not an intermarket one.

### 4. Concentration by shock episode

Each episode's contribution to ΔExpR = (sum of its d) / N, largest first. ΔExpR +0.1731R; the two largest episodes add +0.1332R.

| Episode (signal days) | kept events | contribution to ΔExpR |
|---|---|---|
| 2016-06-27..2016-07-01 | 443 | +0.0752R |
| 2014-12-12..2014-12-16 | 434 | +0.0580R |
| 2019-05-29..2019-06-03 | 489 | +0.0563R |
| 2011-08-18..2011-08-22 | 245 | +0.0328R |
| 2012-06-01 | 307 | +0.0307R |
| 2019-03-25..2019-03-28 | 449 | +0.0306R |
| 2018-05-29..2018-05-31 | 411 | +0.0247R |
| 2016-02-08..2016-02-11 | 403 | +0.0193R |
| 2011-09-06..2011-09-08 | 326 | +0.0187R |
| 2019-01-03 | 266 | +0.0122R |
| 2011-09-21..2011-09-23 | 339 | +0.0119R |
| 2015-01-15 | 187 | +0.0056R |
| 2015-01-05..2015-01-07 | 404 | +0.0032R |
| 2013-04-05 | 345 | +0.0010R |
| 2019-09-20 | 419 | -0.0065R |
| 2011-11-03 | 321 | -0.0103R |
| 2018-12-19 | 385 | -0.0227R |
| 2014-10-01 | 342 | -0.0339R |
| 2011-08-01..2011-08-10 | 1098 | -0.0413R |
| 2019-08-01..2019-08-16 | 999 | -0.0451R |
| 2018-12-04..2018-12-11 | 506 | -0.0472R |

Kept events whose signal day is no shock day (a gap in the stock's own calendar): 0.

### 5. Multiple comparisons

BH q = 0.2720 across the `screen-v1` family (this idea plus every earlier screen row); the head line's q runs across the whole ledger. Reported, never gating.

### 6. Scope

Scope: a shock proxy, not Murphy's intermarket claim itself; a fail closes exactly this frozen definition (TLT 5-day return z >= +2.0 vs its trailing 252 values, long only, the fixed 10-bar race) and nothing broader: not intermarket analysis, not a slow-regime test, not a bearish or longer-horizon variant.
