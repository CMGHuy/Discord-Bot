# v128 pre-registration — FVG lift audit: all vs off vs displacement-only

**Status:** frozen before any arm was produced. Recorded at worktree HEAD `59fc9314` on `2026-10-07 17:19` UTC.
**Spec:** `docs/superpowers/specs/2026-10-02-v128-fvg-displacement-audit-design.md`
**Plan:** `docs/superpowers/plans/2026-10-02-v128-fvg-displacement-audit_0-index.md`
**Edge:** expectancy. Not a re-run of any closed row: FVG has never been lift-tested (v49 measured redundancy only).

## Claim

Removing FVG levels entirely (`off`), or keeping only gaps whose middle candle is a displacement candle (`displacement`), improves the scan under **both** the v72 win-rate gate and the v92 harvest gate.

## Arms (frozen grid; no table from any stage may move it)

| Candidate id | `measure_arms.py` knobs |
|---|---|
| baseline | none (`FVG_LEVELS_MODE=all`) |
| `off` | `--knob FVG_LEVELS_MODE=off` |
| `disp-1.0` | `--knob FVG_LEVELS_MODE=displacement --knob FVG_DISPLACEMENT_ATR_K=1.0` |
| `disp-1.5` | `--knob FVG_LEVELS_MODE=displacement --knob FVG_DISPLACEMENT_ATR_K=1.5` |
| `disp-2.0` | `--knob FVG_LEVELS_MODE=displacement --knob FVG_DISPLACEMENT_ATR_K=2.0` |

Displacement (causal): with `m = bar_index − 1`, `|C[m] − O[m]| ≥ k·ATR14[m]` (`indicators.atr(df, 14)`). A bullish gap needs `C[m] ≥ L[m] + ⅔(H[m] − L[m])`; a bearish gap needs `C[m] ≤ L[m] + ⅓(H[m] − L[m])`. A non-finite or ≤ 0 ATR is not displacement. The filter runs after the freshest-3-per-side truncation. A filtered gap leaves both the vote and the candidate prices; charts are unchanged.

## Stages, instruments and pass rules

A candidate advances only if it passes **both** gates at a stage. A candidate refused at Stage −1 or Stage 0 under either gate is ineligible at Stage 1. Its selection arm is still produced and scored, because its ΔExpR is the plateau neighbour value for an adjacent `k`.

| Stage | Producer (`measure_arms.py --stage`) | Judge | Pass |
|---|---|---|---|
| −1 reachability | `pilot` (2018-06-01..2020-12-31, first 10 cached tickers) | `validate_component.py --stage reachability`, run once with `--gate win_rate` and once with `--gate harvest`. The stage ignores `--gate`, so both runs give the same verdict | `REACHABLE` (changed outcomes > 0) |
| 0 MDE | `selection` (fold-train 2018-06-01..2022-12-31, full universe, all horizons) | `validate_component.py --stage mde`, paired MDE. `--gate win_rate --train-effect-pp <pooled ΔWR>` and `--gate harvest --train-effect-r <pooled ΔExpR>`, both printed by `fvg_select.py effects` | `RESOLVABLE` under both |
| 1 selection | the same `selection` arms (pooled top level) | `fvg_select.py select` | verdict `selected` |
| 2 walk-forward | `walkforward` (test years 2021 / 2022 / 2023) | `validate_component.py --stage walkforward`, `--gate win_rate` (`gate_win_rate`) and `--gate harvest` (`backtest_wf.gate`) | `PASS` under both |
| 3 VALIDATION | `validation` (2024-01-01..2025-12-31), the single Stage-1 winner, **one shot, total** | `validate_component.py --stage validation`. `--gate win_rate --permutation-p <ΔWR p> --mechanism-json <clause 6>` and `--gate harvest --permutation-p <ΔExpR p>` | `PASS` under both. A missing p is a FAIL |

## Frozen resolutions (the spec assumed tooling that did not exist; resolved here before any arm)

