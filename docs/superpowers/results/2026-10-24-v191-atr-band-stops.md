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
