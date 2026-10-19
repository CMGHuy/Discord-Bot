# v178 — Pre-registered test of runner give-back levels: range-multiple and profit-share arms

**Version:** ui 1.31.0 · bot 2.12.0 (at writing)
**Bump:** bot patch — Phase A adds inert simulator modes behind a default that leaves the live v176 rule byte-identical; nothing the user sees changes. Phase B (live parity) exists only if an arm passes the one-shot VALIDATION, and is then its own spec.
**Edge:** harvest — locks in more of a runner's run before a reversal. Prediction: a small paired ΔExpR against the live fixed 5% (|Δ| under 0.05R; the v176 5% rule measured +0.003R and the two earlier tighter-trail rules measured near zero), sign unknown.
**Screen:** harvest-headroom docs/superpowers/results/2026-10-02-v123-runner-headroom.md
**Panel:** risk-manager, veteran-trader, quant-researcher
**Status:** spec written 2026-10-19 from a chat with the partner, who asked for a pullback level that adapts to each trade instead of one fixed percentage, and chose to test both families as separate arms.

## Why

The v176 give-back stops the runner 5% off its best price. Its TRAIN measurement
(`docs/superpowers/results/2026-10-19-v176-giveback-train.md`) was NO-LIFT: ΔExpR
+0.0030R, interval [−0.0124, +0.0159] on the close basis, +0.0100R,
[−0.0071, +0.0258] on the high/low basis. Of the 334 give-back exits, 157 (47%)
were followed by a new best price within 10 daily bars.

A fixed 5% is a different bet on each stock. On a name whose daily range is 8%
of price (RKLB, ATR 4.16 on a 60.67 entry) 5% is about 0.6 of one day's normal
move, so ordinary noise can end the runner. On a calm name it is more than two
days' range. The partner's question: what pullback should end a runner so it
takes profit before the move reverses and gives everything back, with no hard
limit assumed?

This spec does not claim an answer. It pre-registers a small set of
adaptive rules, written down before any is run, and puts them through the
repo's harvest funnel.

## The rules (all frozen before any result is read)

Every rule is another tightening term on the runner stop, exactly the shape of
the v176 give-back: `stop = tightest(existing stop, level)`, active from the
bar after the best price is set, long mirror and short mirror. `E` is the
runner's best price since TP1, `ATR_j` the daily ATR(14) at the bar being
processed, `entry` the original fill.

| Family | Level (long: `E − allowance`, short: `E + allowance`) | Arms |
|---|---|---|
| **R, range multiple** | `allowance = k × ATR_j` | `k` ∈ {0.75, 1.0, 1.25} |
| **S, profit share with a range floor** | `allowance = max(f × |E − entry|, 1.0 × ATR_j)` | `f` ∈ {0.25, 0.33, 0.50} |
| control A | the live v176 rule, fixed 5% of `E` | 1 |
| control B | no give-back (flag off) | 1 |

- Six candidate arms (R×3, S×3) and two controls. `k` stays below 1.5 on
  purpose: v92 `ADAPTIVE_RUNNER_TRAIL` already tested the chandelier multiple
  at {1.5, 1.75, 2.0} after a trigger profit and closed with no lift
  (`backtest-methodology.md` § Closed pre-registrations). That grid is not
  re-run; family R covers lower multiples, applied from TP1.
- The floor in family S is fixed at 1.0 × ATR and is not a grid axis, so the
  range-multiple behaviour is not reopened through the back door.
- Worked example, RKLB short (entry 60.67, `E` = 49.94, profit 10.73, ATR
  4.164): fixed 5% exits at 52.44; R 0.75/1.0/1.25 at 53.06 / 54.10 / 55.14;
  S 25/33/50% at 54.10 / 54.10 / 55.31 (the floor binds for the first two).
  This is arithmetic, not a result.

## Not the Stage −2 screen

An exit rule is not an entry idea, so no `SCREEN-PASS` row applies. The
`**Screen:**` line cites the v123 headroom measurement, as v176 does. This is
`Edge: harvest`, so it states the gate it uses instead of the acceptance funnel:
the harvest gate (`acceptance_harvest.evaluate_harvest`, v92) through the same
four stages.

## The test, stage by stage

The comparison is **paired on the same entries**, against the live fixed 5%
(control A) as the baseline. Control B is reported for context.

