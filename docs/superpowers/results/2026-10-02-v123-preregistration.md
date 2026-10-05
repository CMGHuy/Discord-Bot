# v123 pre-registration -- structure-aware runner exit

**Written before any outcome is read.** No backtest was run and no arm outcome
file was opened to write this record. Spec:
`docs/superpowers/specs/2026-10-02-v123-runner-structure-exit-design.md`.
**Edge:** harvest.

## Gate and funnel

The v72 funnel is **not** used. The gate is the **v92 harvest gate**
(`acceptance_harvest.py`). `backtest-gate` Steps 1-3 were run: the authority
(`docs/claude/backtest-methodology.md`) was read and the closed
pre-registrations table checked by component and mechanism.

**Closed-table check.** Neither arm is a closed row:

- v92 H1 `ADAPTIVE_RUNNER_TRAIL_ENABLED` (measured null) tightened the ATR
  multiplier after an R trigger. `hl_trail` uses swing pivots, not ATR
  multiples of the extreme.
- v92 H2 `STALL_EXIT_ENABLED` (unmeasurable) was pre-TP1 and time-based.
  `progress_stall` is runner-only, structure-triggered, and measured through
  the arm engines' `scale_out=True` walk, which `stall_exit_day` never reached.
- v104 structural stops (no lift) concerned the initial stop. v123 never
  touches the initial stop or anything before TP1.

Funnel stage being registered: the full harvest funnel (Stage -1, Stage 0 MDE,
Stage 1 fold-train selection, Stage 2 walk-forward, Stage 3 VALIDATION), one
arm at a time. Only Stage 3 draws on the one-shot budget.

## Hypothesis (quoted from the spec)

> **Pre-registered claim:** replacing or supplementing the runner's chandelier
> trail with a structure-defined rule raises pooled ExpR on identical entries,
> under the v92 harvest gate.

Basis: lessons 2 and 4 of `docs/strategy/volume-in-context.md` (HH/HL on
cooling volume is not an exit reason; a broken higher low, or a failed higher
high **together with** contracting candle range and cooling volume, is).

**Arm `hl_trail` -- structural trailing floor** (bullish shown, bearish
mirrors; only pivots with index after the entry bar count):

> At the close of runner bar `j`, let `SL*` be the latest confirmed swing low
> with index > entry index (knowable at `j`, i.e. index <= `j - 3`). Candidate
> stop = `Low[SL*] - b x ATR14[j]`. The runner stop becomes `max(current
> runner stop, candidate)` -- it only ratchets toward profit, and the
> chandelier trail and runner floor keep applying (the tighter wins). The new
> stop takes effect from bar `j + 1`, with the same hit-check-then-update
> ordering the chandelier trail already uses. Grid `b` in {0.00, 0.25, 0.50}.

**Arm `progress_stall` -- failed higher high with agreement.** On runner bar
`j`, fires when all hold: (1) a swing high becomes confirmed at `j` (pivot
index `j - 3`, after entry); (2) its High <= the previous confirmed
post-entry swing high; (3) `range_trend_10_50[j] <= c`; (4)
`vol_trend_10_50[j] <= 1.0` (frozen, not gridded). Firing closes the runner
at `Open[j + 1]`. Grid `c` in {0.70, 0.85, 1.00}. Pivots from v121's
`confirmed_pivots(df, k=3)`; `k = 3` frozen.

Both arms act only after TP1, so win (= TP1 touched) cannot change.

## Population

Both engines (`StrategyEngine.iter_trades` and `replay_scenarios`),
`scale_out=True`, the full cached universe and all ten horizons, code defaults
otherwise. Paired exit-only design: identical entries replayed under baseline
and arm through `scripts/backtest/measure_arms.py`. Added and removed trades
(an earlier runner exit can admit a later entry, as `StrategyEngine` holds one
trade per ticker) are disclosed with counts; the harvest clauses score the
paired keys.

## Stages and windows

| Stage | Window / data |
|---|---|
| Pilot | 2018-06..2020-12, 10 tickers |
| Selection / MDE (fold-train) | 2018-06-01..2022-12-31 |
| Walk-forward | folds 2021, 2022, 2023 |
| VALIDATION | 2024-01-01..2025-12-31, one shot per arm |

The two arms are separate budgets, run serially, never pooled.

**Stage -1 (reachability).** Run at `b = 0.00` and `c = 1.00` (the most active
values). Zero changed outcomes means refused, budget intact.

**Stage 0 (MDE).** `validate_component.py --stage mde --gate harvest
--train-effect-r <cell dExpR>` per grid cell, with paired MDE
(`acceptance.mde_paired`). A refused cell is ineligible.

