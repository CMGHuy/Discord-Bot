# v92 Hypothesis 1 — R-adaptive chandelier trail — TRAIN grid

Plan v92 Task 7. One TRAIN-window sweep over Hypothesis 1's two parameters
(`TIGHTEN_TRIGGER_R`, `TIGHTEN_ATR_MULT`), baseline vs. component scored per
cell against the same `evaluate_harvest` harvest-acceptance gate built in
Tasks 1-3 (`scripts/backtest/measure_adaptive_trail.py`). Raw per-ticker log
archived at `docs/superpowers/results/2026-09-23-v92-adaptive-trail-h1.log`.

## Setup

- **Window:** TRAIN 2020-01-01..2023-12-31.
- **Tickers:** full 77-symbol watchlist targeted; 75 of 77 present in the
  backtest cache and run (`CRWV`, `SNDK`, `SPCX` absent — the same cache gap
  as the main repo, not specific to this run; the script's per-ticker `None`
  skip handled the absence gracefully and consistently across the baseline
  and all 9 grid cells).
- **Horizons x strategies:** all 10 horizons (`2w`…`9m`) x all 11
  `ALL_STRATEGIES`, `exit_model="v2"`, `scale_out=True` throughout —
  Hypothesis 1 lives entirely in that exit path.
- **Wall-clock:** 1h 31m (10 passes: 1 baseline + 9 grid cells). Exit 0, no
  errors.

## Baseline

```
Baseline (flag off), 75 tickers...
  4258 closed trades
Stage 0 MDE (ExpR, target_n=4258): +0.2409R
```

## The nine-cell grid

| trigger_r | tighten_mult | n | dExpR | lo95 | expect | wr_floor | volume |
|---:|---:|---:|---:|---:|---|---|---|
| 1.50 | 1.50 | 4258 | +0.0081 | -0.0151 | FAIL | PASS | PASS |
| 1.50 | 1.75 | 4258 | +0.0018 | -0.0128 | FAIL | PASS | PASS |
| 1.50 | 2.00 | 4258 | -0.0045 | -0.0174 | FAIL | PASS | PASS |
| 2.00 | 1.50 | 4258 | +0.0081 | -0.0151 | FAIL | PASS | PASS |
| 2.00 | 1.75 | 4258 | +0.0019 | -0.0127 | FAIL | PASS | PASS |
| 2.00 | 2.00 | 4258 | -0.0043 | -0.0172 | FAIL | PASS | PASS |
| 2.50 | 1.50 | 4258 | +0.0091 | -0.0131 | FAIL | PASS | PASS |
| 2.50 | 1.75 | 4258 | +0.0027 | -0.0116 | FAIL | PASS | PASS |
| 2.50 | 2.00 | 4258 | -0.0041 | -0.0172 | FAIL | PASS | PASS |

## Observations

- **Every cell's lower-95% bound stays negative.** `expectancy_gain`
  requires the bootstrap lower bound to clear zero; the best cell
  (trigger=2.50, mult=1.50) still sits at `lo95=-0.0131`, nowhere close to
  clearing the bar. No cell PASSes.
- **The deltas are tiny relative to what this population can even detect.**
  `dExpR` ranges from -0.0045R to +0.0091R across all nine cells, against a
  Stage 0 MDE of +0.2409R — this population (N=4258) could only reliably
  detect an effect roughly 25-50x larger than anything any cell actually
  shows. This reads as "no effect at this population size," not "a real
  effect this test happens to be underpowered to see" — the observed deltas
  aren't hovering just under a tight detection threshold, they're two orders
  of magnitude below a loose one.
- **`win_rate_floor` and `volume_floor` both PASS everywhere, as expected.**
  Hypothesis 1's mechanism (the adaptive trail) only acts after the
  win/loss decision (post-TP1), so it cannot move win rate by construction
  — consistent with the spec and with `structurally_immune_to_wr=True`
  being the correct flag to pass here, not an unjustified relaxation.
- **No discernible plateau favoring any particular corner of the grid.** The
  sign of `dExpR` mostly tracks `tighten_mult` (tighter multipliers —
  `mult=2.00` — trend more negative at every `trigger_r`) rather than
  `trigger_r` itself, but even the best-performing corner of the grid
  (`trigger_r=2.50, tighten_mult=1.50`) still fails on the lower bound. There
  is no cluster of neighboring cells clearing `expectancy_gain` together —
  per `docs/claude/backtest-methodology.md` Stage 1's plateau requirement, a
  single spiking cell with non-clearing neighbors would not have been enough
  to proceed even if one cell had PASSed; here none does, so the plateau
  question is moot.

## Verdict

**No cell clears the `expectancy_gain` clause. Per the pre-registered
stopping rule, Hypothesis 1 (R-adaptive chandelier trail) closes here on
TRAIN — Tasks 8 (Stage 2 walk-forward folds) and 9 (Stage 3 VALIDATION shot)
are not run; VALIDATION's one-shot budget for this hypothesis is preserved
unspent.** `ADAPTIVE_RUNNER_TRAIL_ENABLED` stays default `false` — ships
inert, exactly like `mfe_informed_tp2_r` and this repo's other closed-negative
flags.
