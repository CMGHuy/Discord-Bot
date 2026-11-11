# v140 screen: `fvg_overhead_aged` -> SCREEN-FAIL

**Ledger id:** `screen-fvg_overhead_aged` (instrument `screen-v1`); BH q = 1.0000 across the ledger (reported, never gating).

**Run:** 2026-11-11; window 2010-01-01..2019-12-31; events count from 2011-01-01 (earlier bars only prime the indicators); the year rule is 7 of 9 calendar years (2011-2019); `python scripts/backtest/screen_idea.py --idea fvg_overhead_aged`; null K = 20, seed 42 per (idea, ticker); bootstrap 10,000 week resamples, seed 42.

**Trigger:** first bar t at which an unfilled bearish FVG (live detector on bars <= t) aged >= 5 bars has Close[t] < bottom <= Close[t] + 3 x ATR14[t]; once per gap; avoid mode against the null and an out-of-reach control (docs/superpowers/results/2026-11-06-loss-review-sep-nov.md: live longs whose TP1 sits at an older unfilled bearish FVG, N = 68, ExpR -0.199R since 2026-09-01 (motivation only)); params side=bearish, anchor=bottom, min_age_bars=5, reach_atr=3.0, atr_n=14, lookback=100, max_per_side=3, fill=any wick touch, onset=once per gap bar_index; time cap 20 bars; long only.

**Trade:** entry next open; stop 1.5 x ATR14; target 3.0 x ATR14; a gap through either level fills at the open; stop first on a bar touching both; costs 5.0 bps a side + 0.0200R commission.

**Spec:** `docs/superpowers/specs/implemented/2026-10-08-v140-idea-screen-design.md`

## Universe and counters

| | count |
|---|---|
| point-in-time S&P 500 members in the window | 719 |
| cached and screened | 506 |
| missing from the cache (survivorship that remains) | 213 |
| cached but empty inside the window | 14 |
| raw events | 33772 |
| `dropped_nonmember` | 6578 |
| `dropped_warmup` | 2265 |
| `dropped_window` | 93 |
| `skipped_overlap` | 7829 |
| `dropped_no_match` | 3099 |
| **kept events (N)** | **13908** |

PIT members missing from the cache: AABA, ABC, ABMD, ACS, ADS, AET, AGN, AKS, ALTR, ALXN, ANDV, ANRZQ, ANSS, ANTM, APC, APOL, ARG, ARNC, ATGE, ATVI, AVB, AVP, AYE, BBBY, BCR, BDK, BHGE, BIG, BJS, BK, BLL, BMC, BMS, BNI, BRCM, BTUUQ, BXLT, CA, CAM, CBE, CBS, CCE, CELG, CEPH, CERN, CFN, CHK, CMA, CMCSK, COG, COL, COV, CPGX, CSRA, CTL, CTXS, CVC, CVH, CXO, DF, DFS, DISCA, DISCK, DISH, DNB, DNR, DO, DRE, DTV, DWDP, EA, EKDKQ, ENDP, EQR, ESRX, ESV, ETFC, EVHC, FBHS, FDO, FII, FL, FLIR, FLT, FRC, FRX, FTR, GAS, GGP, GMCR, GPS, HAR, HBI, HCBK, HCP, HES, HFC, HNZ, HOLX, HOT, HRS, HSH, HSP, IGT, IPG, JCP, JEC, JNPR, JNS, JOY, JWN, K, KORS, KRFT, KSU, LEG, LIFE, LLL, LLTC, LM, LO, LSI, LVLT, LXK, MDP, MEE, MFE, MHS, MIL, MJN, MMC, MNK, MOLX, MON, MRO, MWV, MWW, MXIM, MYL, NBL, NFX, NLOK, NLSN, NOVL, NSM, NVLS, NYX, ODP, PBCT, PBG, PCP, PDCO, PEAK, PETM, PGN, PKI, PLL, POM, PTV, PX, PXD, Q, QEP, QLGC, RAI, RDC, RE, RHT, RRD, RSHCQ, RTN, RX, SCG, SEE, SIAL, SIVB, SNI, SPLS, SRCL, STJ, STR, SUNEQ, SVU, SWN, SWY, SYMC, TEG, TGNA, TIE, TIF, TLAB, TMK, TSS, TWC, TWTR, TWX, UTX, VAR, VIAB, VIAC, WBA, WCG, WFM, WIN, WLTW, WPX, WRK, WYND, X, XEC, XL, XLNX, XTO.

## Verdict: SCREEN-FAIL

| Clause | Measured | Rule | Holds |
|---|---|---|---|
| ΔExpR = mean(R_event − mean R_null) | +0.3709R | ≤ -0.10R | **no** |
| upper 95% bound, week-clustered bootstrap | +0.4521R (lower +0.2962R) | < 0 | **no** |
| years with mean(d) < 0 | 0 of 9 | ≥ 7 | **no** |
| kept events N | 13908 | ≥ 300 | yes |
| control arm ΔExpR = mean(R_event − mean R_control) | +0.0721R | ≤ -0.10R | **no** |
| control arm upper 95% bound | +0.2120R (lower -0.0528R) | < 0 | **no** |
| control arm events N_c | 4559 | ≥ 300 | yes |

