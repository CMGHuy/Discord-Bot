# v140 screen: `shock_failed_bounce_short` -> SCREEN-FAIL

**Definition commit:** fb6d5a62ce9a28b938ad76a1e0a28cd616b21721

**Ledger id:** `screen-shock_failed_bounce_short` (instrument `screen-v1`); BH q = 1.0000 across the ledger (reported, never gating).

**Run:** 2026-11-10; window 2010-01-01..2019-12-31; events count from 2011-01-01 (earlier bars only prime the indicators); the year rule is 7 of 9 calendar years (2011-2019); `python scripts/backtest/screen_idea.py --idea shock_failed_bounce_short`; null K = 20, seed 42 per (idea, ticker); bootstrap 10,000 week resamples, seed 42.

**Trigger:** SHOCK_D on t; bounce bar b in t-5..t-1 (close[b-1] <= max(High[b-10..b-2]) - 1.0 ATR14[b-2], close[b] > close[b-1], High[b] < that max; latest b) and close[t] < Low[b], the first close below it since b (short, next open) (v209 spec § Track 2 (frozen 2026-11-05): breadth-shock-conditioned breakdown shorts, after the 2026-11-05 session the long book lost 13.9R); params breadth=BREADTH_ATR1, vix=^VIX, enter=0.4, release=0.1, decline_atr=1.0, high_from=10, high_to=2, bounce_from=5, bounce_to=1, side=short; time cap 10 bars; short only.

**Trade:** short; entry next open (sell); stop 1.5 x ATR14 above; target 3.0 x ATR14 below; a gap through either level fills at the open; stop first on a bar touching both; borrow 0.5% a year on calendar days held; costs 5.0 bps a side + 0.0200R commission.

**Spec:** `docs/superpowers/specs/implemented/2026-10-08-v140-idea-screen-design.md`

## Universe and counters

| | count |
|---|---|
| point-in-time S&P 500 members in the window | 719 |
| cached and screened | 506 |
| missing from the cache (survivorship that remains) | 213 |
| cached but empty inside the window | 14 |
| raw events | 14352 |
| `dropped_nonmember` | 3017 |
| `dropped_warmup` | 1530 |
| `dropped_window` | 0 |
| `skipped_overlap` | 973 |
| `dropped_no_match` | 362 |
| **kept events (N)** | **8470** |

PIT members missing from the cache: AABA, ABC, ABMD, ACS, ADS, AET, AGN, AKS, ALTR, ALXN, ANDV, ANRZQ, ANSS, ANTM, APC, APOL, ARG, ARNC, ATGE, ATVI, AVB, AVP, AYE, BBBY, BCR, BDK, BHGE, BIG, BJS, BK, BLL, BMC, BMS, BNI, BRCM, BTUUQ, BXLT, CA, CAM, CBE, CBS, CCE, CELG, CEPH, CERN, CFN, CHK, CMA, CMCSK, COG, COL, COV, CPGX, CSRA, CTL, CTXS, CVC, CVH, CXO, DF, DFS, DISCA, DISCK, DISH, DNB, DNR, DO, DRE, DTV, DWDP, EA, EKDKQ, ENDP, EQR, ESRX, ESV, ETFC, EVHC, FBHS, FDO, FII, FL, FLIR, FLT, FRC, FRX, FTR, GAS, GGP, GMCR, GPS, HAR, HBI, HCBK, HCP, HES, HFC, HNZ, HOLX, HOT, HRS, HSH, HSP, IGT, IPG, JCP, JEC, JNPR, JNS, JOY, JWN, K, KORS, KRFT, KSU, LEG, LIFE, LLL, LLTC, LM, LO, LSI, LVLT, LXK, MDP, MEE, MFE, MHS, MIL, MJN, MMC, MNK, MOLX, MON, MRO, MWV, MWW, MXIM, MYL, NBL, NFX, NLOK, NLSN, NOVL, NSM, NVLS, NYX, ODP, PBCT, PBG, PCP, PDCO, PEAK, PETM, PGN, PKI, PLL, POM, PTV, PX, PXD, Q, QEP, QLGC, RAI, RDC, RE, RHT, RRD, RSHCQ, RTN, RX, SCG, SEE, SIAL, SIVB, SNI, SPLS, SRCL, STJ, STR, SUNEQ, SVU, SWN, SWY, SYMC, TEG, TGNA, TIE, TIF, TLAB, TMK, TSS, TWC, TWTR, TWX, UTX, VAR, VIAB, VIAC, WBA, WCG, WFM, WIN, WLTW, WPX, WRK, WYND, X, XEC, XL, XLNX, XTO.

## Verdict: SCREEN-FAIL

| Clause | Measured | Rule | Holds |
|---|---|---|---|
| ΔExpR = mean(R_event − mean R_null) | -0.2000R | ≥ +0.10R | **no** |
| lower 95% bound, week-clustered bootstrap | -0.3843R (upper -0.0014R) | > 0 | **no** |
| years with mean(d) > 0 | 1 of 9 | ≥ 7 | **no** |
| kept events N | 8470 | ≥ 300 | yes |

One-sided bootstrap p (share of resamples ≤ 0): 0.9757. N < 300 is `SCREEN-UNDERPOWERED` whatever the other clauses say.

