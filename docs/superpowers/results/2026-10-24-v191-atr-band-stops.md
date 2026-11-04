# v191 — Confluence ATR-band stops: results

**Spec (the pre-registration):** `docs/superpowers/specs/2026-10-24-v191-confluence-atr-band-stops-design.md`, last changed in `6966724d`. Stage 3 runs only with `--preregistration` naming that file.
**Plan:** `docs/superpowers/plans/2026-10-24-v191-confluence-atr-band-stops_0-index.md` (§ Global Constraints carries the frozen block below).
**Driver:** `scripts/backtest/measure_atr_band_stop.py`; stage files under `docs/superpowers/results/v191/`.

## Frozen before any run

- Claim: on confluence plans whose stop the floor moves, an ATR band (floor `k × ATR14`, ceiling `2 × ATR14`) with fixed-dollar sizing raises expectancy under the v92 harvest gate. Two arms, never pooled: arm K (keep TP1, drop under the minimum R:R) is primary; arm R (re-choose TP1) is second; Holm across the two on each arm's Stage 3 permutation p, an arm that never reached Stage 3 entering as p = 1.0; BH q reported, never gating.
- Prediction (falsifiable, per cell on the floor-moved stratum): ΔWR ≥ +4pp; arm K ΔExpR > 0; arm R ΔExpR < 0. A contradiction is recorded as a missed prediction.
- Grid `k ∈ {0.75, 1.0, 1.5}` (the partner's, uneven steps kept); ceiling `2.0 × a`, `a` = raw Wilder ATR14 / entry × 100 of completed bars through the creating bar.
- Decision stratum: floor-moved alone. Untouched and ceiling strata are reported, never counted towards a pass.
- Gate: v92 harvest (`acceptance_harvest.evaluate_harvest`): ΔExpR lower 95% bound > 0; Δ standardised WR lower bound ≥ −2.0pp; closed-trade cut ≤ 25%; permutation n = 200, p < 0.05, VALIDATION only. Week-clustered bootstrap.
- Stage −1: per-cell `refused:zero-diff` when the floor moves no plan; the arm is REACHABLE when any cell is. Stage 0: paired ΔExpR MDE on fold-train, a cell over +0.10R at power 0.80 refused; the arm is POWERED when any cell is. Stage 1: only powered cells are candidates; winner = highest ΔExpR with clauses 1–3 passing on fold-train and every existing grid neighbour within `plateau_report`'s 0.03R tolerance (all three cells are neighbours whether powered or not; an edge cell is adoptable with its one neighbour). Stage 2: folds 2021 / 2022 / 2023, at least 2 of 3 with positive ΔExpR at N ≥ 30. Stage 3: one VALIDATION shot per arm.
- Windows: fold-train 2018-06-01..2022-12-31; fold 2023 2023-01-01..2023-12-31; VALIDATION 2024-01-01..2025-12-31.
- Instrument v1; `data_source` alpaca (the v162 training-data store); universe `measure_arms.cached_universe()` with `MEASURE_ARMS_UNIVERSE=cache`; replay `gates=None` (live `ScanParams` through config).
- Frictions identical on both sides; a gap through a stop fills at the open; a fill past the stored ceiling is disclosed as `fill_beyond_ceiling`, never silently kept.
- Disclosed spec inconsistency: the spec's panel log says "0.05R tolerance frozen", while its § Gate (the binding text, after the plan-briefer correction) freezes `plateau_report`'s existing 0.03R. The § Gate text governs; the code uses 0.03R unchanged.

## Stage −1 (census, plans only, no outcome read)

### Arm K

**arm K stage -1: REACHABLE** (instrument v1, data alpaca)

plans today 9903; arm S overlap 6494; ATR missing 0

| cell | verdict | plans | floor | ceiling | untouched | newly_admitted | removed | band_rr_drop | band_no_target | band_size_zero | baseline_stop_exits | reversal | conc max | conc p95 | days over heat slots |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| k0.75 | REACHABLE | 35546 | 34024 | 19 | 1503 | 33971 | 8328 | 7042 | 551 | 0 | 5251 | 815 | 5178 | 4983.3000 | 1475 |
| k1 | REACHABLE | 18214 | 17799 | 19 | 396 | 17579 | 9268 | 7026 | 223 | 0 | 5251 | 1378 | 3346 | 3148.5000 | 1470 |
| k1.5 | REACHABLE | 4735 | 4671 | 19 | 45 | 4607 | 9775 | 4001 | 45 | 0 | 5251 | 2298 | 1157 | 984.7000 | 1433 |

| ATR14 % bucket | rows |
|---|---|
| 0.0-0.5 | 147 |
| 0.5-1.0 | 407 |
| 1.0-1.5 | 3509 |
| 1.5-2.0 | 10576 |
| 2.0-2.5 | 11342 |
| 2.5-3.0 | 8605 |
| 3.0-3.5 | 5727 |
| 3.5-4.0 | 3768 |
| 4.0-4.5 | 2355 |
| 4.5-5.0 | 1870 |
| 5.0-5.5 | 1317 |
| 5.5-6.0 | 1063 |
| 6.0-6.5 | 689 |
| 6.5-7.0 | 587 |
| 7.0-7.5 | 515 |
| 7.5-8.0 | 462 |
| 8.0-8.5 | 410 |
| 8.5-9.0 | 267 |
| 9.0-9.5 | 213 |
| 9.5-10.0 | 160 |
| 10.0-10.5 | 153 |
| 10.5-11.0 | 119 |
| 11.0-11.5 | 105 |
| 11.5-12.0 | 49 |
| 12.0-12.5 | 46 |
| 12.5-13.0 | 51 |
| 13.0-13.5 | 24 |
| 13.5-14.0 | 28 |
| 14.0-14.5 | 22 |
| 14.5-15.0 | 37 |
| 15.0-15.5 | 31 |
| 15.5-16.0 | 5 |
| 16.0-16.5 | 10 |
| 16.5-17.0 | 29 |
| 17.0-17.5 | 17 |
| 17.5-18.0 | 10 |
| 18.0-18.5 | 4 |
| 18.5-19.0 | 10 |
| 19.0-19.5 | 20 |
| 19.5-20.0 | 7 |
| 20.0-20.5 | 2 |
| 21.5-22.0 | 8 |
| 23.0-23.5 | 2 |
| 29.0-29.5 | 10 |
| 32.0-32.5 | 10 |

reachable cells [0.75, 1.0, 1.5]; identical adjacent []
### Arm R

**arm R stage -1: REACHABLE** (instrument v1, data alpaca)

plans today 9903; arm S overlap 6494; ATR missing 0

| cell | verdict | plans | floor | ceiling | untouched | newly_admitted | removed | band_rr_drop | band_no_target | band_size_zero | baseline_stop_exits | reversal | conc max | conc p95 | days over heat slots |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| k0.75 | REACHABLE | 40643 | 38612 | 95 | 1936 | 37840 | 7100 | 0 | 0 | 0 | 5251 | 815 | 5626 | 5321.4500 | 1476 |
| k1 | REACHABLE | 23032 | 22331 | 95 | 606 | 21476 | 8347 | 0 | 0 | 0 | 5251 | 1378 | 3838 | 3687.2000 | 1475 |
| k1.5 | REACHABLE | 7256 | 7037 | 103 | 116 | 6755 | 9402 | 0 | 0 | 0 | 5251 | 2298 | 1508 | 1413.2500 | 1454 |

| ATR14 % bucket | rows |
|---|---|
| 0.0-0.5 | 140 |
| 0.5-1.0 | 396 |
| 1.0-1.5 | 3456 |
| 1.5-2.0 | 10312 |
| 2.0-2.5 | 10798 |
| 2.5-3.0 | 8132 |
| 3.0-3.5 | 5061 |
| 3.5-4.0 | 3204 |
| 4.0-4.5 | 1953 |
| 4.5-5.0 | 1554 |
| 5.0-5.5 | 1100 |
| 5.5-6.0 | 913 |
| 6.0-6.5 | 619 |
| 6.5-7.0 | 541 |
| 7.0-7.5 | 479 |
| 7.5-8.0 | 405 |
| 8.0-8.5 | 388 |
| 8.5-9.0 | 255 |
| 9.0-9.5 | 190 |
| 9.5-10.0 | 140 |
| 10.0-10.5 | 151 |
| 10.5-11.0 | 119 |
| 11.0-11.5 | 104 |
| 11.5-12.0 | 49 |
| 12.0-12.5 | 43 |
| 12.5-13.0 | 50 |
| 13.0-13.5 | 24 |
| 13.5-14.0 | 28 |
| 14.0-14.5 | 22 |
| 14.5-15.0 | 37 |
| 15.0-15.5 | 31 |
| 15.5-16.0 | 5 |
| 16.0-16.5 | 10 |
| 16.5-17.0 | 28 |
| 17.0-17.5 | 17 |
| 17.5-18.0 | 10 |
| 18.0-18.5 | 4 |
| 18.5-19.0 | 10 |
| 19.0-19.5 | 20 |
| 19.5-20.0 | 7 |
| 20.0-20.5 | 2 |
| 21.5-22.0 | 8 |
| 23.0-23.5 | 2 |
| 29.0-29.5 | 10 |
| 32.0-32.5 | 10 |

reachable cells [0.75, 1.0, 1.5]; identical adjacent []
Arm K: verdict REACHABLE, reachable_cells [0.75, 1.0, 1.5], no identical-adjacent cells; per-horizon/direction counts are in the file's `by_stratum`.

Arm R: verdict REACHABLE, reachable_cells [0.75, 1.0, 1.5], no identical-adjacent cells; per-horizon/direction counts are in the file's `by_stratum`.

Census sanity check (plan V191-20 Step 7): `census sane`; `plans_today` 9903 and `arm_s_overlap` 6494 match across arms. Both census rows files are under 50 MB (K 32,016,946 B, R 29,560,136 B) and are committed.

## Arm K (primary)

**Verdict: UNDERPOWERED at Stage 0, budget intact.** Arm K closes at Stage 0; Stages 1-3 did not run, so its VALIDATION shot is not spent. Evidence: `docs/superpowers/results/v191/2026-10-24-v191-armK-stage0.json`.

### Stage 0

**arm K stage 0: UNDERPOWERED** (instrument v1, data alpaca)

| cell | stratum N | paired N | newly admitted | observed N | target N | MDE R |
|---|---|---|---|---|---|---|
| k0.75 | 39492 | 728 | 32075 | 728 | 318 | 0.1489 |
| k1 | 25407 | 357 | 16798 | 357 | 156 | 0.1855 |
| k1.5 | 13709 | 77 | 4439 | 77 | 34 | 1.0390 |

powered cells [] (ceiling 0.1R, power 0.8)

### Prediction

Prediction not scored (closed before Stage 1).

### Disclosures

No Stage 1 report exists, so there are no component-side dollar-exceedance counts to disclose. Sanity conditions passed: no cell has `paired_n > stratum_n`, none has `observed_n == 0`, and every cell is in Stage −1's `reachable_cells`.

### Observations

Every cell has observed N above its target N, yet none meets the 0.10R MDE ceiling. The cause is paired-row scarcity: only 728 / 357 / 77 paired rows come from tens of thousands of stratum rows, because most band plans are newly admitted and have no baseline twin. The ceiling, windows and cells are frozen and are not widened.
