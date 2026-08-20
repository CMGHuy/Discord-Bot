# v39 — Runner floor protection at TP1: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

Version: ui 1.7.13 · bot 1.3.0
Bump: bot patch (1.3.0 → 1.3.1) — a tuning change to the runner's starting stop. `ui` none.

**Goal:** Set the runner leg's stop, the instant TP1 fires, to `entry + (2/3) * (tp1 - entry)` instead of pure breakeven, in both the live plan manager and the backtest exit walk, from one shared helper.

**Architecture:** A single `plan_engine.runner_floor(entry, tp1) -> float` built on a new module constant `RUNNER_FLOOR_FRACTION = 2.0 / 3.0`, imported by `plan_manager.py` rather than re-declared. Three call sites move together in one commit (`_scale_out_exit_walk`, `_step_active`, `_check_bar_active`), and the three "breakeven vs. trail" reason-label comparisons switch from `== entry` to `== runner_floor(...)`. The chandelier ratchet, TP2 branch, timeout clamp, and every reason string are untouched.

**Tech Stack:** Python 3.11, pandas/numpy, pytest. Tests run via `python scripts/dev/testrun.py file <path>` (never the full suite mid-task).

## Progress

- **Completed 2026-08-20, all 5 tasks, one session:** Task 1 (`runner_floor`
  + all three call sites + reason-label comparisons, plus the existing-test
  rework `test_exit_sim_scaleout.py` needed — 2 of its tests genuinely
  broke, 4 needed number updates, 1 needed a rounding-tolerance widening the
  plan didn't anticipate: `test_legs_fractions_always_sum_to_one` hit a
  round-half-to-even edge case once the floor's r-multiple (1.333...)
  stopped being an exact 0.0). Task 2 (boundary coverage on both paths;
  confirmed the two backtest boundary tests are real guards by temporarily
  reverting the floor and watching them fail, per the plan's own Step 2).
  Task 3 (Discord copy). Task 4 (docs staleness note).
- **Deviation from the plan's literal text:** Task 5 bumped `bot` to
  **1.3.2**, not the `1.3.1` the plan names — a concurrent, unrelated
  session (`v35-anchored-vwap`) had already taken `1.3.1` before this plan
  executed, and had left `version_history.json` unregenerated for it (fixed
  in a separate commit, before this plan's own work, so the pre-implementation
  baseline was genuinely green rather than carrying someone else's gap).
- **Branch:** `worktree-2026-08-20-v39-runner-floor-protection`, merged to
  `main`.

## Global Constraints

- **The reason strings never change.** `"runner_be"`, `"runner_trail"`, `"tp1_runner_be"`, `"tp1_runner_trail"`, `"tp1_runner_tp2"`, `"runner_tp2"`, `"runner_timeout"` keep their exact current values. ~30 files pattern-match them, including frozen historical result JSONs under `docs/superpowers/results/*.json` (never rewritten retroactively) and `performance.py`'s win/loss classifier keying off `reason.startswith("tp1_")`. Only the **comparison** that selects between `_be` and `_trail` moves.
- **`RUNNER_FLOOR_FRACTION = 2.0 / 3.0`**, defined once in `swingbot/core/planning/plan_engine.py` beside `TRAIL_ATR_MULT`/`TP1_FRACTION`. `plan_manager.py` imports `runner_floor`; it must never re-declare the expression.
- **One formula, both directions.** `tp1 - entry` is already signed correctly (positive bullish, negative bearish). No `is_bull` branch at any call site.
- **`BREAKEVEN_TRIGGER_FRACTION` (0.5) is frozen and out of scope.** The *pre*-TP1 breakeven trigger, its `"be_moved"` event, its `"scratch"` close reason, and the `"🛡 Stop moved to break-even"` / `"⚪ Scratched at break-even"` Discord copy are a different mechanism. Do not touch them.
- **`select_tp2` / `_tp2_from_r` / the 3x-leg1 cap, and `maybe_pyramid`, are out of scope** and not re-derived.
- **Byte-identical live/backtest coupling.** `_scale_out_exit_walk`'s docstring promises phase-1 parity with the single-leg walk and mirrors the live manager in phase 2. Never leave a commit where one path has the floor and the other does not.
- **Commit style:** conventional commits (`feat:`, `fix:`, `test:`, `docs:`, `refactor:`), one commit per task. Stage specific files — never `git add -A` (concurrent sessions share this working tree).

## Parallelisation

- **Sequential: Task 1 → Task 2.** Task 1 is one coupled unit (the formula, its three call sites, the three label comparisons, and every existing-test update needed to keep the suite green). Splitting the call sites would leave live and backtest disagreeing mid-implementation — exactly the drift the "byte-identical" design goal exists to prevent. Task 2 adds the new boundary coverage and can only be written against real post-Task-1 code.
- **Group 2 (parallel with each other, after Task 2 lands):** Task 3 (`embeds.py` + `tests/scanning/test_transition_embeds.py`) and Task 4 (`config.py` + `docs/features.md`) — disjoint files, no contract dependency.
- **Sequential: Task 5 last.** The version bump is a release marker and goes after the work it names is committed and green.

---

# Phase 1 — The floor

### Task 1: Introduce `runner_floor` and move all three call sites

**Files:**
- Modify: `swingbot/core/planning/plan_engine.py:31-33` (constants), `:1174-1181` (new helper after `chandelier_stop`), `:1186-1192` (docstring), `:1252-1264` (phase-2 setup), `:1266-1272` (reason label), `:1320-1329` (`simulate_exit` docstring)
- Modify: `swingbot/core/planning/plan_manager.py:16-18` (import), `:272` (`_step_active`), `:293` + `:307-310` + `:326` (`_step_partial`), `:393` (`_check_bar_active`), `:405` + `:407-411` (`_check_bar_partial`), `:80-81` + `:88-92` (pyramid docstring note)
- Test: `tests/planning/test_plan_manager_active.py:67`
- Test: `tests/planning/test_exit_sim_scaleout.py` (module docstring + 6 existing tests)

**Interfaces:**
- Produces: `swingbot.core.planning.plan_engine.RUNNER_FLOOR_FRACTION: float` (== `2.0 / 3.0`) and `swingbot.core.planning.plan_engine.runner_floor(entry: float, tp1: float) -> float`. Task 2, and any later task, imports both from `swingbot.core.planning.plan_engine`.
- Consumes: `plan_engine.chandelier_stop(extreme_close_since_tp1, atr_value, mult, direction) -> float` (unchanged).

**Reference values used throughout this task** (all computed by running the patched code, not by hand):

| Plan | `runner_floor` |
|---|---|
| bullish `entry=100.0, tp1=110.0` | `106.66666666666667` |
| bearish `entry=100.0, tp1=90.0` | `93.33333333333333` |
| bullish `entry=100.0, tp1=102.0` | `101.33333333333333` |

- [ ] **Step 1: Update the existing live-path assertion so it fails**

In `tests/planning/test_plan_manager_active.py`, replace line 67 (inside `test_tp1_touch_banks_partial_and_moves_to_partial`):

```python
    assert p.working_stop == pytest.approx(106.66666666666667)   # v39 runner floor:
                                                                 # 100 + (2/3)*(110-100)
```

(The file already imports `pytest` at line 1. Nothing else in this file changes — every other test here exercises the pre-TP1 `BREAKEVEN_TRIGGER_FRACTION` mechanism, which this plan does not touch.)

- [ ] **Step 2: Run it to make sure it fails**

Run: `python -m pytest tests/planning/test_plan_manager_active.py::test_tp1_touch_banks_partial_and_moves_to_partial -v`
Expected: FAIL — `assert 100.0 == 106.66666666666667 ± 1.1e-04`

- [ ] **Step 3: Add the constant to `plan_engine.py`**

Replace lines 31-33 of `swingbot/core/planning/plan_engine.py`:

```python
TRAIL_ATR_MULT = 2.5          # chandelier default; finalized by the Task 30 TRAIN grid
TP1_FRACTION = 0.5            # fixed by spec §5
RUNNER_FLOOR_FRACTION = 2.0 / 3.0   # v39: the runner's stop the instant TP1 fires locks
                                    # in this fraction of the entry->TP1 move (was 0.0,
                                    # i.e. plain breakeven). Spec:
                                    # docs/superpowers/specs/2026-08-20-v39-runner-floor-protection-design.md
DEFAULT_EXPIRY_BARS = 5
```

- [ ] **Step 4: Add the `runner_floor` helper**

In `swingbot/core/planning/plan_engine.py`, immediately after `chandelier_stop` (currently ending at line 1180) and before `def _scale_out_exit_walk`, insert:

```python
def runner_floor(entry: float, tp1: float) -> float:
    """The runner leg's stop the instant TP1 fires (v39).

    ``entry + RUNNER_FLOOR_FRACTION * (tp1 - entry)`` -- 2/3 of the
    entry->TP1 move locked in, so a reversal right after TP1 gives back at
    most a third of that leg's gain instead of all of it. Replaces the plain
    breakeven (``entry``) floor the scale-out model shipped with.

    One formula, both directions: ``tp1 - entry`` is already signed per
    direction (positive for a bullish plan, negative for a bearish one), so
    no ``is_bull`` branch is needed at any call site.

    Single source of truth. ``plan_manager.py`` imports this rather than
    re-declaring the expression, exactly as it already does for
    ``chandelier_stop`` -- the live poll path, the overnight bar-check path
    and this module's backtest walk must never drift apart.
    """
    return entry + RUNNER_FLOOR_FRACTION * (tp1 - entry)
```

- [ ] **Step 5: Move the backtest call site**

In `swingbot/core/planning/plan_engine.py::_scale_out_exit_walk`, replace lines 1252-1257:

```python
    # ---- phase 2: runner. Stop starts at the v39 runner floor (entry +
    # RUNNER_FLOOR_FRACTION x (tp1 - entry)), NOT at plain breakeven; it
    # protects bars AFTER the TP1 bar (same "subsequent bars only"
    # convention as the BE move). Task 25 added the TP2 branch; Task 26 adds
    # the chandelier ratchet: the stop trails the extreme close since TP1 by
    # trail_atr_mult x ATR(14), only ever moving toward profit (never back
    # down toward the floor).
    runner_stop = runner_floor(entry_price, tp1)
```

and lines 1263-1264:

```python
    checked_stop = runner_stop   # the level checked against the CURRENT bar; stays
                                 # at the initial runner-floor value if the loop
                                 # below never runs
```

- [ ] **Step 6: Move the backtest reason-label comparison**

In the same function, replace line 1271:

```python
            # v39: "runner_be" now means "closed at its initial post-TP1
            # floor", not literally at entry. The STRING is deliberately
            # unchanged -- ~30 files pattern-match it, including frozen
            # result JSONs under docs/superpowers/results/ and
            # performance.py's reason.startswith("tp1_") classifier.
            runner_reason = ("runner_be"
                             if runner_stop == runner_floor(entry_price, tp1)
                             else "runner_trail")
```

- [ ] **Step 7: Correct the two `plan_engine.py` docstrings that claim breakeven**

Replace lines 1189-1190 (inside `_scale_out_exit_walk`'s docstring):

```python
    hands the rest to the runner: stop starts at the v39 runner floor
    (entry + 2/3 x (tp1 - entry), see runner_floor) and ratchets
```

Replace lines 1326-1327 (inside `simulate_exit`'s docstring):

```python
    tp1_fraction and hands the rest to a runner whose stop starts at the
    v39 runner floor (runner_floor: entry + 2/3 of the entry->TP1 move),
    ratchets via a chandelier ATR trail (Task 26), and can also
```

- [ ] **Step 8: Import `runner_floor` into `plan_manager.py`**

Replace lines 16-18 of `swingbot/core/planning/plan_manager.py`:

```python
from swingbot.core.planning.plan_engine import (PlanStatus, TradePlanV2,
                                       chandelier_stop, pending_expired,
                                       pending_invalidated, record_transition,
                                       runner_floor)
```

- [ ] **Step 9: Move the live poll TP1 call site**

In `swingbot/core/planning/plan_manager.py::_step_active`, replace line 272:

```python
            plan.working_stop = runner_floor(entry, plan.tp1)   # v39 runner floor
```

- [ ] **Step 10: Move the overnight bar-check TP1 call site**

In `swingbot/core/planning/plan_manager.py::_check_bar_active`, replace line 393:

```python
            plan.working_stop = runner_floor(entry, plan.tp1)   # v39 runner floor
```

- [ ] **Step 11: Move the live reason-label comparison and the PARTIAL fallbacks**

In `_step_partial`, replace line 293:

```python
        # A PARTIAL plan always has working_stop set (the TP1 branch above
        # writes it). The fallback only fires for a plan persisted to
        # data/plans.json before v39; using the floor there tightens those
        # legacy runners too, and keeps the reason label below correct.
        stop = (plan.working_stop if plan.working_stop is not None
                else runner_floor(entry, plan.tp1))
```

replace lines 307-310:

```python
        hit_stop = price <= stop if is_bull else price >= stop
        if hit_stop:
            # v39: "tp1_runner_be" now means "closed at the initial post-TP1
            # floor", not literally at entry. The string is unchanged on
            # purpose -- see the same note in plan_engine._scale_out_exit_walk.
            reason = ("tp1_runner_be" if stop == runner_floor(entry, plan.tp1)
                      else "tp1_runner_trail")
            return self._close_runner(plan, price, reason, risk, sign)
```

and replace line 326 (the chandelier ratchet's floor):

```python
                floor = (plan.working_stop if plan.working_stop is not None
                         else runner_floor(entry, plan.tp1))
```

- [ ] **Step 12: Move the bar-check reason-label comparison and its fallback**

In `_check_bar_partial`, replace line 405:

```python
        stop = (plan.working_stop if plan.working_stop is not None
                else runner_floor(plan.entry_price, plan.tp1))
```

and replace lines 407-411:

```python
        hit_stop = bar_low <= stop if is_bull else bar_high >= stop
        if hit_stop:
            fill = gap_stop_fill(bar_open, stop, plan.direction)
            # v39: "tp1_runner_be" == "closed at the initial post-TP1 floor".
            reason = ("tp1_runner_be"
                      if stop == runner_floor(plan.entry_price, plan.tp1)
                      else "tp1_runner_trail")
            return self._close_runner(plan, fill, reason, risk, sign)
```

- [ ] **Step 13: Note the floor change in the pyramiding docstring**

`maybe_pyramid`'s risk derivation assumes the remainder stops at breakeven. That bound stays valid (the floor is strictly more protective) but its wording is now stale. In `swingbot/core/planning/plan_manager.py`, replace lines 80-81:

```python
    """Add size at +1R with the add's stop at the ORIGINAL entry. Only from
    PARTIAL (TP1 banked, remainder stopped at the v39 runner floor -- the
    derivation below still assumes plain breakeven, which is now a strictly
    conservative floor rather than the exact one, so the bound holds).
```

- [ ] **Step 14: Run the live-path test to confirm it now passes**

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_active.py`
Expected: PASS, `0 failed`.

- [ ] **Step 15: Run the live PARTIAL tests — they must already be green with no edits**

Run: `python scripts/dev/testrun.py file tests/planning/test_plan_manager_partial.py`
Expected: PASS, `0 failed`. All four existing tests here (`test_runner_closes_at_breakeven`, `test_runner_closes_at_tp2`, `test_tp2_none_runner_ignores_high_prices`, `test_trail_ratchets_and_closes`) were traced under the new floor and none of their assertions depended on the old value of `100.0`:
- `[99.9]` is below `106.667`, so it still closes `tp1_runner_be` (leg2 `r == -0.02`, total `1.04 >= 0.9`).
- `[118.5]` with `tp2=118.0` never reaches the floor, so it still closes `tp1_runner_tp2`.
- `[140.0]` with `tp2=None` and no `atr_fn` still returns `[]`.
- `[120.0, 118.0, 114.9]` with ATR 2.0 ratchets to `max(106.667, 115.0) == 115.0`, unchanged, and still closes `tp1_runner_trail` at `r == 2.98`.

If any of these fails, stop and re-derive before continuing — it means the implementation diverged from this plan.

- [ ] **Step 16: Update the `test_exit_sim_scaleout.py` module docstring**

Replace lines 3-7 of `tests/planning/test_exit_sim_scaleout.py`:

```python
Phase 1 (pre-TP1) is byte-identical to the single-leg walk. The runner
phase's stop starts at the v39 runner floor -- entry + 2/3 x (tp1 - entry),
plan_engine.runner_floor (it started at plain break-even from Task 24 until
v39) -- can exit early at an optional TP2 (Task 25), and otherwise ratchets
via a chandelier ATR trail (Task 26) that only ever moves toward profit.
Task 27 still owes runner-timeout coverage.
```

- [ ] **Step 17: Rework `test_bullish_tp1_partial_then_runner_stopped_at_trail`**

This test exists to prove the chandelier ratchet fires. Its old bar 2 had a low of `104.0`, which is **below** the new floor of `106.667`, so under the new code it would close `runner_be` on bar 2 and never reach the trail at all. The bar-2/bar-3 prices are rebuilt so the whole runner phase lives above the floor. Replace lines 16-42 of `tests/planning/test_exit_sim_scaleout.py`:

```python
def test_bullish_tp1_partial_then_runner_stopped_at_trail():
    # entry 100, stop 95, tp1 110 -> rr = 2. v39 runner floor = 106.666...7.
    # This tape is only 4 bars long, well short of ATR(14)'s warmup, so
    # atr_series.iloc[j] is NaN and _safe_atr_value falls back to a
    # synthetic 2% of entry (2.0) -- the chandelier ratchet (Task 26) is
    # live on that fallback. Bar 2 must stay ABOVE the runner floor (low
    # 108.0 > 106.667) or it would close runner_be there and this test would
    # stop proving anything about the trail; its close of 113.0 lifts the
    # trail to 113.0 - 2.5*2.0 = 108.0, above the floor. Bar 3's low of
    # 107.0 then pierces that ratcheted trail -- and NOT the floor, which
    # 107.0 still clears -- so the exit is unambiguously the trail's.
    df = make_ohlcv([
        100.0,                           # 0: entry bar
        (100.0, 111.0, 99.5, 110.5),     # 1: High 111 >= tp1 110 -- leg 1 banked
        (110.0, 114.0, 108.0, 113.0),    # 2: low above the floor -- ratchets to 108.0
        (113.0, 113.5, 107.0, 108.5),    # 3: Low 107.0 <= ratcheted trail (108.0)
    ])
    plan = _plan(direction="bullish", stop_loss=95.0, tp1=110.0, tp2=None)
    result = simulate_exit(df, signal_index=0, plan=plan, scale_out=True)
    rr = 2.0
    assert result.outcome == "win"
    assert result.runner_outcome == "runner_trail"
    assert result.exit_index == 3
    assert result.r_total == pytest.approx(1.8)
    assert len(result.legs) == 2
    assert result.legs[0] == {"fraction": 0.5, "exit_price": 110.0,
                              "r": pytest.approx(rr), "reason": "tp1"}
    assert result.legs[1]["exit_price"] == pytest.approx(108.0)
    assert result.legs[1]["r"] == pytest.approx(1.6)
    assert result.legs[1]["reason"] == "runner_trail"
    # The floor is a starting point, not a ceiling: the trail carried the
    # stop strictly above it before the exit.
    assert result.legs[1]["exit_price"] > runner_floor(100.0, 110.0)
```

Add the import this needs at the top of the file — replace line 11:

```python
from swingbot.core.planning.plan_engine import (RUNNER_FLOOR_FRACTION,
                                                runner_floor, simulate_exit)
```

- [ ] **Step 18: Update `test_bearish_mirror_runner_be`'s expected numbers**

The bearish runner still closes on bar 2 at its initial floor, but that floor is now `93.33333333333333` rather than `100.0`, so `r_total` moves from `1.0` to `1.667`. Replace lines 45-54:

```python
def test_bearish_mirror_runner_be():
    # entry 100, stop 105, tp1 90 -> rr = 2. v39 runner floor = 100 +
    # (2/3)*(90-100) = 93.333...3 -- the same formula, no is_bull branch,
    # because (tp1 - entry) is already negative here.
    df = make_ohlcv([
        100.0,
        (100.0, 100.5, 89.0, 90.5),      # 1: Low 89 <= tp1 90 -- leg 1 banked
        (91.0, 100.5, 90.5, 99.5),       # 2: High 100.5 >= runner floor 93.333 -- runner_be
    ])
    plan = _plan(direction="bearish", stop_loss=105.0, tp1=90.0, tp2=None)
    result = simulate_exit(df, signal_index=0, plan=plan, scale_out=True)
    assert result.outcome == "win" and result.runner_outcome == "runner_be"
    assert result.legs[1]["exit_price"] == pytest.approx(93.33333333333333)
    assert result.legs[1]["r"] == pytest.approx(1.333)
    assert result.r_total == pytest.approx(1.667)
```

- [ ] **Step 19: Update `test_same_bar_runner_stop_and_tp2_is_conservative_stop_first`**

The mechanism (a bar spanning both the runner stop and TP2 resolves stop-first) is unchanged; only the level the stop sits at moved. Replace lines 98-108:

```python
def test_same_bar_runner_stop_and_tp2_is_conservative_stop_first():
    # Runner bar spans BOTH the runner floor (106.666...7) and tp2 (118):
    # stop wins. Low 99.0 is far below the floor, so the ordering -- not the
    # exact level -- is what this fixture probes.
    df = make_ohlcv([
        100.0,
        (100.0, 111.0, 99.5, 110.5),     # 1: TP1 banked
        (110.0, 119.0, 99.0, 105.0),     # 2: High >= tp2 118 AND Low <= floor 106.667
    ])
    plan = _plan(direction="bullish", stop_loss=95.0, tp1=110.0, tp2=118.0)
    result = simulate_exit(df, signal_index=0, plan=plan, scale_out=True)
    assert result.runner_outcome == "runner_be"
    assert result.legs[1]["exit_price"] == pytest.approx(106.66666666666667)
    assert result.legs[1]["r"] == pytest.approx(1.333)
```

- [ ] **Step 20: Tighten `test_chandelier_trail_locks_in_runner_profit`'s floor claim**

This test passes unchanged (verified: it exits `runner_trail` at `128.0822076652532`), but its `> 100.0` assertion no longer proves anything the floor doesn't already guarantee. Replace lines 126-129:

```python
    exit_leg = result.legs[1]
    assert exit_leg["exit_price"] > runner_floor(100.0, 110.0)   # trail beat the floor
    assert exit_leg["r"] > 0.0
    assert result.r_total > (0.5 + 0.5 * RUNNER_FLOOR_FRACTION) * 2.0  # better than the floor
```

- [ ] **Step 21: Document the narrow margin in `test_runner_timeout_marks_leg2_at_last_close`**

This test passes unchanged (its drift bars' low of `107.0` clears the `106.667` floor by `0.333`), but that margin is now load-bearing and invisible. Replace lines 169-172:

```python
def test_runner_timeout_marks_leg2_at_last_close():
    # 2w horizon (max_holding_days=14): TP1 on bar 1, then a drift that never
    # touches the floor/trail/tp2 -> runner_timeout at entry+14, leg 2 at that
    # close. The drift bars' low of 107.0 deliberately clears the v39 runner
    # floor (106.666...7) -- a lower low would close this as runner_be on the
    # first drift bar and it would stop testing the timeout at all.
    closes = [100.0, (100.0, 111.0, 99.5, 110.5)] + [(108.0, 109.0, 107.0, 108.0)] * 20
```

- [ ] **Step 22: Tighten the win-never-negative property test to the new floor**

The old bound `r_total >= 0.5*rr` is now strictly weaker than the model guarantees: the runner leg can never realize less than `RUNNER_FLOOR_FRACTION * rr`, so the blended floor is `(0.5 + 0.5 * RUNNER_FLOOR_FRACTION) * rr == 0.8333 * rr`. Across the 50 seeded walks the smallest observed slack against that bound is `-0.00067` (pure `round(..., 3)` noise on the two legs), so the tolerance is `0.002` absolute. Replace lines 184-200:

```python
def test_win_never_goes_negative_property():
    # 50 seeded random walks: whenever scale_out reports a win, r_total must
    # be >= (tp1_fraction + runner_fraction * RUNNER_FLOOR_FRACTION) * rr --
    # leg 1 banked at TP1, the runner leg floored at the v39 runner floor
    # rather than at breakeven. That is 0.8333*rr, up from the pre-v39
    # 0.5*rr. The 0.002 slack absorbs plan_engine's round(..., 3) on each
    # leg (measured worst case across these 50 seeds: -0.00067).
    rng = np.random.RandomState(42)
    floor_multiple = 0.5 + 0.5 * RUNNER_FLOOR_FRACTION
    violations = []
    for k in range(50):
        closes = list(100.0 * np.cumprod(1 + rng.normal(0.001, 0.02, 60)))
        df = make_ohlcv(closes)
        plan = _plan(direction="bullish",
                     stop_loss=closes[0] * 0.95, tp1=closes[0] * 1.04,
                     trigger_price=closes[0], tp2=None, horizon_key="4w")
        result = simulate_exit(df, signal_index=0, plan=plan, scale_out=True)
        if result.outcome == "win":
            rr = (plan.tp1 - closes[0]) / (closes[0] - plan.stop_loss)
            if result.r_total < floor_multiple * rr - 0.002:
                violations.append((k, result.r_total, floor_multiple * rr))
    assert not violations, violations
```

- [ ] **Step 23: Update `test_runner_timeout_floors_at_protective_stop_when_tp1_on_last_bar`**

The mechanism (the runner-phase loop is empty because `tp1_index == end`, so the timeout clamps to the never-ratcheted initial stop) is unchanged and now demonstrates more: the clamp lands on `106.667`, not `100.0`. Replace lines 224-230:

```python
    assert result.outcome == "win"
    assert result.runner_outcome == "runner_timeout"
    assert result.exit_index == 14
    # Clamped to runner_stop -- the v39 runner floor (106.666...7), which the
    # empty runner loop never ratcheted -- not the raw close (96).
    assert result.legs[1]["exit_price"] == pytest.approx(106.66666666666667)
    assert result.legs[1]["r"] == pytest.approx(1.333)
    assert result.r_total == pytest.approx(1.667)
    assert result.r_total >= 0.5 * rr - 1e-9   # the invariant the bug violated
```

- [ ] **Step 24: Re-base `test_runner_timeout_uses_checked_stop_not_post_ratchet_trail`**

This test's whole scenario — surviving a quiet decline from `108.0` down to `103.6` without any stop triggering, so that bar 13's timeout clamp can be inspected — happens entirely **below** a `106.667` floor, so under the new code it would close `runner_be` on bar 4 and never reach the timeout. Fixing it by moving the bars would destroy the pinned `atr(14)[13] == 1.488244065325937` the test is built around.

Instead lower the plan's TP1 from `110.0` to `102.0`, which moves the floor to `101.33333333333333` — below the `103.0` `checked_stop` this test already relies on, so the floor is never the binding constraint and every relationship the test pins is preserved exactly: `checked_stop (103.0) < close[end] (104.0) < post_ratchet_trail (104.27938983668516)`. The dataframe is byte-for-byte unchanged, so `atr13` stays `1.488244065325937`. Only `rr` and the two leg R-multiples move (`rr` becomes `(102-100)/5 == 0.4`).

Replace lines 262-290:

```python
    decline = [108.0 - 0.4 * k for k in range(1, 12)]   # 11 bars: 107.6 .. 103.6
    closes = ([100.0, (100.0, 111.0, 99.5, 108.0)]              # 0: entry, 1: TP1 touch (peak close=108)
              + [(c, c * 1.002, c * 0.998, c) for c in decline]  # 2-12: gradual quiet decline
              + [(103.7, 104.5, 103.5, 104.0)])                 # 13 (=end, n=14 rows): timeout bar
    df = make_ohlcv(closes)
    assert len(df) == 14

    # Verify the real ATR(14) value driving the post-ratchet (buggy) trail
    # on this exact constructed df, rather than hand-waving the arithmetic.
    atr13 = float(atr_indicator(df, 14).iloc[13])
    assert atr13 == pytest.approx(1.488244065325937)
    checked_stop = 108.0 - 2.5 * 2.0          # fallback-ATR ratchet, pinned through bars 2-12
    post_ratchet_trail = 108.0 - 2.5 * atr13  # the buggy (unchecked) value
    assert checked_stop == pytest.approx(103.0)
    assert post_ratchet_trail == pytest.approx(104.27938983668516)
    assert checked_stop < 104.0 < post_ratchet_trail   # close sits strictly between the two

    # v39: tp1 is 102, not 110, ON PURPOSE. The runner floor is
    # runner_floor(100, 102) == 101.333, comfortably BELOW checked_stop
    # (103.0), so this fixture's quiet decline still survives to the bar-13
    # timeout and the clamp -- not the floor -- is what it probes. With
    # tp1=110 the floor would be 106.667, above the entire decline, and the
    # runner would close runner_be on bar 4 instead.
    plan = _plan(direction="bullish", stop_loss=95.0, tp1=102.0, tp2=None,
                 horizon_key="2w")
    assert runner_floor(100.0, 102.0) < checked_stop
    result = simulate_exit(df, signal_index=0, plan=plan, scale_out=True)
    rr = 0.4                                   # (102 - 100) / 5
    assert result.outcome == "win"
    assert result.runner_outcome == "runner_timeout"
    assert result.exit_index == 13
    # Fixed: reports the bar's real close (104.0), NOT the inflated
    # post-ratchet trail (104.27938983668516) that was never checked.
    assert result.legs[0]["exit_price"] == pytest.approx(102.0)
    assert result.legs[0]["r"] == pytest.approx(rr)
    assert result.legs[1]["exit_price"] == pytest.approx(104.0)
    assert result.legs[1]["r"] == pytest.approx(0.8)
    assert result.r_total == pytest.approx(0.6)
```

- [ ] **Step 25: Run the backtest exit-walk tests**

Run: `python scripts/dev/testrun.py file tests/planning/test_exit_sim_scaleout.py`
Expected: PASS, `0 failed`. `test_runner_rides_to_tp2`, `test_tp2_none_means_runner_ignores_it`, `test_pre_tp1_loss_is_identical_to_single_leg`, `test_trail_never_ratchets_backwards`, `test_chandelier_stop_pure_function` and `test_legs_fractions_always_sum_to_one` were all traced under the new floor and need no edits.

- [ ] **Step 26: Run the neighbouring planning tests**

Run each and expect `0 failed`:
```bash
python scripts/dev/testrun.py file tests/planning/test_exit_sim_single.py
python scripts/dev/testrun.py file tests/planning/test_plan_manager_partial.py
python scripts/dev/testrun.py file tests/edge/test_edge_stops.py
python scripts/dev/testrun.py file tests/backtesting/test_backtest_engine.py
```
`test_edge_stops.py` sets `working_stop` as a literal fixture value and never derives it, so it is unaffected. `test_backtest_engine.py`'s cache-gated tests assert inequalities (`v2_t.r_multiple >= v1_t.r_multiple * TP1_FRACTION - 0.02`) and the existence of at least one `runner_be` win — both strictly easier to satisfy under a higher floor. If the OHLCV cache is absent these skip; that is expected, not a failure.

- [ ] **Step 27: Syntax gate**

Run: `python -m py_compile swingbot/core/planning/plan_engine.py swingbot/core/planning/plan_manager.py`
Expected: no output.

- [ ] **Step 28: Commit**

```bash
git add swingbot/core/planning/plan_engine.py swingbot/core/planning/plan_manager.py \
        tests/planning/test_plan_manager_active.py tests/planning/test_exit_sim_scaleout.py
git commit -m "feat: runner stop starts at 2/3 of the TP1 move, not breakeven

v39. plan_engine.runner_floor(entry, tp1) is the single source both the
live plan manager (_step_active, _check_bar_active) and the backtest exit
walk (_scale_out_exit_walk) use for the runner's stop the instant TP1
fires. The runner_be/tp1_runner_be reason strings are unchanged -- only
the comparison that selects them moved from == entry to == runner_floor."
```

---

### Task 2: Boundary coverage for the new floor

**Files:**
- Test: `tests/planning/test_plan_manager_partial.py` (append; also one edit at line 49-59)
- Test: `tests/planning/test_exit_sim_scaleout.py` (append)

**Interfaces:**
- Consumes: `plan_engine.runner_floor(entry: float, tp1: float) -> float` and `plan_engine.RUNNER_FLOOR_FRACTION: float` from Task 1.
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Write the failing backtest-side tests**

Append to `tests/planning/test_exit_sim_scaleout.py`:

```python
# ---------------------------------------------------------------------------
# v39: the runner floor. The formula itself, both directions, and the
# boundary guard proving the stop is no longer plain breakeven.
# ---------------------------------------------------------------------------

def test_runner_floor_is_two_thirds_of_the_tp1_move():
    # One formula, no is_bull branch: (tp1 - entry) carries the sign.
    assert RUNNER_FLOOR_FRACTION == pytest.approx(2.0 / 3.0)
    assert runner_floor(100.0, 110.0) == pytest.approx(106.66666666666667)
    assert runner_floor(100.0, 90.0) == pytest.approx(93.33333333333333)
    # A degenerate plan whose tp1 sits on entry floors at entry, exactly as
    # the pre-v39 model did. (_scale_out_exit_walk returns "no_trade" before
    # ever reaching phase 2 when risk <= 0, so that case never gets here.)
    assert runner_floor(100.0, 100.0) == pytest.approx(100.0)


def test_bullish_runner_stops_at_the_floor_not_at_plain_breakeven():
    # Bar 2 dips to 103.0 -- ABOVE the old breakeven floor (entry 100) and
    # BELOW the v39 floor (106.666...7). Pre-v39 this bar survived and the
    # trade timed out at that bar's close (104.0, r_total 1.4); now it must
    # close at the floor. This is the regression guard: if the boundary
    # silently reverted to entry, this test fails.
    df = make_ohlcv([
        100.0,
        (100.0, 111.0, 99.5, 110.5),     # 1: TP1 banked
        (110.0, 110.5, 103.0, 104.0),    # 2: low between old BE and the new floor
    ])
    plan = _plan(direction="bullish", stop_loss=95.0, tp1=110.0, tp2=None)
    result = simulate_exit(df, signal_index=0, plan=plan, scale_out=True)
    assert result.outcome == "win"
    assert result.runner_outcome == "runner_be"
    assert result.exit_index == 2
    assert result.legs[1]["exit_price"] == pytest.approx(106.66666666666667)
    assert result.legs[1]["r"] == pytest.approx(1.333)
    assert result.r_total == pytest.approx(1.667)


def test_bearish_runner_stops_at_the_floor_not_at_plain_breakeven():
    # Mirror image: bar 2 rallies to 97.0 -- BELOW the old breakeven floor
    # (entry 100) and ABOVE the v39 floor (93.333...3). Pre-v39 this
    # survived to a 96.0 timeout (r_total 1.4).
    df = make_ohlcv([
        100.0,
        (100.0, 100.5, 89.0, 90.5),      # 1: TP1 banked
        (91.0, 97.0, 90.5, 96.0),        # 2: high between the new floor and old BE
    ])
    plan = _plan(direction="bearish", stop_loss=105.0, tp1=90.0, tp2=None)
    result = simulate_exit(df, signal_index=0, plan=plan, scale_out=True)
    assert result.outcome == "win"
    assert result.runner_outcome == "runner_be"
    assert result.exit_index == 2
    assert result.legs[1]["exit_price"] == pytest.approx(93.33333333333333)
    assert result.legs[1]["r"] == pytest.approx(1.333)
    assert result.r_total == pytest.approx(1.667)
```

- [ ] **Step 2: Run them to verify they fail if the floor is absent**

Run: `python scripts/dev/testrun.py file tests/planning/test_exit_sim_scaleout.py`
Expected: PASS (Task 1 already landed the implementation). To confirm these are genuine guards rather than tautologies, temporarily revert `runner_stop = runner_floor(entry_price, tp1)` to `runner_stop = entry_price` in `plan_engine.py`, re-run, and confirm both new `*_not_at_plain_breakeven` tests FAIL with `runner_timeout`/`1.4` — then restore the line before continuing. Do not commit the reverted state.

- [ ] **Step 3: Write the failing live-path tests**

Append to `tests/planning/test_plan_manager_partial.py`:

```python
# ---------------------------------------------------------------------------
# v39: the runner floor on the live poll path and the overnight bar-check
# path. FLOOR / BEAR_FLOOR are plan_engine.runner_floor's values for the two
# fixture plans, written out so a drift in the constant fails loudly here.
# ---------------------------------------------------------------------------

FLOOR = 106.66666666666667        # runner_floor(100.0, 110.0)
BEAR_FLOOR = 93.33333333333333    # runner_floor(100.0,  90.0)


def _bear_active(**kw):
    p = _plan(entry_type="market", direction="bearish", trigger_price=100.0,
              entry_price=100.0, stop_loss=105.0, tp1=90.0, tp2=None, **kw)
    record_transition(p, PlanStatus.ACTIVE, reason="market_entry", at="t0")
    return p


def _bear_partial_env(tmp_path, prices):
    feed = FakePriceFeed()
    feed.set_series("AAPL", [89.5] + list(prices))
    store = PlanStore(path=str(tmp_path / "plans.json"))
    store.add(_bear_active())
    mgr = PlanManager(store, feed.get_price)
    assert [e.transition for e in mgr.poll()] == ["tp1_partial"]
    return store, mgr


def test_tp1_sets_the_working_stop_to_the_runner_floor(tmp_path):
    store, _ = _partial_env(tmp_path, [])
    assert store.get("p1").working_stop == pytest.approx(FLOOR)
    assert store.get("p1").working_stop == pytest.approx(runner_floor(100.0, 110.0))


def test_bearish_tp1_sets_the_working_stop_to_the_runner_floor(tmp_path):
    store, _ = _bear_partial_env(tmp_path, [])
    assert store.get("p1").working_stop == pytest.approx(BEAR_FLOOR)


def test_pullback_to_exactly_the_floor_closes_the_runner_as_be(tmp_path):
    store, mgr = _partial_env(tmp_path, [FLOOR])
    events = mgr.poll()
    assert [e.transition for e in events] == ["closed"]
    assert events[0].detail["reason"] == "tp1_runner_be"
    assert events[0].detail["exit_price"] == pytest.approx(FLOOR)
    assert store.get("p1").legs_realized[1]["r"] == pytest.approx(4.0 / 3.0)


def test_pullback_between_old_breakeven_and_the_floor_now_closes(tmp_path):
    # THE regression guard. 103.0 is above the pre-v39 breakeven floor
    # (entry 100) and below the v39 floor, so pre-v39 the runner stayed open
    # here. It must now close. The live path fills at the observed price
    # (103.0), not at the stop level -- that is the existing live-vs-backtest
    # fill convention (_close_runner takes `price`), unchanged by v39.
    store, mgr = _partial_env(tmp_path, [103.0])
    events = mgr.poll()
    assert [e.transition for e in events] == ["closed"]
    assert events[0].detail["reason"] == "tp1_runner_be"
    assert events[0].detail["exit_price"] == pytest.approx(103.0)
    assert store.get("p1").status == PlanStatus.CLOSED
    assert store.get("p1").legs_realized[1]["r"] == pytest.approx(0.6)


def test_price_just_above_the_floor_keeps_the_runner_open(tmp_path):
    # The other side of the same boundary: 107.0 clears the floor, so the
    # runner rides on with its stop untouched.
    store, mgr = _partial_env(tmp_path, [107.0])
    assert mgr.poll() == []
    assert store.get("p1").status == PlanStatus.PARTIAL
    assert store.get("p1").working_stop == pytest.approx(FLOOR)


def test_check_bar_tp1_sets_the_runner_floor_and_closes_at_it(tmp_path):
    # Overnight bar-check path (_check_bar_active / _check_bar_partial) must
    # mirror the poll path exactly.
    store = PlanStore(path=str(tmp_path / "plans.json"))
    store.add(_active())
    mgr = PlanManager(store, lambda t: 100.0)
    events = mgr.check_bar("p1", bar_open=109.0, bar_high=111.0, bar_low=108.0)
    assert [e.transition for e in events] == ["tp1_partial"]
    assert store.get("p1").working_stop == pytest.approx(FLOOR)
    events = mgr.check_bar("p1", bar_open=107.0, bar_high=107.5, bar_low=100.0)
    assert [e.transition for e in events] == ["closed"]
    assert events[0].detail["reason"] == "tp1_runner_be"
    # gap_stop_fill(107.0, 106.667, "bullish") == 106.667 -- the bar opened
    # above the floor, so the stop fills at the floor, not at the open.
    assert events[0].detail["exit_price"] == pytest.approx(FLOOR)
    assert store.get("p1").legs_realized[1]["r"] == pytest.approx(4.0 / 3.0)


def test_check_bar_bearish_tp1_sets_the_runner_floor_and_closes_at_it(tmp_path):
    store = PlanStore(path=str(tmp_path / "plans.json"))
    store.add(_bear_active())
    mgr = PlanManager(store, lambda t: 100.0)
    events = mgr.check_bar("p1", bar_open=91.0, bar_high=92.0, bar_low=89.0)
    assert [e.transition for e in events] == ["tp1_partial"]
    assert store.get("p1").working_stop == pytest.approx(BEAR_FLOOR)
    events = mgr.check_bar("p1", bar_open=93.0, bar_high=100.0, bar_low=92.5)
    assert [e.transition for e in events] == ["closed"]
    assert events[0].detail["reason"] == "tp1_runner_be"
    assert events[0].detail["exit_price"] == pytest.approx(BEAR_FLOOR)
    assert store.get("p1").legs_realized[1]["r"] == pytest.approx(4.0 / 3.0)


def test_legacy_partial_without_a_working_stop_falls_back_to_the_floor(tmp_path):
    # A PARTIAL plan persisted to data/plans.json before v39 has
    # working_stop set to the old breakeven -- or, for the oldest records,
    # to None. The None fallback resolves to the v39 floor (not entry), so
    # legacy live runners are tightened too and the reason label stays
    # correct rather than mislabelling a floor exit as "trail".
    feed = FakePriceFeed()
    feed.set_series("AAPL", [103.0])
    store = PlanStore(path=str(tmp_path / "plans.json"))
    store.add(_plan(direction="bullish", entry_type="market",
                    trigger_price=100.0, entry_price=100.0, stop_loss=95.0,
                    tp1=110.0, tp2=None, status=PlanStatus.PARTIAL,
                    working_stop=None,
                    legs_realized=[{"fraction": 0.5, "exit_price": 110.0,
                                    "r": 2.0, "reason": "tp1"}]))
    mgr = PlanManager(store, feed.get_price)
    events = mgr.poll()
    assert [e.transition for e in events] == ["closed"]
    assert events[0].detail["reason"] == "tp1_runner_be"
    assert events[0].detail["exit_price"] == pytest.approx(103.0)
```

These need three more imports. Replace lines 3-7 of `tests/planning/test_plan_manager_partial.py`:

```python
from swingbot.core.planning.plan_engine import (PlanStatus, record_transition,
                                                runner_floor)
from swingbot.core.planning.plan_manager import PlanManager
from swingbot.core.planning.plan_store import PlanStore
from tests.fake_feed import FakePriceFeed
from tests.planning.test_plan_engine_model import _plan
from tests.planning.test_plan_manager_active import _active
```

- [ ] **Step 4: Strengthen the existing trail test's floor claim**

`test_trail_ratchets_and_closes` already proves the chandelier trail carries the stop past the floor, but never says so. Replace lines 53-54 of `tests/planning/test_plan_manager_partial.py`:

```python
    assert mgr.poll() == []                      # 120: trail -> max(floor, 115)
    assert store.get("p1").working_stop == 115.0
    assert store.get("p1").working_stop > FLOOR  # floor is a start, not a ceiling
```

- [ ] **Step 5: Run both test files**

```bash
python scripts/dev/testrun.py file tests/planning/test_plan_manager_partial.py
python scripts/dev/testrun.py file tests/planning/test_exit_sim_scaleout.py
```
Expected: `0 failed` for both.

- [ ] **Step 6: Commit**

```bash
git add tests/planning/test_plan_manager_partial.py tests/planning/test_exit_sim_scaleout.py
git commit -m "test: pin the v39 runner floor boundary on both exit paths

Exact floor value in both directions, a pullback to exactly the floor
closing as tp1_runner_be, a pullback between the OLD breakeven (entry) and
the new floor now closing where it used to survive, a price just above the
floor still riding, the overnight bar-check mirror, and the legacy
working_stop=None fallback."
```

---

# Phase 2 — The copy that would now lie

*Tasks 3 and 4 are Group 2: parallel with each other, both after Task 2.*

### Task 3: Reword the two Discord strings that claim break-even

**Files:**
- Modify: `swingbot/core/scanning/embeds.py:1002` and `:1031-1032`
- Test: `tests/scanning/test_transition_embeds.py:28-33`

**Interfaces:**
- Consumes: nothing from Tasks 1-2 at the code level (this is copy only); it is sequenced after them so the copy never describes behaviour that has not shipped.
- Produces: nothing.

**Do not touch** `_EVENT_STYLE["be_moved"]` (line 996) or `_CLOSE_STYLE["scratch"]` (line 1001). Those describe the pre-TP1 `BREAKEVEN_TRIGGER_FRACTION` mechanism, which is frozen and out of scope — their "break-even" wording is still accurate.

- [ ] **Step 1: Update the failing copy assertion**

Replace lines 28-33 of `tests/scanning/test_transition_embeds.py`:

```python
def test_tp1_partial_embed_mentions_runner_and_its_floor():
    e = _embed("tp1_partial", {"fraction": 0.5, "exit_price": 110.0, "r": 2.0})
    assert "💰" in e.title
    joined = " ".join(f.value or "" for f in e.fields)
    assert "runner" in joined.lower()
    # v39: the runner's stop is no longer break-even, so the copy must not
    # say so -- it names the fraction of the TP1 move the floor protects.
    assert "2/3 of the tp1 move" in joined.lower()
    assert "break-even" not in joined.lower()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/scanning/test_transition_embeds.py::test_tp1_partial_embed_mentions_runner_and_its_floor -v`
Expected: FAIL — `assert '2/3 of the tp1 move' in 'runner active, stop at break-even'`

- [ ] **Step 3: Reword the close-reason title**

Replace line 1002 of `swingbot/core/scanning/embeds.py`:

```python
    "tp1_runner_be":   ("🟢 Win — runner closed at its floor — {ticker}", discord.Color.green()),
```

- [ ] **Step 4: Reword the tp1_partial "Runner" field**

Replace lines 1031-1032 of `swingbot/core/scanning/embeds.py`:

```python
        embed.add_field(name="Runner",
                        value="runner active, stop protecting 2/3 of the TP1 move",
                        inline=False)
```

- [ ] **Step 5: Run the embed tests**

Run: `python scripts/dev/testrun.py file tests/scanning/test_transition_embeds.py`
Expected: `0 failed`. `test_close_reasons_have_distinct_copy` still sees five distinct titles: "Stopped out", "Scratched at break-even", "runner closed at its floor", "runner hit TP2", "trail locked profit".

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/scanning/embeds.py tests/scanning/test_transition_embeds.py
git commit -m "fix: Discord copy no longer claims the runner sits at break-even

v39 moved the runner's floor to 2/3 of the TP1 move; the tp1_partial
'Runner' field and the tp1_runner_be close title said break-even. The
pre-TP1 be_moved/scratch copy is a different mechanism and is untouched."
```

---

### Task 4: Mark the pre-v39 backtest numbers stale

**Files:**
- Modify: `swingbot/config.py:461-465`
- Modify: `docs/features.md:28` and after `:36`

**Interfaces:**
- Consumes: nothing. Documentation only.
- Produces: nothing.

Per the spec's rollout decision, v39 ships default-on with **no** TRAIN/VALIDATION pre-registration. The staleness note is the honesty mechanism that replaces the validation gate. This does **not** touch `docs/claude/backtest-methodology.md`'s closed-pre-registrations table — no new pre-registered run is being claimed.

- [ ] **Step 1: Correct and annotate the `SCALE_OUT_ENABLED` help text**

Replace lines 461-465 of `swingbot/config.py`:

```python
    Field("SCALE_OUT_ENABLED", "SCALE_OUT_ENABLED", "Plan Engine v2", "Scale-out exits enabled",
          type="checkbox", default="true",
          help="At TP1, close 50% and move the stop to the runner floor -- entry plus 2/3 of "
               "the entry-to-TP1 move (v39, was plain break-even) -- while the runner rides "
               "toward TP2 behind a chandelier ATR trail that only ever ratchets that floor "
               "further into profit. STALE NUMBERS: the win-rate/expectancy figures in README's "
               "Plan Engine v2 section were measured under the pre-v39 break-even floor and have "
               "not been re-measured against this one. v39 is strictly more protective of realized "
               "gains, never less, so it shipped without a fresh pre-registration; a TRAIN/"
               "VALIDATION run against the new floor is future work, not a gate this shipped behind."),
```

- [ ] **Step 2: Correct the `docs/features.md` flag table**

Replace line 28 of `docs/features.md`:

```markdown
| `SCALE_OUT_ENABLED` | `true`/`false` | At TP1, close 50% and move the stop to the **runner floor** — entry plus 2/3 of the entry→TP1 move (v39; it was plain break-even before) — while the runner rides toward TP2 with a chandelier ATR trail that only ratchets that floor further into profit. Enable only after `PLAN_ENGINE_V2=on` has run cleanly. |
```

- [ ] **Step 3: Add the staleness note**

Insert after line 36 of `docs/features.md` (the paragraph ending "enable scale-out + manager."), as its own paragraph:

```markdown
**The validated numbers below predate v39's runner floor.** Every win-rate
and expectancy figure quoted for the scale-out exit model was measured with
the runner's stop starting at plain break-even. v39 starts it at
`entry + 2/3 × (tp1 − entry)` instead (`plan_engine.runner_floor`), which is
strictly more protective of realized gains and never less — so it shipped
default-on without a pre-registered re-validation, unlike every entry in
`docs/claude/backtest-methodology.md`'s closed-pre-registrations table.
Treat the cited numbers as a floor on the new model's performance, not a
measurement of it, until a fresh TRAIN/VALIDATION run against the new floor
is done.
```

- [ ] **Step 4: Verify the config schema still parses**

Run: `python scripts/dev/testrun.py file tests/test_config_schema.py`
Expected: `0 failed`. If that file does not exist, run `python -c "from swingbot import config; print(len(config.FIELDS))"` instead and expect a number with no traceback.

- [ ] **Step 5: Commit**

```bash
git add swingbot/config.py docs/features.md
git commit -m "docs: flag the pre-v39 scale-out numbers as stale

SCALE_OUT_ENABLED's help text and features.md both described the runner's
stop as moving to break-even at TP1, and cited win-rate/expectancy figures
measured under that model. Both now describe the v39 runner floor and say
plainly that the cited numbers have not been re-measured against it."
```

---

# Phase 3 — Release

### Task 5: Bump `bot` to 1.3.1 and regenerate the version matrix

**Files:**
- Modify: `VERSION.json`
- Modify: `swingbot/admin/version_history.json` (generated — do not hand-edit)

**Interfaces:**
- Consumes: Tasks 1-4, all committed and green.
- Produces: nothing.

- [ ] **Step 1: Run the full suite as the pre-release gate**

Run: `python scripts/dev/testrun.py full`
Expected: `0 failed` and `0 xfailed`. Reference baseline is `1686 passed, 66 skipped, 0 failed` — a *changed* pass count is not a failure (this plan adds tests), only `failed` is.

- [ ] **Step 2: Bump `VERSION.json`**

Set `"bot"` to `"1.3.1"` (patch: a tuning change to an existing mechanism — the runner's starting stop — not a new capability). Set `"bot_updated"` to the current UTC timestamp in `YYYY-MM-DD HH-MM-SS` form. Leave `ui` and `ui_updated` untouched.

- [ ] **Step 3: Commit the bump on its own**

```bash
git add VERSION.json
git commit -m "release(bot): 1.3.1 -- runner stop starts at 2/3 of the TP1 move"
```

- [ ] **Step 4: Regenerate the version matrix**

The generator walks `git log` for `VERSION.json`, so it must run **after** the bump commit or it records a `"commit": "uncommitted"` placeholder.

Run: `python scripts/dev/build_version_matrix.py`

- [ ] **Step 5: Verify the regenerated artifact**

Run: `python scripts/dev/testrun.py file tests/scripts/test_build_version_matrix.py`
Expected: `0 failed`. `test_the_committed_file_matches_the_current_generator` asserts the frozen file's `current` pair equals `VERSION.json` — a bump without a regeneration is a red suite, and the pre-bump full run in Step 1 structurally cannot catch it.

- [ ] **Step 6: Commit the artifact**

```bash
git add swingbot/admin/version_history.json
git commit -m "chore(bot): 1.3.1 -- runner stop starts at 2/3 of the TP1 move"
```

- [ ] **Step 7: Close out the documents**

```bash
git mv docs/superpowers/specs/2026-08-20-v39-runner-floor-protection-design.md \
       docs/superpowers/specs/implemented/
git mv docs/superpowers/plans/2026-08-20-v39-runner-floor-protection.md \
       docs/superpowers/plans/implemented/
```

Add a Progress block to the top of the moved plan recording what shipped, then re-point any reference to either path that this move dangles, and commit all of it together:

```bash
git add docs/superpowers/specs docs/superpowers/plans
git commit -m "docs: close v39 runner floor protection"
```