## Both arms

Mean R_event -0.2070R; mean R_null (each event's null mean, averaged) -0.0070R. Both after costs.

| Exit | event arm | null arm |
|---|---|---|
| gap_stop | 678 (8.0%) | 8830 (5.8%) |
| gap_target | 225 (2.7%) | 3716 (2.4%) |
| stop | 4120 (48.6%) | 59317 (38.9%) |
| target | 1111 (13.1%) | 24268 (15.9%) |
| timeout | 2336 (27.6%) | 56432 (37.0%) |

## Per year

| Year | N | mean(d) |
|---|---|---|
| 2011 | 1632 | +0.2169R |
| 2012 | 486 | -0.0846R |
| 2013 | 724 | -0.4608R |
| 2014 | 1474 | -0.3019R |
| 2015 | 1105 | -0.2691R |
| 2016 | 761 | -0.5562R |
| 2017 | 355 | -0.6013R |
| 2018 | 1105 | -0.0052R |
| 2019 | 828 | -0.3480R |

## Forward drift (reported, never gating)

Mean excess forward return in ATR14 units from the signal close, event minus its matched null.

| h (bars) | events | mean excess (ATR) |
|---|---|---|
| 5 | 8470 | -0.4982 |
| 10 | 8470 | -0.6237 |
| 20 | 8470 | -0.8106 |
| 60 | 8467 | -0.7187 |

Spearman rank correlation, raw event indicator vs h-bar forward return, member and warm bars pooled across tickers per year:

| Year | h=5 | h=10 | h=20 | h=60 |
|---|---|---|---|---|
| 2011 | +0.0133 | +0.0542 | +0.0179 | -0.0057 |
| 2012 | +0.0066 | -0.0182 | -0.0232 | -0.0391 |
| 2013 | -0.0380 | -0.0526 | -0.0536 | -0.0446 |
| 2014 | -0.0146 | -0.0380 | -0.0609 | -0.0484 |
| 2015 | -0.0631 | -0.0655 | -0.0446 | -0.0200 |
| 2016 | -0.0124 | -0.0358 | -0.0022 | -0.0167 |
| 2017 | -0.0217 | -0.0321 | -0.0285 | -0.0097 |
| 2018 | -0.0129 | +0.0075 | -0.0257 | -0.0039 |
| 2019 | -0.0469 | -0.0345 | -0.0500 | -0.0224 |

## Short-side blocks (descriptive, never gating)

**Event overlap** with `shock_support_break_short` (raw event bars on member, warm bars): 3391 of 9805 `shock_failed_bounce_short` bars (34.6%) are also `shock_support_break_short` bars; 3391 of 7956 `shock_support_break_short` bars (42.6%) are also `shock_failed_bounce_short` bars. Nested ideas are two looks at one hypothesis: read both results docs together (family of two, BH q above).

**Unconditional control** (`control_events`: the same trigger with the shock state ignored; same race, same matched null): N = 43835, ΔExpR -0.2011R, 95% week-clustered interval -0.2483R to -0.1526R. The idea's ΔExpR minus the control's: +0.0011R. A pass whose ΔExpR is not clearly above the control is not credited to the shock condition.

**SPY regime split** (SPY close vs its 200-day average at the last close before entry):

| SPY | N | ΔExpR |
|---|---|---|
| above its 200-day average | 6406 | -0.2795R |
| below its 200-day average | 2064 | +0.0467R |

Events with no SPY average before entry: 0.

## Shock read-outs (v211; descriptive, never gating)

Kept events N = 8470; skipped as overlapping an open race (`skipped_overlap`) = 973.

**Shock-day null** (K = 20 bars drawn only from this ticker's SHOCK days, no month or trend match; its own seeded stream): N = 8462, ΔExpR -0.0314R, 95% week-clustered interval -0.2307R to +0.1846R; events dropped for fewer than 5 SHOCK-day candidates: 8. The standard ΔExpR minus this one: -0.1686R. An edge that vanishes against this null is the market's drift after a shock day, not the stock trigger.

**Re-priced at 3 x slippage** (15.0 bps a side, both fills, events and standard null; shock-day spreads widen 2-5x): ΔExpR -0.1994R, 95% week-clustered interval -0.3831R to -0.0014R; change vs the base book +0.0006R. Printed, never gating.

**Gap split** (next open vs the signal close; the race fills the entry at that open, gap included, and a gap through the stop at the open):

| gap | N | mean R_event | ΔExpR (standard null) |
|---|---:|---:|---:|
| <= -1% | 777 | -0.2785R | -0.4127R |
| -1% .. +1% | 6459 | -0.2215R | -0.2057R |
| >= +1% | 1234 | -0.0861R | -0.0359R |

Events with no next open: 0.

**Day of the episode** (`peak`: the signal close is the episode's highest BREADTH_ATR1 so far, so the entry is the session after the breadth peak; `later`: any other SHOCK day of the episode):

| day | N | mean R_event | ΔExpR (standard null) |
|---|---:|---:|---:|
| peak | 7426 | -0.2214R | -0.2061R |
| later | 1044 | -0.1041R | -0.1563R |

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
| `screen-shock_failed_bounce_short` | 0.9996 |
