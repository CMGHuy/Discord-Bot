# v123 — Structure-aware runner exit

**Version:** ui 1.21.0 · bot 2.0.0 (at writing)
**Bump:** bot patch (only if an arm passes VALIDATION and ships default-on; runner exits change, no new surface)
**Edge:** harvest

## Hypothesis

Lessons 2 and 4 of `docs/strategy/volume-in-context.md`: after a breakout
the trend can keep printing HH/HL on cooling volume, and that is **not** a
reason to exit; what deserves action is structure itself — a broken higher
low, or a failed higher high **together with** contracting candle range and
cooling volume ("look for agreement, not one signal").

Today's runner (post-TP1 leg of the scale-out walk,
`planning/exit_sim.py:_scale_out_exit_walk`) exits on a chandelier trail
(ATR from the extreme close), TP2, the runner floor or timeout. Nothing in
any exit reads structure or volume. A memory note (2026-09-10, live book)
says winners banked only about 43% of the move; that figure is stale and is
**re-derived on TRAIN replay in this plan's first task** before anything
else runs.

**Pre-registered claim:** replacing or supplementing the runner's chandelier
trail with a structure-defined rule raises pooled ExpR on identical entries,
under the v92 harvest gate.

## Not a re-run of a closed row

| Closed row | Why this differs |
|---|---|
| v92 H1 `ADAPTIVE_RUNNER_TRAIL_ENABLED` (measured null) | tightened the ATR multiplier after an R trigger; v123's levels are swing pivots, not ATR multiples of the extreme |
| v92 H2 `STALL_EXIT_ENABLED` (unmeasurable) | pre-TP1, time-based, `< 0.5R` after day N; v123 is runner-only and structure-triggered, and is measured through the arm engines' `scale_out=True` walk, which v92 H2's `stall_exit_day` never reached |
| v104 structural stops (no lift) | the **initial** stop at the strategy's own structure; v123 never touches the initial stop or anything before TP1 |

## Two arms, each its own pre-registration

Both consume v121's `confirmed_pivots(df, k=3)` and feature series from
`swingbot/core/market/structure.py` (v121 merged first). Bullish shown;
bearish mirrors. Only pivots with pivot index **after the entry bar** count.

**Arm `hl_trail` — structural trailing floor.** At the close of runner bar
`j`, let `SL*` be the latest confirmed swing low with index > entry index
(knowable at `j`, i.e. index ≤ `j − 3`). Candidate stop =
`Low[SL*] − b × ATR14[j]`. The runner stop becomes
`max(current runner stop, candidate)` — it only ratchets toward profit, and
the chandelier trail and runner floor keep applying (the tighter wins). The
new stop takes effect from bar `j + 1`, with the same hit-check-then-update
ordering the chandelier trail already uses. Grid `b ∈ {0.00, 0.25, 0.50}`.

**Arm `progress_stall` — failed higher high with agreement.** On runner bar
`j`, the arm fires when **all** hold:

1. a swing high becomes confirmed at `j` (pivot index `j − 3`, after entry);
2. its High ≤ the previous confirmed post-entry swing high (failed HH);
3. `range_trend_10_50[j] ≤ c` (candle range contracting);
4. `vol_trend_10_50[j] ≤ 1.0` (volume cooling; frozen, not gridded).

Firing closes the runner at `Open[j + 1]` — the earliest price a live
paper trade could act on after the confirming close, so replay never books a
fill the live path cannot match. Stop / TP2 / trail hits on bar `j + 1`
before the open are impossible (the open is first), so ordering is
unambiguous. Grid `c ∈ {0.70, 0.85, 1.00}`.

Both arms act **only after TP1**, so win (= TP1 touched) cannot change:
`win_rate_floor` is `SKIPPED` by mechanism and the outcome-flip count is
disclosed and must be 0 (a non-zero count is a bug, not a result). The
pre-TP1 analogue is out of scope and would be its own pre-registration with
a live win-rate floor.

## Knobs

- `RUNNER_STRUCTURE_EXIT` — `off | hl_trail | progress_stall`, default `off`.
- `RUNNER_HL_TRAIL_ATR_BUFFER` — `b`, float, default `0.0`.
- `RUNNER_STALL_RANGE_MAX` — `c`, float, default `1.0`.

All `search_class = searchable`, all in `swingbot/config.py`'s schema.
With `RUNNER_STRUCTURE_EXIT = off` the walk is byte-identical to today
(witness test).

## One implementation, two callers