**Stage 1 (fold-train selection), rule as implemented in
`scripts/backtest/harvest_select.py` (V123-12).** Quoted from the code, which
is authoritative over the plan's test fixture:

- Eligible: `res.lo is not None and res.lo > 0` where
  `res = bootstrap_delta(baseline, component, delta_expectancy_r)` (the
  bootstrap lower 95% bound of dExpR on the selection-stage window), and the
  cell is not in the Stage 0 `refused` set.
- Qualifying (`_qualifies`): the cell is eligible, **and**
  `plateau_report(param, grid, deltas, grid[i])["is_plateau"]`, **and**
  `any(rows[j]["eligible"] for j in neighbours)` with neighbours `i-1`, `i+1`
  in grid order.
- `plateau_report`: `is_plateau = all(abs(expectancies[j] - expectancies[i])
  <= PLATEAU_TOLERANCE_R for j in neighbors)`, `PLATEAU_TOLERANCE_R = 0.03`
  (`backtest_wf.py`), applied to the dExpR list (a missing delta counts 0.0).
- Pick (`_pick`): among qualifying cells, `best = max(round(delta_r, 4))`; tied
  cells are those equal to `best` at 4 dp; tie-break takes the **less
  aggressive** value, `max(tied)` for `b` (`--less-aggressive larger`, stop
  further away), `min(tied)` for `c` (`smaller`, fires less often).
- Verdicts: `NO_ELIGIBLE_CELL` if no cell is eligible; `NO_PLATEAU` if none
  qualifies; else `SELECTED`.

**Stage 2 (walk-forward).** `gate_expectancy_harvest`: at least 2 of 3 folds
with dExpR > 0, none below -0.02R, per-fold N(TP1-touched) >= 30.

**Stage 3 (VALIDATION).** All four harvest clauses. `not_luck` uses the
V123-11 ticker-cluster arm-label permutation on dExpR (n = 200, seed 42). A
missing p is FAIL.

## Disclosure

The outcome-flip count must be **0**; non-zero is a bug and stops the run.
Added and removed trade counts are disclosed. `win_rate_floor` is SKIPPED only
if `evaluate_harvest` confirms immunity; otherwise its -2pp floor is
bootstrapped for real.

**Reachability disclosure (V123-10).** `RUNNER_STRUCTURE_EXIT`,
`RUNNER_HL_TRAIL_ATR_BUFFER` and `RUNNER_STALL_RANGE_MAX` are registered
`REACHABLE` in `swingbot/core/backtesting/arms/reachability.py` with
`fixture_observable=False`: on the v74 fixture, `hl_trail` at b=0.0 and
`progress_stall` at c=1.0 changed 0 outcomes or R (measured 2026-10-05; no
fixture runner reaches a post-entry pivot rule). Observability on the fixture
is therefore not demonstrated; the rows are covered by the V123-5 unit tests.
Stage -1 on the full population is the real reachability test and can still
refuse an arm.

## Headroom (V123-0)

Source: `docs/superpowers/results/2026-10-02-v123-runner-headroom.md`. Frozen
stop rule: mean runner capture >= 75% means both arms close without a shot.
Result: **HEADROOM**. Pooled mean capture **70.4%** (n = 3127 runner trades,
TRAIN 2020-01-01..2023-12-31, 75 tickers, ten horizons, both engines),
below 75%, so both arms proceed. Sum-of-ratios capture 64.5%; mean runner R
2.430 vs mean MFE R 3.769; exit mix runner_be 66.5%, runner_tp2 20.5%,
runner_trail 11.6%, runner_timeout 1.4%. The 2026-09-10 "43%" memory figure is
superseded. Baseline description, not selection.

## Ship rule (quoted from the spec)

> An arm ships default-on only after its own VALIDATION passes. If both pass,
> only the one with the larger VALIDATION dExpR ships (they are alternative
> runner policies, not stackable without a new test). Failure closes the arm in
> the closed-pre-registrations table; code ships merged and inert. Reopening
> needs a mechanism other than "post-entry confirmed `k=3` swing low minus
> `b` in {0, 0.25, 0.5} ATR" / "failed HH with range ratio <= `c` in {0.70,
> 0.85, 1.00} and volume ratio <= 1.0, exit next open".

## Inconsistencies noted at registration

- The V123-12 plan test fixture put a cell at lift 0.0 next to one at 0.25
  (differ by 0.05 > `PLATEAU_TOLERANCE_R` 0.03), which is inconsistent with
  the plateau rule. The rule above is quoted from the code, not the fixture.
- The headroom instrument's window (TRAIN 2020-01-01..2023-12-31) differs from
  the selection window above; it is baseline description only and feeds no
  selection.