One-sided bootstrap p (share of resamples ≥ 0): 1.0000. N < 300 or N_c < 300 is `SCREEN-UNDERPOWERED` whatever the other clauses say; the control arm is drawn from bars where the idea's control condition holds (G1), so a sign flip alone never passes.

## Both arms

Mean R_event +0.0893R; mean R_null (each event's null mean, averaged) -0.2816R. Both after costs.

| Exit | event arm | null arm |
|---|---|---|
| gap_stop | 1038 (7.5%) | 14907 (8.9%) |
| gap_target | 547 (3.9%) | 4500 (2.7%) |
| stop | 6413 (46.1%) | 99463 (59.2%) |
| target | 3564 (25.6%) | 28596 (17.0%) |
| timeout | 2346 (16.9%) | 20606 (12.3%) |

## Per year

| Year | N | mean(d) |
|---|---|---|
| 2011 | 1619 | +0.2164R |
| 2012 | 1357 | +0.3619R |
| 2013 | 1238 | +0.4485R |
| 2014 | 1429 | +0.4225R |
| 2015 | 1686 | +0.3204R |
| 2016 | 1683 | +0.3191R |
| 2017 | 1445 | +0.4204R |
| 2018 | 2137 | +0.4584R |
| 2019 | 1314 | +0.3757R |

## Forward drift (reported, never gating)

Mean excess forward return in ATR14 units from the signal close, event minus its matched null.

| h (bars) | events | mean excess (ATR) |
|---|---|---|
| 5 | 13908 | +0.4917 |
| 10 | 13908 | +0.7456 |
| 20 | 13908 | +0.8447 |
| 60 | 13692 | +0.7138 |

Spearman rank correlation, raw event indicator vs h-bar forward return, member and warm bars pooled across tickers per year:

| Year | h=5 | h=10 | h=20 | h=60 |
|---|---|---|---|---|
| 2011 | +0.0098 | +0.0009 | +0.0052 | -0.0026 |
| 2012 | -0.0209 | -0.0094 | -0.0141 | +0.0048 |
| 2013 | -0.0141 | +0.0056 | +0.0190 | +0.0166 |
| 2014 | +0.0134 | +0.0168 | +0.0219 | +0.0014 |
| 2015 | +0.0130 | +0.0254 | -0.0004 | +0.0096 |
| 2016 | -0.0053 | +0.0023 | -0.0006 | +0.0107 |
| 2017 | -0.0098 | -0.0093 | -0.0107 | -0.0194 |
| 2018 | +0.0260 | +0.0314 | +0.0350 | +0.0176 |
| 2019 | -0.0068 | -0.0232 | +0.0142 | -0.0117 |

## Avoid mode (read-outs, never gating)

**Seeds:** the matched null draws with `null_seed(idea, ticker)` = [42, crc32(idea), crc32(ticker)]; the control arm with `null_seed(idea + ":control", ticker)`, from bars where the idea's control condition holds, at least 5 candidates per event. Every bar where the idea's condition holds is excluded from both pools.

| Read-out | Count | Share |
|---|---|---|
| member and warm bars | 845874 | |
| condition bars excluded from both pools | 220345 | 26.0% of member and warm bars |
| kept events below the control floor | 9349 | 67.2% of kept events |
| kept events whose next open reached the gap bottom (overnight) | 236 | 1.7% of kept events |
| tickers aborted by an idea error | 0 | |

Idea errors per ticker: none.

### Control arm per year

| Year | N_c | mean(d_c) |
|---|---|---|
| 2011 | 604 | -0.1441R |
| 2012 | 397 | +0.1517R |
| 2013 | 239 | -0.0340R |
| 2014 | 357 | +0.1272R |
| 2015 | 637 | +0.2389R |
| 2016 | 552 | -0.0753R |
| 2017 | 448 | +0.0508R |
| 2018 | 873 | +0.2519R |
| 2019 | 452 | -0.0776R |

### Calibration: four closed screens (never re-run)

Clause 1 is ΔExpR ≤ -0.10R. Clause 2 (upper 95% bound < 0) is read from the ledger's edge p as p ≥ 0.975, because the ledger stores no interval. A screen passing both shows what a sign flip alone would clear; the control arm is what it never faced.

| Ledger id | Direction | ΔExpR | edge p | Clause 1 | Clause 2 |
|---|---|---|---|---|---|
| `screen-high52w` | long | -0.3660R | 1.0000 | yes | yes |
| `screen-gap_volume` | long | -0.4639R | 1.0000 | yes | yes |
| `screen-sweep_reclaim_bos` | long | -0.1618R | 1.0000 | yes | yes |
| `screen-range_breakdown_close` | short | -0.3210R | 0.9996 | yes | yes |

### Ledger order

This row is ledger row 80; v211 shots already in the ledger: screen-shock_support_break_short, screen-shock_failed_bounce_short. The BH q in the header is computed across the whole ledger in this order (spec § Constraints).
