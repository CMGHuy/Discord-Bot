# v92 Hypothesis 1 — R-adaptive chandelier trail — TRAIN grid

Plan v92 Task 7. One TRAIN-window sweep over Hypothesis 1's two parameters
(`TIGHTEN_TRIGGER_R`, `TIGHTEN_ATR_MULT`), baseline vs. component scored per
cell against the same `evaluate_harvest` harvest-acceptance gate built in
Tasks 1-3 (`scripts/backtest/measure_adaptive_trail.py`). Raw per-ticker log
was written to `docs/superpowers/results/2026-09-23-v92-adaptive-trail-h1.log`
during this run for cross-checking at the time; not committed --
`.gitignore` excludes `docs/superpowers/results/*.log`, so it does not
persist past this worktree.

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
| 1.50 | 1.50 | 4258 | +0.0081 | -0.0151 | FAIL | SKIPPED | PASS |
| 1.50 | 1.75 | 4258 | +0.0018 | -0.0128 | FAIL | SKIPPED | PASS |
| 1.50 | 2.00 | 4258 | -0.0045 | -0.0174 | FAIL | SKIPPED | PASS |
| 2.00 | 1.50 | 4258 | +0.0081 | -0.0151 | FAIL | SKIPPED | PASS |
| 2.00 | 1.75 | 4258 | +0.0019 | -0.0127 | FAIL | SKIPPED | PASS |
| 2.00 | 2.00 | 4258 | -0.0043 | -0.0172 | FAIL | SKIPPED | PASS |
| 2.50 | 1.50 | 4258 | +0.0091 | -0.0131 | FAIL | SKIPPED | PASS |
| 2.50 | 1.75 | 4258 | +0.0027 | -0.0116 | FAIL | SKIPPED | PASS |
| 2.50 | 2.00 | 4258 | -0.0041 | -0.0172 | FAIL | SKIPPED | PASS |

(`wr_floor` recorded here as `SKIPPED`, matching the corrected implementation
-- a whole-branch review found `_clause_win_rate_floor`'s `structurally_immune=True`
path returned the verdict string `"PASS"` instead of `"SKIPPED"` at the time
this grid ran; the underlying immunity fact and every other number in this
table are unchanged, only the printed verdict string for that one clause.)

## Observations

- **Every cell's lower-95% bound stays negative.** `expectancy_gain`
  requires the bootstrap lower bound to clear zero; the best cell
  (trigger=2.50, mult=1.50) still sits at `lo95=-0.0131`, nowhere close to
  clearing the bar. No cell PASSes.
- **The deltas are tiny relative to the interval widths actually observed.**
  `dExpR` ranges from -0.0045R to +0.0091R across all nine cells. The
  Stage 0 MDE (+0.2409R) is cited here only as a sanity check on grid
  design, not as the basis for "no effect": `mde_expectancy_r` computes an
  UNPAIRED-design MDE, and this comparison is paired (the same entries
  replayed under two exit rules), for which the true detectable-effect size
  is considerably smaller than +0.2409R (see the caveat on
  `acceptance_harvest.mde_expectancy_r` and `docs/claude/backtest-
  methodology.md`'s "Harvest acceptance gate" section) — so citing the raw
  MDE number here would overstate what this population can rule out. The
  defensible reading instead comes from the bootstrap confidence intervals
  actually reported per cell above: every cell's `lo95` sits in a narrow
  band (-0.0116R to -0.0174R), and the widest of those magnitudes
  (~0.017R) already bounds what these intervals rule out at this sample
  size — an order of magnitude tighter than the unpaired MDE would suggest,
  and still comfortably clear of every observed `dExpR`. "No effect at this
  population size" is the correct conclusion; it is grounded in the
  interval widths, not in the MDE figure.
- **`win_rate_floor` reports SKIPPED at every cell, `volume_floor` PASSes
  everywhere, both as expected.** Hypothesis 1's mechanism (the adaptive
  trail) only acts after the win/loss decision (post-TP1), so it cannot
  move win rate by construction — consistent with the spec and with
  `structurally_immune_to_wr=True` being the correct flag to pass here, not
  an unjustified relaxation. (A whole-branch review after this grid ran
  found the harvest gate's implementation printed `"PASS"` for this
  structurally-immune path instead of `"SKIPPED"`; the table above reflects
  the corrected verdict string, not a re-run — every number besides that
  one label is unchanged.)