| Stage | Window | What happens | Closes the arm if |
|---|---|---|---|
| −1 reachability | pilot | the arm's knob is reachable by replay and changes at least one outcome | unreachable, or zero changed outcomes: refused, budget intact |
| 0 MDE | fold-train | paired MDE (`acceptance.mde_paired`) against the arm's expected effect | TRAIN effect below the MDE: shot refused, budget intact |
| 1 plateau | fold-train (2018-06..2020 / ..2021 / ..2022) | `plateau_report()` (`backtest_wf.py:36`) within each family, over its three arms, mandatory and disqualifying | a spike with unstable neighbours: closed |
| 2 walk-forward | fold-test 2021 / 2022 / 2023 | at least 2 of 3 folds improving, no fold worse than −1.0pp, per-fold N ≥ 30 | fails: closed |
| 3 validation | 2024-01-01..2025-12-31 | **one shot**, for the single surviving arm, all clauses of the harvest gate | any clause fails: closed; the live 5% stays |

- At most **one** arm reaches stage 3: the one with the best stage-2 result among
  those that passed stage 1. If both families have survivors, the larger mean
  paired ΔExpR across the three folds goes through; the other is closed
  unspent. Ties go to the lower-complexity rule (family R).
- Multiple comparisons: six candidates are looked at at stage 1. The result
  reports the number looked at, a Holm-adjusted p across the six, and appends
  one ledger row per candidate (so `ledger_qvalues` counts every look). A
  per-family reading is descriptive; the funnel's pass rule is the gate.
- The harvest gate's `win_rate_floor` is `SKIPPED` (a post-TP1 rule cannot move
  the TP1-touch win rate) and `volume_floor` does not apply (the count of
  trades is unchanged). Win→non-win outcome flips are disclosed.
- Frictions: non-zero slippage and commission in every arm, from
  `swingbot/core/edge/frictions.py`.
- Data source `yfinance`, the 75-ticker cache, both engines, all ten horizons,
  `scale_out=True`, instrument v1, TRAIN-side windows only before stage 3.
  Stated in the frozen block before any window is read.
- The v176 measurement already read TRAIN for control A only. Control A's numbers
  are known; this is disclosed, and it sets no threshold here.

## Phases

**Phase A: simulator and measurement (this spec).** Add the two families to
`giveback_stop` and to the simulators, behind
`RUNNER_GIVEBACK_MODE` ∈ {`pct` (default), `range`, `profit_share`} plus the
arm parameters, via the standard arm producer (`measure_arms.py`, v100).
The default `pct` keeps the live v176 rule and all existing tests unchanged.
Nothing in `plan_manager.py` changes. The new fields are `_SEARCH_CLASSES`
"excluded" until reachability requires otherwise (`scan_params`,
`reachability` edits only where the funnel needs them).

**Phase B: live parity, only after a stage-3 pass.** The live tick path and the
bar catch-up path need the arm's level from `atr_fn` and the stored extreme.
That is a separate spec, its own panel, and the partner's go-ahead. Until then
production keeps the fixed 5%.

## Out of scope

- Changing the live percentage or turning the v176 rule off.
- Any entry idea, TP1 or TP2 change, or sizing.
- A grid larger than the six arms above. A result that suggests a different
  level (a `k` of 0.5, a different `f`) is a new pre-registration, not a tweak.

## Risks

- **Six arms at roughly 0.01R effects.** The earlier tests of similar rules
  closed near zero. The most likely outcome is NO-LIFT at stage 1 or 0. That
  is a finished result, and the 5% stays live.
- **A volatility-scaled stop can be wide in a real drawdown.** A 1.25 × ATR
  allowance on a name with an 8% daily range is a 10% give-back. The
  measurement reports max drawdown and dollars at fixed risk, off against on,
  per arm, as a separate descriptive block. They never gate, and a better
  paired ΔExpR with a deeper drawdown goes to the partner as a trade-off.
- **Live differs from the simulator.** The simulator trails the best close, the
  live bot trails the best tick. v176 measured the gap (+0.003R against
  +0.010R). Any stage-3 pass is read together with a high/low sensitivity run
  on the survivor, as v176 did.
- **Real-money orders.** The bot moves only its paper stop. A rule that is
  wider than the live 5% would move the paper stop less often; any switch of the
  live rule needs the partner to move broker stops by hand.

## Testing

- `giveback_stop` for each family: long, short, the floor binding and not
  binding, `E` at entry (zero profit), parameter bounds.
- Simulator parity: `pct` mode is byte-identical to the v176 simulator on an
  existing fixture; each new mode gives a constructed run-up-and-reversal exit
  at the hand-derived level (RKLB arithmetic above); `exit_sim` and
  `exit_sim_v2` agree on every arm.
- No lookahead: a level is built from the extreme and ATR of the bars before
  the one tested, effective the next bar.
- Funnel plumbing: reachability classifies each knob; stage files refused when
  unstamped or wrong-stage; a result file never overwritten.
- The live path is untouched: the existing v176 tests pass unmodified.

## Panel review

(filled after the panel runs)