Pure functions in `planning/exit_sim.py` (beside `chandelier_stop` and
`runner_floor`, the established single-source pattern):
`structural_runner_stop(pivots_row, atr_value, b, direction, entry_index)`
and `progress_stall_fires(pivots_row, prev_post_entry_sh, features_row, c,
direction, entry_index, j)`. `_scale_out_exit_walk` precomputes the v121
series once per walk (they are truncation-stable, so row `j` equals a
recomputation on `df.iloc[:j+1]` — tested) and calls them per bar.
`planning/plan_manager.py` calls the same two functions from its
completed-daily-bar check (the path that already updates the chandelier
trail), never from the intraday poll. A `progress_stall` fire marks the
runner for exit at the next session open and emits the existing runner-close
lifecycle event with reason `progress_stall`; `hl_trail` updates
`working_stop` with reason `structure_trail`. Wording goes through the
`alert-surface` skill. Paper only — no order is ever placed.

## Measurement

**Task 0 — headroom re-derivation (TRAIN replay, baseline only).** For
trades that touched TP1: runner realised R, runner MFE R (best close after
TP1 before runner exit), capture ratio, and the runner exit-reason mix,
pooled and per horizon. **Frozen stop rule:** if mean runner capture ≥ 75%,
there is no headroom: both arms can only exit at or before today's runner
exit (`hl_trail` only ratchets the stop tighter; `progress_stall` only adds
an earlier exit), so both close without a shot. The numbers are reported
as-is either way; this is baseline description, not selection.

**Funnel per arm (v92 harvest gate, `acceptance_harvest.py`).** Paired
exit-only design: identical entries replayed under baseline and arm through
`scripts/backtest/measure_arms.py` (arm engines, `scale_out=True`).

1. Stage −1 reachability — zero changed runner exits ⇒ refused, budget intact.
2. Stage 0 MDE — `validate_component.py --stage mde --gate harvest`
   (paired variance via `acceptance.mde_paired`).
3. Stage 1 fold-train selection — eligible: `expectancy_gain` lower 95% > 0
   on fold-train; `plateau_report()` needs an eligible grid neighbour;
   choose largest ΔExpR, tie → the less aggressive value (larger `b`:
   stop further away; smaller `c`: fires less often).
4. Stage 2 walk-forward — ≥ 2 of 3 folds with ΔExpR > 0, none below −0.02R,
   per-fold N(TP1-touched) ≥ 30.
5. Stage 3 VALIDATION 2024-01-01..2025-12-31 — one shot per arm, all four
   harvest clauses; missing permutation p = FAIL.

The two arms are separate budgets, run serially, never pooled. Pre-
registration record committed under `docs/superpowers/results/` before any
outcome is read; `backtest-gate` invoked before every run.

## Ship rule

An arm ships default-on only after its own VALIDATION passes. If both pass,
only the one with the larger VALIDATION ΔExpR ships (they are alternative
runner policies, not stackable without a new test). Failure closes the arm in
the closed-pre-registrations table; code ships merged and inert. Reopening
needs a mechanism other than "post-entry confirmed `k=3` swing low minus
`b ∈ {0, 0.25, 0.5}` ATR" / "failed HH with range ratio ≤ `c ∈ {0.70, 0.85,
1.00}` and volume ratio ≤ 1.0, exit next open".

## Testing

- Off witness: `RUNNER_STRUCTURE_EXIT=off` walk byte-identical on fixtures.
- `hl_trail`: stop never loosens; a pivot confirmed at `j` affects bar
  `j + 1`, never `j`; pre-entry pivots ignored; bearish mirror.
- `progress_stall`: fires only with all four conditions; exits at
  `Open[j+1]`; never fires pre-TP1; a final bar `j = n−1` with no `j+1`
  defers to timeout handling.
- Outcome-flip test: across a fixture set, TP1-touched status is identical
  baseline vs arm.
- Parity: one fixture through `_scale_out_exit_walk` and through
  `plan_manager`'s daily-bar check produces the same stop sequence and exit
  session.
- `no-lookahead` review of every new function.

## Parallelisation

Sequential spine: v121 merged → Task 0 headroom (can run while code is
written; it only reads baseline) → knobs → pure functions → exit-walk wiring
→ plan_manager wiring (consumes the same functions; serial after the walk
because the parity test needs both) → parity test → reachability →
pre-registration commit → measurement (serial, one arm at a time).
`config.py` and `reachability.py` are shared with v122: those tasks never
run concurrently with v122's. Full suite once, as the plan's final task.