- **Win→non-win outcome-flip disclosure (spec §3):** structurally zero at
  every cell. The mechanism only ever touches the runner leg after TP1,
  which has already banked the win/loss decision before Hypothesis 1's code
  runs — no trade can flip win→non-win (or the reverse) under this
  hypothesis, by construction, so there is nothing to tabulate.
- **No discernible plateau favoring any particular corner of the grid.**
  `TIGHTEN_ATR_MULT` values 1.50/1.75/2.00 are all tighter than the base
  `TRAIL_ATR_MULT=2.5` (by construction — `min(base, TIGHTEN_ATR_MULT)` in
  `_effective_trail_mult`), so `mult=1.50` is the TIGHTEST of the three
  tested and `mult=2.00` the LOOSEST, not the reverse. The sign of `dExpR`
  tracks `tighten_mult` in that direction: **looser multipliers (`mult=2.00`)
  trend more negative** at every `trigger_r`, while the tightest
  (`mult=1.50`) is the least-bad column throughout. Even so, the
  best-performing corner of the grid (`trigger_r=2.50, tighten_mult=1.50`)
  still fails on the lower bound. There is no cluster of neighboring cells
  clearing `expectancy_gain` together — per `docs/claude/backtest-
  methodology.md` Stage 1's plateau requirement, a single spiking cell with
  non-clearing neighbors would not have been enough to proceed even if one
  cell had PASSed; here none does, so the plateau question is moot.
- **Two cells are bit-identical** (`trigger_r=1.50/mult=1.50` and
  `trigger_r=2.00/mult=1.50`, both `dExpR +0.0081R`, `lo95 -0.0151`). This is
  not a data artifact: `runner_r` is measured since entry, and `extreme_close`
  starts at the TP1 bar's close, and TP1 sits at 1.5-2.5R (this codebase's
  frozen `MIN_RISK_REWARD_RATIO`/`MAX_RISK_REWARD_RATIO` band, `config.py`,
  the same band `plan_engine.select_structural_target` picks every plan's
  target inside). So `TIGHTEN_TRIGGER_R=1.5` fires on essentially the first runner bar for
  nearly every trade, and `TIGHTEN_TRIGGER_R=2.0` does too for any plan with
  planned RR >= 2 — the two trigger values are frequently indistinguishable
  in practice at this grid's tightest tested multiplier, not a bug. What was
  really measured here is closer to "a tighter trail from TP1" for the
  tighter trigger/mult combinations; only the `trigger_r=2.50` row
  meaningfully tests genuine R-adaptivity (a runner that has to bank real
  R since entry, beyond what TP1 itself already implies, before the trail
  tightens). Separately, `params.py`'s per-strategy base trail multipliers
  confirm one more reason the `mult=2.00` column is weaker evidence than it
  looks: RSI, MACD and RSI Divergence all use a base `trail_atr_mult=2.0`
  (not the 2.5 default), so `min(2.0, TIGHTEN_ATR_MULT=2.00)` is a genuine
  no-op for those three strategies specifically — the `mult=2.00` column
  measures nothing at all for roughly a third of `ALL_STRATEGIES` and only a
  real (if loose) tightening for the rest. Reopening a trigger measured from
  TP1 itself (not since entry) would be a genuinely new mechanism, not a
  re-run of this one.

## Verdict

**No cell clears the `expectancy_gain` clause. Per the pre-registered
stopping rule, Hypothesis 1 (R-adaptive chandelier trail) closes here on
TRAIN — Tasks 8 (Stage 2 walk-forward folds) and 9 (Stage 3 VALIDATION shot)
are not run; VALIDATION's one-shot budget for this hypothesis is preserved
unspent.** `ADAPTIVE_RUNNER_TRAIL_ENABLED` stays default `false` — ships
inert, exactly like `mfe_informed_tp2_r` and this repo's other closed-negative
flags. Caveat for the record, since the flag is closed and will not be
revisited without a new pre-registration: the adaptive trail is wired into
the backtest walk only (`exit_sim.py`'s `_effective_trail_mult`) — the live
poll path (`plan_manager.py`) still calls `chandelier_stop` with the plan's
raw `trail_atr_mult` directly and was never wired to this mechanism, so
flipping this flag true today would silently diverge live behavior from
backtest.
