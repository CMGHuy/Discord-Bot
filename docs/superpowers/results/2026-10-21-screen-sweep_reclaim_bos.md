# v140 screen: `sweep_reclaim_bos` -> SCREEN-FAIL

**Ledger id:** `screen-sweep_reclaim_bos` (instrument `screen-v1`); BH q = 1.0000 across the ledger (reported, never gating).

**Run:** 2026-10-21; window 2010-01-01..2019-12-31; events count from 2011-01-01 (earlier bars only prime the indicators); the year rule is 7 of 9 calendar years (2011-2019); `python scripts/backtest/screen_idea.py --idea sweep_reclaim_bos`; null K = 20, seed 42 per (idea, ticker); bootstrap 10,000 week resamples, seed 42.

**Trigger:** low < the last confirmed k=3 swing low (>= 4 bars old), a close back above it on that bar or within 2 more, then a close above the last confirmed swing high known at the sweep, within 10 bars of the sweep; a low under the sweep low after the reclaim cancels; each swing low arms at most one setup (Daiken/BigWhale price-action pages, steps 4-5 (liquidity sweep, reclaim, BOS confirmation); partner-shared 2026-10-21); params pivot_k=3, min_age=4, reclaim_bars=2, bos_bars=10; time cap 20 bars; long only.

**Trade:** entry next open; stop 1.5 x ATR14; target 3.0 x ATR14; a gap through either level fills at the open; stop first on a bar touching both; costs 5.0 bps a side + 0.0200R commission.

**Spec:** `docs/superpowers/specs/implemented/2026-10-08-v140-idea-screen-design.md`

## Universe and counters

| | count |
|---|---|
| point-in-time S&P 500 members in the window | 719 |
| cached and screened | 506 |
| missing from the cache (survivorship that remains) | 213 |
| cached but empty inside the window | 14 |
| raw events | 7850 |
| `dropped_nonmember` | 1682 |
| `dropped_warmup` | 533 |
| `dropped_window` | 89 |
| `skipped_overlap` | 93 |
| `dropped_no_match` | 136 |
| **kept events (N)** | **5317** |

PIT members missing from the cache: AABA, ABC, ABMD, ACS, ADS, AET, AGN, AKS, ALTR, ALXN, ANDV, ANRZQ, ANSS, ANTM, APC, APOL, ARG, ARNC, ATGE, ATVI, AVB, AVP, AYE, BBBY, BCR, BDK, BHGE, BIG, BJS, BK, BLL, BMC, BMS, BNI, BRCM, BTUUQ, BXLT, CA, CAM, CBE, CBS, CCE, CELG, CEPH, CERN, CFN, CHK, CMA, CMCSK, COG, COL, COV, CPGX, CSRA, CTL, CTXS, CVC, CVH, CXO, DF, DFS, DISCA, DISCK, DISH, DNB, DNR, DO, DRE, DTV, DWDP, EA, EKDKQ, ENDP, EQR, ESRX, ESV, ETFC, EVHC, FBHS, FDO, FII, FL, FLIR, FLT, FRC, FRX, FTR, GAS, GGP, GMCR, GPS, HAR, HBI, HCBK, HCP, HES, HFC, HNZ, HOLX, HOT, HRS, HSH, HSP, IGT, IPG, JCP, JEC, JNPR, JNS, JOY, JWN, K, KORS, KRFT, KSU, LEG, LIFE, LLL, LLTC, LM, LO, LSI, LVLT, LXK, MDP, MEE, MFE, MHS, MIL, MJN, MMC, MNK, MOLX, MON, MRO, MWV, MWW, MXIM, MYL, NBL, NFX, NLOK, NLSN, NOVL, NSM, NVLS, NYX, ODP, PBCT, PBG, PCP, PDCO, PEAK, PETM, PGN, PKI, PLL, POM, PTV, PX, PXD, Q, QEP, QLGC, RAI, RDC, RE, RHT, RRD, RSHCQ, RTN, RX, SCG, SEE, SIAL, SIVB, SNI, SPLS, SRCL, STJ, STR, SUNEQ, SVU, SWN, SWY, SYMC, TEG, TGNA, TIE, TIF, TLAB, TMK, TSS, TWC, TWTR, TWX, UTX, VAR, VIAB, VIAC, WBA, WCG, WFM, WIN, WLTW, WPX, WRK, WYND, X, XEC, XL, XLNX, XTO.

## Verdict: SCREEN-FAIL

| Clause | Measured | Rule | Holds |
|---|---|---|---|
| ΔExpR = mean(R_event − mean R_null) | -0.1618R | ≥ +0.10R | **no** |
| lower 95% bound, week-clustered bootstrap | -0.2215R (upper -0.0994R) | > 0 | **no** |
| years with mean(d) > 0 | 0 of 9 | ≥ 7 | **no** |
| kept events N | 5317 | ≥ 300 | yes |

One-sided bootstrap p (share of resamples ≤ 0): 1.0000. N < 300 is `SCREEN-UNDERPOWERED` whatever the other clauses say.

## Both arms

Mean R_event +0.0910R; mean R_null (each event's null mean, averaged) +0.2528R. Both after costs.

| Exit | event arm | null arm |
|---|---|---|
| gap_stop | 382 (7.2%) | 6336 (6.5%) |
| gap_target | 237 (4.5%) | 5141 (5.2%) |
| stop | 2466 (46.4%) | 41551 (42.4%) |
| target | 1298 (24.4%) | 29828 (30.4%) |
| timeout | 934 (17.6%) | 15216 (15.5%) |

## Per year

| Year | N | mean(d) |
|---|---|---|
| 2011 | 579 | -0.1760R |
| 2012 | 571 | -0.2739R |
| 2013 | 616 | -0.0781R |
| 2014 | 514 | -0.2375R |
| 2015 | 546 | -0.1627R |
| 2016 | 601 | -0.1413R |
| 2017 | 738 | -0.1725R |
| 2018 | 590 | -0.1479R |
| 2019 | 562 | -0.0774R |

## Forward drift (reported, never gating)

Mean excess forward return in ATR14 units from the signal close, event minus its matched null.

| h (bars) | events | mean excess (ATR) |
|---|---|---|
| 5 | 5317 | -0.2787 |
| 10 | 5317 | -0.4494 |
| 20 | 5317 | -0.6254 |
| 60 | 5229 | -0.7136 |

Spearman rank correlation, raw event indicator vs h-bar forward return, member and warm bars pooled across tickers per year:

| Year | h=5 | h=10 | h=20 | h=60 |
|---|---|---|---|---|
| 2011 | -0.0114 | -0.0015 | +0.0029 | +0.0026 |
| 2012 | -0.0109 | -0.0002 | -0.0059 | -0.0108 |
| 2013 | +0.0014 | +0.0022 | -0.0043 | -0.0018 |
| 2014 | -0.0079 | -0.0102 | -0.0044 | -0.0078 |
| 2015 | -0.0022 | -0.0013 | +0.0014 | +0.0023 |
| 2016 | -0.0002 | +0.0002 | -0.0052 | -0.0110 |
| 2017 | +0.0002 | -0.0026 | -0.0009 | -0.0011 |
| 2018 | -0.0019 | -0.0071 | -0.0076 | -0.0050 |
| 2019 | -0.0020 | -0.0008 | -0.0097 | -0.0023 |
