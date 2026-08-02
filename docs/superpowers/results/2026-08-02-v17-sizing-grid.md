# V17 — Target/stop sizing grid, TRAIN only (plan v8, Phase V4)

**Status:** pre-registration written 2026-08-02 **before** the grid was run.
Everything above the "Results" heading was committed first; nothing in it is
edited once numbers exist.

**Command:** `python scripts/tune_sizing.py --strategy "<name>" --json <out>`,
one background chunk per strategy.
**Window:** TRAIN = 1999-01-01 .. 2023-12-31 (`swingbot/core/backtest_windows.py`,
widened by V46). The validation window is not touched and this script has no
flag that could reach it.
**Exit model:** v2 + `--scale-out`, `tp2_mode=levels` — what production runs
(`PLAN_ENGINE_V2` on, `INTRADAY_MANAGER_V2=true`). V16's baseline was v1 by
default and said so; V17 is where exit parameters are actually being chosen, so
it uses the production model, exactly as V16's own note asked.

## Step 1 — the selection rule, pre-registered

Quoted verbatim from plan v8 **V6 Step 3** (human-partner directive, 2026-07-31).
This is the rule; it is not re-derived here and it is not amended after seeing a
result:

```
OBJECTIVE   maximise win_rate
SUBJECT TO  every win >= MIN_TARGET_PCT (2.5%)
            expectancy_r > 0
            scratches + timeouts <= 50% of closed trades
STRETCH     win_rate >= 90%
FLOOR       reject any config with expectancy_r <= 0 regardless of WR
```

**Trade volume is explicitly NOT an objective.** A config producing 20 trades at
85% WR beats one producing 400 at 60%. Frequency does not tie-break.

Two things the rule's own preamble requires, applied here as stated rather than
as new criteria:

1. **`N >= 30` is applied to the independent sample, not the summed one.**
   V16 finding 2 / V49 Step 3 measured that five of eleven strategies reuse the
   same entry signal across horizons — RSI's summed N=122 is ~13 independent
   trades. A strategy-level N in this grid is likewise a sum over ten horizons,
   so the same correction applies or the sample gate is scored against inflated
   evidence. `tune_sizing.py` re-measures the reuse ratio **per config**
   (distinct `(date, entry, direction)` signatures vs. the summed count, flagged
   at >=1.5x, the threshold V49 pinned) and gates on `n_independent`.
2. **Wilson lower bounds beside every win rate** (V6 Step 5), computed on that
   same independent sample. V6 Step 5 also stands: proving WR > 90% needs
   N >= 59, so any cohort under that is provisional however good it looks.

**V6 Step 4's honesty clause is pre-registered here too.** If the frontier tops
out below 90%, the achieved number gets recorded and the task stops. No relaxing
`MIN_TARGET_PCT`, no post-hoc cohort re-cutting, no dropping losers from the
denominator. V16 already measured a ~78% headline ceiling over this window, so
that is the expected outcome, and it is a result.

## Step 2 — the grid, pre-registered

Full cross product, per strategy, all 11 strategies:

| Axis | Values | Knob it moves |
|---|---|---|
| `min_target_pct` | **2.5, 3.5, 5.0** | `config.MIN_TARGET_PCT` — the V10 target floor |
| `rr` | **0.35, 0.75, 1.25, 2.0** | `STRATEGY_RR_OVERRIDE[strategy]` (unfrozen by V6 Step 2) |
| `atr_stop_multiple` | **1.5, 2.0, 2.5** | every horizon's `HORIZONS[hk]["atr_stop_multiple"]` |
| `trail_atr_mult` | **2.0, 2.5, 3.0** | `EXIT_V2_PARAMS[strategy]["trail_atr_mult"]` |

**108 configs x 11 strategies = 1188 runs**, each over the 78-ticker watchlist x
10 horizons.

Three deliberate choices, recorded before the run so they cannot be
rationalised afterwards:

- **The floor axis starts at 2.5, not lower.** The rule's own constraint is
  "every win >= 2.5%", so a config below that is disqualified by construction;
  gridding it would only manufacture rows that cannot be selected. Whether 2.5
  is the right floor is not a V17 question — V12's live measurement and V27's
  shadow week own it.
- **`tp2` is not an axis.** Task 30's TRAIN grid chose it per strategy
  (`EXIT_V2_PARAMS`) and the plan names `tune_exit_v2.py` as the script that
  re-opens it. V17 moves the trail and holds each strategy's adopted `tp2`.
  Caveat for whoever reads this later: those Task-30 values were chosen on the
  old 2020-2023 window under the WR>=80 rule that V6 voided, so they are
  inherited, not re-validated.
- **Per-horizon `atr_stop_multiple` is set uniformly.** It is a flat 2.0 across
  all ten horizons today; V19 owns making it horizon-dependent, and doing that
  here would confound the two.

**Axis interaction, expected in advance:** `MIN_TARGET_PCT` and `rr` both price
TP1 and `apply_target_floor` takes the max, so at high `rr` the floor never binds
and the `min_target_pct` axis collapses — those rows will be exact duplicates.
That is the cross product being honest about a degeneracy, not a bug; duplicate
rows are reported, not deleted.

**Where `atr_stop_multiple` is inert:** it only reaches `plan_engine._atr_plan`.
Fibonacci and Elliott Wave size their stop off structure (capped by
`max_risk_pct`) and Support/Resistance off `sr_stop_pct`, so for those three the
axis is expected to change nothing. Recorded in advance so a flat result there is
read as the known mechanism rather than as a finding.

## The harness — and why it is a new script

`tune_strategy.py --grid` sweeps `entry_filters.DEFAULT_PARAMS`, i.e. *entry*
parameters; `tune_exit_v2.py` sweeps trail/tp2/entry-type. **Neither has an axis
for the target floor, the R:R override or the ATR stop multiple**, so the grid
the plan's V17 Step 2 names could not be expressed in either script. Rather than
bend those two (both are load-bearing for other tasks), V17 adds
`scripts/tune_sizing.py` with exactly the four missing axes and the same
pre-registered rule, and leaves them untouched. The plan's Step 2 wording is
amended to match what was actually run.

### The finding that made the run possible at all

Measured by cProfile on 2026-08-02, not assumed: **an exit-v2 `tp2_mode=levels`
backtest spends ~98% of its runtime inside `build_level_map` ->
`trendline_levels` -> `_find_best_trendline`**, which is O(pivots^3) over the
full df history. One config over the universe costs ~7 min under v2 against
~14 s under v1, and the entire difference is the level map.

None of the level map's inputs — `(df up to the entry bar, horizon, entry
price)` — is a sizing parameter. So a sizing grid recomputes a bit-identical
level map once per config: **the pre-registered grid was a ~30-hour job, of
which ~29 hours was recomputing the same numbers.** `backtest.py` now carries an
opt-in exact-key memo (`enable_level_map_memo`, off by default, tuning harnesses
only — the live bot's memory profile is unchanged). Measured effect on a
4-ticker MACD probe: 29.3s cold, **0.9s warm (~33x)**, with the emitted trades
byte-identical across memoized and non-memoized runs.

This is the third time in this plan that an unexamined cost or gap would have
silently shaped a result (V43's cache overwrite, V48's skipped parity suite).
The memo is an exact memo, not an approximation: a hit returns precisely what
the call would have computed.

---

# Results

*(written after the run; nothing above this line is edited)*