- **R1, harvest walk-forward rule.** `acceptance_harvest.py` has none, and v92 reused the funnel "as-is". The v92 Stage 2 rule is therefore the existing pre-registered expectancy fold gate, `backtest_wf.gate()`: ≥ 2 of 3 test folds with ΔExpR > 0, no fold below −0.05R, and per-fold N ≥ 30. N is the min closed-trade count (win/loss/scratch/timeout) of the two arms. No new constant.
- **R2, Stage 1 clauses and window.** Scored on the pooled fold-train arms (the selection blob's top level, 2018-06-01..2022-12-31). The fold-train-applicable clauses are v72 `win_rate`, `profit_floor`, `geometry`, `volume` and `mechanism` (clause 6 per R5), evaluated with `acceptance.evaluate(stage="walkforward")`, plus v92 `expectancy_gain`, `win_rate_floor` and `volume`, evaluated with `evaluate_harvest(stage="walkforward", structurally_immune_to_wr=False)`. Permutation is validation-only. Every listed clause must be `PASS`; `SKIPPED` does not count as a pass.
- **R3, plateau.** `backtest_wf.plateau_report("FVG_DISPLACEMENT_ATR_K", [1.0, 1.5, 2.0], <pooled ΔExpR per k>, k)` must return `is_plateau: True` (tolerance 0.03R), **and** at least one grid neighbour of `k` must be eligible. `off` is a one-point arm: `plateau_report` would return `is_plateau: True` vacuously, so it is not called. `off` is eligible on its clauses alone (v35's AVWAP on/off precedent). A missing ΔExpR on `k` or a neighbour fails the plateau.
- **R4, one winner.** Among contenders (eligible `off`; eligible `k` that pass R3), take the largest pooled ΔExpR, compared at 4 decimal places. On a tie, the smaller v72 alert cut (2 decimal places). Then `displacement` over `off`. Then the smaller `k` (it keeps more gaps, so it is the smaller change). No contender: `no-eligible-cell` if nothing is eligible, else `spike`.
- **R5, clause 6 (the spec's frozen amendment), as computed.** Scored on the **baseline** arm by `fvg_attribution.py` from one replay of the baseline confluence arm per stage.
  - **Confluence trade, vote:** at the signal bar's window, `FVG` is among the families `count_confirming_strategies(..., take_profit, 5.0)` returns with every gap, and absent once the candidate's filtered FVG candidates are removed.
  - **Confluence trade, price:** at the bar whose level map the replay actually used (`levels_asof`), the scenario's stop cluster or the plan's TP1 cluster contains an FVG member whose price is a filtered gap's midpoint.
  - **Entry:** confluence plans enter at the signal bar's close, never at a level, so entry provenance is structurally empty.
  - **Strategy trade:** there is no confluence vote, and the TP2/lifecycle level provenance is not recorded, so a pairing proxy applies. "Price" holds iff the key is absent from the candidate arm, or its outcome or `r_multiple` differs.
  - Removed = vote or price; retained = every other baseline trade. PASS iff removed WR < retained WR and removed ExpR ≤ 0. Either population lacking decided trades is a FAIL.
- **R6, clause 5 / v92 `not_luck`.** v72 clause 5 uses v122's `permutation_test.py --arms <validation arms> --n 200 --seed 42` (ΔWR p). v92 clause 4 is on ΔExpR, which v122's extension does not produce. V128-12 adds `--statistic expectancy` to the same function: same null-arm construction (per-ticker circular label shift in [20, 200), replacements kept), with the share of null ΔExpR ≥ observed. It is not a second instrument. If v122's extension is not on `main` at Stage 3, the plan stops before VALIDATION with the budget unspent.
- **R7, Stage 0 claims.** The claimed TRAIN effects are the pooled selection-window ΔWR (pp) and ΔExpR (R), as printed. A `null` or ≤ 0 claim is passed as `0`, which is refused, correctly.
- **R8, reporting.** Every stage writes one results file with an attribution table per live candidate (vote-only / price-only / both / unaffected, removed vs retained WR/ExpR, per direction, top-2 horizon share flagged above 80%, replacement count). That table is diagnostic and never a gate. Stage 1 adds the FVG-in-families context slice, labelled confounded.
- **R9, one shot.** The validation arms file is produced once. A crash in any scoring step after it may be re-run on that same file; the file is never regenerated, and nothing is retuned after it.

## Outcomes

PASS (both gates at Stage 3): `FVG_LEVELS_MODE` defaults to the winner (and `FVG_DISPLACEMENT_ATR_K` to its `k`), in its own commit, released as a bot patch. Any other outcome: default stays `all`, code merged inert. Either way, a row is added to `docs/claude/backtest-methodology.md` § Closed pre-registrations.
