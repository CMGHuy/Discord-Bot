# v173 Execution fidelity, part 3b: override-bar state and the frozen verdict

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task with `grep -n "^### Task V173-23:" -A 400 <this file>`; never read the file whole.

**Spec:** [`docs/superpowers/specs/2026-10-18-v173-execution-fidelity-overrides-design.md`](../specs/2026-10-18-v173-execution-fidelity-overrides-design.md) §3 (the `ambiguous` status, the summary), §4 (the frozen verdict rule) and `## Plan panel review` (breakeven arming and stop moves on the override bar, `waiting_on`, the before-costs mean, the Postgres verdict record and its jsonl mirror)
**Bump:** bot minor; ui minor (applied once, in V173-17)
**Edge:** none (integrity)
**Index:** [`2026-10-18-v173-execution-fidelity-overrides_0-index.md`](2026-10-18-v173-execution-fidelity-overrides_0-index.md) carries the Goal, `## Global Constraints`, `## Parallelisation`, `## Where to work` (`$WT`, `$R`), the task ledger, `## Handoff` and `## Revision 2026-10-19`. Every task below implicitly includes those Global Constraints, in particular **Replay, two frames, no lookahead**, **Status precedence**, **Counted rows**, **Verdict**, **Stored verdict record**, **jsonl mirror**, **Report payload** and **`build_report`**.

Tasks: V173-23, then V173-10 (both edit `swingbot/core/analytics/override_fidelity.py`; V173-10 also creates `override_verdict.py` and edits `stats.py`). Both need part 3's V173-9 and V173-22 committed on the branch first. Part 3c (`_3c-verdict-store.md`) continues with V173-24..V173-27; V173-26 consumes `build_report`, `evaluate_verdict`, `verdict_record` and `engine_flags` from V173-10.

**What earlier tasks created, per the index ledger** (check each with `git -C $WT grep -n "<name>" swingbot/core/analytics/override_fidelity.py` before starting; a missing one means an earlier task is not on the branch yet: stop and report, never re-create it here):

- V173-7: constants `STATUSES` (eight), `EXCLUDED_STATUSES` (six), `DEAD_BAND`, `VERDICT_FLOOR`, `WEEK_FLOOR`, `EXCLUDED_CAP`, `LEDGER_ID`; `OverrideRow` (20 fields, `delta_r_gross` after `delta_r`; property `entry_date`; `to_dict()` with `close_date` as ISO text); `ROW_FIELDS`; `outcome_of`; `is_override`; `state_at_close`.
- V173-8: `engine_frame(df, ov_idx)` (the override session's `High`/`Low` clamped to `max(Open, Close)`/`min(Open, Close)`), `engine_path(plan, df, fill_idx, *, indicator_df=None) -> ExitResult`.
- V173-9: `_Replay`, `_status(plan, rp, asof) -> tuple[str, ExitResult | None]` (replaced by V173-23), `_parity_broken`, `_ambiguous`, `_engine_arm`, `_still_open`, `replay_override(plan, bars, asof, trade=None) -> OverrideRow`; the test helpers `plan`, `frame`, `partial_frame`, `stamp`, `replay` and the bar constants in `tests/analytics/test_override_fidelity_replay.py`.
- V173-22: `trim_to_asof`, `missing_sessions`, `split_suspect`, the new `_admission`.

**Tests never touch a database** (Global Constraints): plain `TradePlanV2` objects, synthetic frames on real NYSE session dates, plain dicts for stored records. No `seed_store`, no `db_conn`, never the production replica. The table and its repository are part 3c's.

# Phase: Override-bar state and the verdict (V173-23, V173-10)

### Task V173-23: Override-bar state the clamped frame lacks: breakeven arming and stop moves → `ambiguous`

**Model:** opus — no-lookahead replay feeding a frozen verdict

**Files:**
- Modify: `swingbot/core/analytics/override_fidelity.py` (append a V173-23 section; replace V173-9's `_status` in place)
- Create: `tests/analytics/test_override_fidelity_bar_state.py`

**Interfaces:**
- Consumes (V173-8): `engine_frame(df, ov_idx) -> pd.DataFrame`, `engine_path(plan, df, fill_idx, *, indicator_df=None) -> ExitResult`. (V173-9): `_Replay`, `_admission` (as rewritten by V173-22), `_parity_broken(plan, real, rp)`, `_ambiguous(real, ov_idx)`, `_engine_arm(plan, rp)`, `_still_open(plan, eng, rp)`, `_status` (replaced here). (V173-6): `ExitResult.entry_index`, `exit_index`, `r_total`, `legs`. Library: `swingbot.core.backtesting.instrument.fills.target_touched(bar_high, bar_low, target, direction) -> bool` (fills.py:48); `exit_sim.GIVEBACK_EXTREME_BASIS` (exit_sim.py, v176, read at call time by `_giveback_extreme`).
- Produces: `be_armed(plan, high: float, low: float) -> bool`; `bar_state_differs(plan, real: ExitResult, engine: ExitResult, df: pd.DataFrame, ov_idx: int, state: str) -> bool`; private `_bar_hl(df, j) -> tuple[float, float]`, `_be_only_on_real_bar(plan, df, fill_idx, ov_idx) -> bool`. `_status` keeps its signature `(plan, rp, asof) -> tuple[str, ExitResult | None]`; V173-10's `build_report` reaches all of it through `replay_override`.

**Why this task exists** (index § Handoff trap): breakeven arming is a local in `exit_sim_v2._pre_tp1_v2` (`exit_sim_v2.py:155-156`, not 151-152 as the spec guessed): `stop_moved = True` when the bar's high (long) reaches `be_trigger = entry + sign × breakeven_trigger_fraction × |tp1 − entry|`, effective the next bar. `ExitResult` keeps no trace of it. The engine frame clamps the override bar's high/low, so a trigger touched only by the real bar's wick arms the real path and not the engine's; nothing in the two results shows it when the price never returns to the entry. The replay recomputes the trigger.

**Decisions this task makes inside the index's status precedence** (each has a test below):

1. **Rule A (breakeven):** `ambiguous` when the state at close is `ACTIVE`, the engine is still in the trade after the override session (`engine.exit_index > ov_idx`), the trigger is touched on the real override bar and not on the clamped one, **and it was not already touched on a bar between the fill and the override session** (bars `fill_idx + 1 .. ov_idx − 1`, the bars `_pre_tp1_v2` would have armed on; they are identical in both frames). Already armed, the clamp changes nothing, so marking the row would only spend the 20% exclusion cap. PARTIAL rows skip rule A: after TP1 the runner has no breakeven move.
2. **Rule B (any other state on the override bar):** `ambiguous` when the real frame exits after the override session and the real and engine results differ in `r_total` or in `legs`. The two frames differ only in that bar's high/low and both read indicators from the real frame (V173-21), so any difference is state the clamped bar lacks. A real exit **on** the override session is V173-9's `_ambiguous` rule's (stop or target) or a close-based exit both frames share; rule B leaves it alone.
3. **What rule B catches today.** The chandelier ratchet (`exit_sim._chandelier_ratchet`) reads the bar's close and the real-frame ATR, and v176's give-back on its default `"close"` basis reads closes too: neither sees the clamp. A runner stop that reads a bar's **high** does: v176's give-back on the `"high_low"` basis (`exit_sim.GIVEBACK_EXTREME_BASIS`). The runner test pins rule B on that path and pins the `"close"` basis as the control. Rule B also covers any future engine rule that reads a bar's range, with no change here.
4. **Order in `_status`:** after V173-9's `_ambiguous`, before `_still_open`, so a row that is both is `ambiguous` (the index precedence puts `ambiguous` above `open`).

- [ ] **Step 1: Write the failing test**

Create `$WT/tests/analytics/test_override_fidelity_bar_state.py`:

```python
"""v173 plan panel review: state the override bar gives the real path and the
clamped engine frame lacks -- breakeven arming, and stop moves that read the
bar's range -- marks the row ambiguous.

Frames from test_override_fidelity_replay: fill at index 15, override at 17
(Wed 2026-10-07), last bar 25; plan() is bullish, entry 100, stop 95, TP1
110, breakeven trigger 105, hold cap 8 (timeout at index 23).
"""
from types import SimpleNamespace

import pytest

from swingbot import config
from swingbot.core.analytics import override_fidelity as of
from swingbot.core.planning import exit_sim
from tests.analytics.test_override_fidelity_replay import (FILL_IDX, OV_IDX, frame,
                                                           partial_frame, plan, replay)
from tests.backtesting.test_pullback_dryup_witness import pin_code_defaults

HIGHER = (102.0, 103.0, 101.0, 102.0)    # low above the entry: a breakeven stop never fires
BE_WICK = (101.0, 106.0, 100.5, 102.0)   # high 106 >= 105; clamped high max(101, 102) = 102
BE_BODY = (101.0, 106.0, 100.5, 105.5)   # clamped high 105.5 >= 105: armed on both frames
AFTER_HIGHER = {i: HIGHER for i in range(18, 26)}
GB_WICK = (112.0, 120.0, 111.5, 113.0)   # runner override bar; clamped (112, 113, 112, 113)
GB_NEXT = (113.0, 113.5, 112.5, 113.0)


@pytest.fixture(autouse=True)
def _pinned(monkeypatch):
    pin_code_defaults(monkeypatch)
    monkeypatch.setattr(config, "STALL_EXIT_ENABLED", False)
    monkeypatch.setattr(config, "RUNNER_STRUCTURE_EXIT", "off")
    monkeypatch.setattr(config, "ADAPTIVE_RUNNER_TRAIL_ENABLED", False)


def both(p, df):
    """(real-frame result, engine-frame result) as replay_override walks them."""
    real = of.engine_path(p, df, FILL_IDX)
    eng = of.engine_path(p, of.engine_frame(df, OV_IDX), FILL_IDX, indicator_df=df)
    return real, eng


def result(exit_index, r_total=0.2, reason="timeout"):
    """A stand-in for ExitResult: bar_state_differs reads only these fields."""
    return SimpleNamespace(entry_index=FILL_IDX, exit_index=exit_index, r_total=r_total,
                           legs=[{"fraction": 1.0, "exit_price": 101.0, "r": r_total,
                                  "reason": reason, "kind": "close"}])


# -- be_armed ----------------------------------------------------------------

def test_be_armed_recomputes_the_walks_trigger():
    bull = plan()                                             # trigger 100 + 0.5 x 10 = 105
    assert of.be_armed(bull, 105.0, 100.0) is True
    assert of.be_armed(bull, 104.99, 100.0) is False
    bear = plan(direction="bearish", stop_loss=105.0, tp1=90.0)   # trigger 95
    assert of.be_armed(bear, 101.0, 95.0) is True
    assert of.be_armed(bear, 101.0, 95.01) is False


# -- rule A: breakeven armed only by the real override bar ---------------------

def test_breakeven_touched_only_on_the_real_override_bar_is_ambiguous():
    """Prices never come back to the entry, so the real and engine results
    are identical: only rule A can see the arming."""
    p, df = plan(), frame({OV_IDX: BE_WICK, **AFTER_HIGHER})
    real, eng = both(p, df)
    assert (real.r_total, real.legs) == (eng.r_total, eng.legs)
    assert eng.exit_index > OV_IDX
    row = replay(p, df)
    assert row.status == "ambiguous"
    assert (row.engine_r, row.delta_r, row.outcome) == (None, None, None)


def test_breakeven_from_the_wick_that_then_stops_out_is_ambiguous():
    """FLAT bars after the wick reach the entry: the real path takes a
    breakeven stop at index 18, the clamped engine rides to the timeout."""
    p, df = plan(), frame({OV_IDX: BE_WICK})
    real, eng = both(p, df)
    assert real.legs[-1]["reason"] == "breakeven_stop"
    assert eng.legs[-1]["reason"] == "timeout"
    assert replay(p, df).status == "ambiguous"


def test_breakeven_touched_on_the_clamped_bar_too_is_resolved():
    row = replay(plan(), frame({OV_IDX: BE_BODY}))
    assert (row.status, row.engine_exit_reason) == ("resolved", "breakeven_stop")


def test_breakeven_already_armed_before_the_override_is_resolved():
    row = replay(plan(), frame({16: BE_WICK, OV_IDX: BE_WICK, **AFTER_HIGHER}))
    assert (row.status, row.engine_exit_reason) == ("resolved", "timeout")


# -- rule B: a runner stop that reads the override bar's high ------------------

def _giveback(monkeypatch, basis):
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_ENABLED", True)
    monkeypatch.setattr(config, "RUNNER_GIVEBACK_PCT", 5.0)
    monkeypatch.setattr(exit_sim, "GIVEBACK_EXTREME_BASIS", basis)


def test_a_runner_whose_override_bar_high_moves_its_trailing_stop_is_ambiguous(monkeypatch):
    """The chandelier reads closes and the real-frame ATR, so the clamp never
    moves it. v176's give-back on the high_low basis reads the bar's high:
    the real override bar lifts its best price to 120 (stop 114, hit on the
    next bar), the clamped one only to 113."""
    _giveback(monkeypatch, "high_low")
    p, df = plan(partial=True), partial_frame({OV_IDX: GB_WICK, 18: GB_NEXT})
    real, eng = both(p, df)
    assert real.exit_index > OV_IDX
    assert (real.r_total, real.legs) != (eng.r_total, eng.legs)
    assert replay(p, df).status == "ambiguous"


def test_the_same_runner_on_the_close_basis_is_resolved(monkeypatch):
    _giveback(monkeypatch, "close")
    p, df = plan(partial=True), partial_frame({OV_IDX: GB_WICK, 18: GB_NEXT})
    real, eng = both(p, df)
    assert (real.r_total, real.legs) == (eng.r_total, eng.legs)
    assert replay(p, df).status == "resolved"


# -- bar_state_differs, rule by rule --------------------------------------------

def test_bar_state_differs_rule_by_rule():
    quiet, wick = frame(), frame({OV_IDX: BE_WICK})
    armed_early = frame({16: BE_WICK, OV_IDX: BE_WICK})
    same = result(23)
    assert of.bar_state_differs(plan(), same, same, quiet, OV_IDX, "ACTIVE") is False
    assert of.bar_state_differs(plan(), same, same, wick, OV_IDX, "ACTIVE") is True
    assert of.bar_state_differs(plan(), same, same, wick, OV_IDX, "PARTIAL") is False
    assert of.bar_state_differs(plan(), same, same, armed_early, OV_IDX, "ACTIVE") is False
    gone = result(OV_IDX)                       # engine out on the override session
    assert of.bar_state_differs(plan(), gone, gone, wick, OV_IDX, "ACTIVE") is False
    assert of.bar_state_differs(plan(), same, result(23, r_total=-0.1), quiet, OV_IDX,
                                "PARTIAL") is True
    assert of.bar_state_differs(plan(), same, result(23, reason="runner_trail"), quiet,
                                OV_IDX, "PARTIAL") is True
    # a real exit ON the override session is _ambiguous's call, not rule B's
    assert of.bar_state_differs(plan(), result(OV_IDX), result(23, r_total=-0.1), quiet,
                                OV_IDX, "ACTIVE") is False
```

The scenario arithmetic, checked against `walk_v2` when this plan was written: in the give-back case the give-back extreme seeds at the TP1 bar's high (111) on the `high_low` basis; the real override bar raises it to 120, so the stop checked on index 18 is `max(floor 106.67, chandelier, 120 × 0.95 = 114)` = 114 and `GB_NEXT`'s low 112.5 hits it; the clamped bar raises it only to 113 (stop 107.35), so the engine runs on to the FLAT bar at index 19. On the `close` basis both frames seed at the TP1 close (108) and see the override close 113, so both exit on index 19 identically. If either equality/inequality line fails, print `real` and `eng`: a changed give-back or chandelier rule since this plan was written is a report, not a reason to reshape the frame.

- [ ] **Step 2: Run it to verify it fails**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/analytics/test_override_fidelity_bar_state.py
```

Expected: FAIL with `AttributeError: module 'swingbot.core.analytics.override_fidelity' has no attribute 'be_armed'` (and `bar_state_differs`); `test_breakeven_touched_only_on_the_real_override_bar_is_ambiguous`, `test_breakeven_from_the_wick_that_then_stops_out_is_ambiguous` and `test_a_runner_whose_override_bar_high_moves_its_trailing_stop_is_ambiguous` read `resolved`. The three `resolved` tests may already pass.

- [ ] **Step 3: Implement**

In `$WT/swingbot/core/analytics/override_fidelity.py`, add `from swingbot.core.backtesting.instrument import fills` beside the other imports if it is missing. Append at the end of the module:

```python
# --------------------------------------------------------------------------
# V173-23: state the real override bar gives the walk and the clamped engine
# frame lacks (plan panel review). Breakeven arming is a local in
# exit_sim_v2._pre_tp1_v2 (:155-156) and leaves no trace in ExitResult, so
# it is recomputed; anything else shows as a difference between the two
# results, because the frames differ only in that bar's high and low.
# --------------------------------------------------------------------------

def be_armed(plan, high: float, low: float) -> bool:
    """walk_v2's breakeven trigger touched by a bar with this high and low."""
    entry = float(plan.entry_price)
    sign = 1 if plan.direction == "bullish" else -1
    trigger = entry + sign * plan.breakeven_trigger_fraction * abs(plan.tp1 - entry)
    return fills.target_touched(high, low, trigger, plan.direction)


def _bar_hl(df: pd.DataFrame, j: int) -> tuple[float, float]:
    return float(df["High"].iloc[j]), float(df["Low"].iloc[j])


def _be_only_on_real_bar(plan, df: pd.DataFrame, fill_idx: int, ov_idx: int) -> bool:
    """The real override bar arms breakeven, the clamped one does not, and no
    bar since the fill had armed it already."""
    if any(be_armed(plan, *_bar_hl(df, j)) for j in range(fill_idx + 1, ov_idx)):
        return False
    clamped = engine_frame(df, ov_idx)
    return (be_armed(plan, *_bar_hl(df, ov_idx))
            and not be_armed(plan, *_bar_hl(clamped, ov_idx)))


def bar_state_differs(plan, real: ExitResult, engine: ExitResult, df: pd.DataFrame,
                      ov_idx: int, state: str) -> bool:
    """Rule A: an ACTIVE plan armed only by the real override bar, the engine
    still in after it. Rule B: the real frame exits after the override bar
    and the two results differ."""
    if (state == "ACTIVE" and engine.exit_index > ov_idx
            and _be_only_on_real_bar(plan, df, real.entry_index, ov_idx)):
        return True
    return real.exit_index > ov_idx and (real.r_total != engine.r_total
                                         or real.legs != engine.legs)
```

Replace V173-9's `_status` **in place** (one definition in the module) with:

```python
def _status(plan, rp: _Replay, asof: dt.date) -> tuple[str, ExitResult | None]:
    """The row's status after _prepare, and the engine-frame result when resolved.

    The real frame decides parity and ambiguity (its tp1_index is read
    straight from engine_path's result, see _engine_arm); the engine arm is
    the clamped engine frame. V173-23: state the real override bar gives the
    walk and the clamped bar lacks is ambiguous too."""
    early = _admission(plan, rp, asof)
    if early is not None:
        return early, None
    real = engine_path(plan, rp.df, rp.fill_idx)
    if not real.legs:
        return "unreplayable", None
    if _parity_broken(plan, real, rp):
        return "parity_mismatch", None
    if _ambiguous(real, rp.ov_idx):
        return "ambiguous", None
    eng = _engine_arm(plan, rp)
    if bar_state_differs(plan, real, eng, rp.df, rp.ov_idx, rp.state):
        return "ambiguous", None
    if _still_open(plan, eng, rp):
        return "open", None
    return "resolved", eng
```

- [ ] **Step 4: Run the new test and the earlier override tests**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/analytics/test_override_fidelity_bar_state.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/analytics/test_override_fidelity_replay.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/analytics/test_override_fidelity_admission.py
```

Expected: all PASS, `0 failed`, `0 xfailed`. V173-9's tests stay green unchanged: no V173-9 override bar reaches the 105 trigger without also touching a level `_ambiguous` already catches, and every V173-9 runner frame has the give-back pinned off (`pin_code_defaults`) and the override bar's close inside its range, so the real and engine results agree. If one flips to `ambiguous`, print both results for it and report before changing anything.

- [ ] **Step 5: Complexity**

```bash
python -m radon cc -s -n C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/swingbot/core/analytics/override_fidelity.py
```

Expected: no output (`_status` about 8, `bar_state_differs` about 6, `_be_only_on_real_bar` about 4).

- [ ] **Step 6: Commit on the branch**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides add swingbot/core/analytics/override_fidelity.py tests/analytics/test_override_fidelity_bar_state.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides commit -m "feat(v173): override-bar state the clamped frame lacks marks the row ambiguous -- breakeven arming, range-reading stop moves"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

The last command checks the main tree stayed clean of branch edits.

### Task V173-10: `summarise`, the frozen verdict rule, stored-record and mirror shapes, ledger enums and `build_report`

**Model:** opus — statistical code feeding a frozen pre-registration

**Files:**
- Modify: `swingbot/core/analytics/override_fidelity.py` (append `summarise`; created by V173-7)
- Create: `swingbot/core/analytics/override_verdict.py`
- Modify: `swingbot/core/backtesting/instrument/stats.py:114-117` (`VERDICTS`)
- Modify: `tests/backtesting/test_instrument_stats_ledger.py:20-22` (the pinned `VERDICTS` tuple, index § Handoff)
- Create: `tests/analytics/test_override_summary.py`
- Create: `tests/analytics/test_override_verdict.py`

**Interfaces:**
- Consumes: V173-7's `OverrideRow` (keyword-constructed with its 20 fields; `to_dict()` gives `close_date` as ISO), `outcome_of`, `is_override`, `STATUSES`, `EXCLUDED_STATUSES`, `VERDICT_FLOOR`, `WEEK_FLOOR`, `EXCLUDED_CAP`, `DEAD_BAND`, `LEDGER_ID`, `ROW_FIELDS`; V173-9/22/23's `replay_override(plan, bars, asof, trade)`; `stats.week_cluster_bootstrap`, `stats.iso_week_key`, `stats.validate_ledger_row`, `stats.append_ledger_row`, `stats.load_ledger`, `stats.WEEK_BOOTSTRAP_RESAMPLES`, `stats.WEEK_BOOTSTRAP_SEED` (all in `swingbot/core/backtesting/instrument/stats.py`).
- Produces:
  - `override_fidelity.summarise(rows: list[OverrideRow]) -> dict`, keys exactly `n_by_status, bulk_n, bulk_dates, approx_n, counted_n, sum_delta_r, sum_delta_r_gross, sum_delta_usd, usd_missing_n, helped, hurt, neutral, splits`.
  - In `override_verdict.py`: `counted(rows) -> list`, `eligible(rows) -> list`, `conditions(rows) -> dict` (`n, weeks, open_n, excluded_share, evaluable, waiting_on`), `evaluate_verdict(rows) -> dict` (keys exactly `state, n, weeks, mean_delta_r, mean_delta_r_gross, ci, sum_delta_r, sum_delta_usd, bar_close_n, excluded_share`; `ValueError` unless evaluable), `verdict_record(verdict: dict, rows: list, engine_flags: dict, *, recorded_on: date) -> dict` (the stored-record shape of Global Constraints), `mirror_ledger_row(record: dict) -> dict`, `verdict_payload(rows, recorded: dict | None) -> dict` (never evaluates), `build_report(plans, trades_by_plan, bars_fn, asof, recorded: dict | None, currency_symbol) -> dict` (keys exactly `rows, summary, verdict, engine_flags, asof, currency_symbol`), `engine_flags() -> dict`; constants `RESULTS_RECORD`, `WAITING`, `COST`, `SAVED`, `INCONCLUSIVE`. V173-26's `run_daily_check` calls `build_report`, `evaluate_verdict(report["rows"])` and `verdict_record(verdict, report["rows"], report["engine_flags"], recorded_on=asof)`; V173-11 calls `mirror_ledger_row`; V173-12 and V173-11 call `build_report` with the stored record.
  - **Every verdict function accepts rows either as `OverrideRow` or as their `to_dict()` form**, so V173-26 can pass `report["rows"]` straight on.
  - `stats.VERDICTS` gains `"COST", "SAVED", "INCONCLUSIVE"` (appended, never `WAITING`).
  - Gone from the pre-revision version of this task (index § Revision 2026-10-19): `recorded_verdict(ledger_rows)`, `ledger_row(verdict, *, today)`, `SPEC_PATH`, and `ledger_rows` as a `build_report`/`verdict_payload` argument. No code reads the jsonl ledger to decide a verdict.

**Shapes this task fixes** (the index names the keys; V173-11..14 and V173-26 read the value types as written here):

- `n_by_status`: `{status: int}` over every value of `STATUSES` (eight), counting **eligible** rows only (`not bulk and not approx`; `unstamped` rows have `approx=False`, so they are eligible). Bulk rows are counted only in `bulk_n`, non-bulk approx rows only in `approx_n`, so `bulk_n + approx_n + sum(n_by_status.values()) == len(rows)` and no exclusion note counts a row twice.
- `bulk_dates`: `{iso_date: int}` sorted by date (one exclusion note line per key).
- `sum_delta_r` and `sum_delta_r_gross` (3 dp) and `sum_delta_usd` (2 dp; rows without dollars skipped and counted in `usd_missing_n`) are over counted rows; all three are `0.0` with no counted rows.
- `splits`: `{"state_at_close"|"horizon"|"direction": {value: {"n", "sum_delta_r", "sum_delta_usd"}}}` over counted rows, values sorted.
- `conditions`: `excluded_share` unrounded (the cap compares it); `waiting_on` a **list**, the failing subset of `("count", "weeks", "open", "excluded")` in that order, `[]` exactly when `evaluable`.
- `evaluate_verdict` and the stored record: `mean_delta_r`, `mean_delta_r_gross`, `sum_delta_r` 3 dp; `ci` `[lo, hi]` 3 dp; `sum_delta_usd` 2 dp over counted rows with dollars, `None` when none has dollars; `bar_close_n` = counted rows with `price_source == "bar_close"`; `excluded_share` 4 dp.
- `verdict_payload`: `excluded_share` 4 dp; `needed` = `VERDICT_FLOOR`, `week_floor` = `WEEK_FLOOR`. Recorded: `state` = the record's `verdict`, and `n, weeks, recorded_on, mean_delta_r, mean_delta_r_gross, ci, sum_delta_r, sum_delta_usd, bar_close_n` from the record; `open_n, excluded_share, evaluable, waiting_on` live. Not recorded: `state = "WAITING"` even when evaluable (only `run_daily_check` evaluates); `n`, `weeks` and `bar_close_n` live; `recorded_on` and the five mean/CI/sum fields `None`.
- The stored record's `rows`: the counted rows in `to_dict()` form (JSON-ready; `close_date` ISO text), in the order given.
- `engine_flags()`: `{"stall_exit_enabled": bool, "runner_structure_exit": str}`, read live from `config`.
- `build_report`'s `rows` are sorted newest `close_date` first, then `plan_id` descending.

- [ ] **Step 1: Write the failing summary test**

Create `$WT/tests/analytics/test_override_summary.py`:

```python
"""v173 §3: summarise -- descriptive totals over the counted rows only."""
from datetime import date

import pytest

from swingbot.core.analytics import override_fidelity as of

SUMMARY_KEYS = {"n_by_status", "bulk_n", "bulk_dates", "approx_n", "counted_n",
                "sum_delta_r", "sum_delta_r_gross", "sum_delta_usd", "usd_missing_n",
                "helped", "hurt", "neutral", "splits"}


def row(delta=0.2, day=date(2026, 8, 3), *, status="resolved", bulk=False, approx=False,
        usd=None, gross=None, price_source=None, state="ACTIVE", horizon="2w",
        direction="bullish", plan_id="p"):
    """One OverrideRow. A resolved row's gross delta defaults to delta + 0.01."""
    resolved = status == "resolved"
    return of.OverrideRow(
        plan_id=plan_id, ticker="T", horizon=horizon, direction=direction,
        state_at_close=state, close_date=day, bulk=bulk, approx=approx,
        price_source=price_source or ("session_close" if approx else "quote"),
        status=status, actual_r=delta, engine_r=0.0 if resolved else None,
        delta_r=delta if resolved else None,
        delta_r_gross=(round(delta + 0.01, 3) if gross is None else gross) if resolved else None,
        actual_usd=None, engine_usd=None, delta_usd=usd if resolved else None,
        engine_exit_reason="timeout" if resolved else None,
        outcome=of.outcome_of(delta if resolved else None), source="manual")


def test_keys_and_the_empty_summary():
    out = of.summarise([])
    assert set(out) == SUMMARY_KEYS
    assert out["n_by_status"] == {s: 0 for s in of.STATUSES}
    assert len(out["n_by_status"]) == 8
    assert (out["bulk_n"], out["bulk_dates"], out["approx_n"], out["counted_n"]) == (0, {}, 0, 0)
    assert (out["sum_delta_r"], out["sum_delta_r_gross"], out["sum_delta_usd"],
            out["usd_missing_n"]) == (0.0, 0.0, 0.0, 0)
    assert (out["helped"], out["hurt"], out["neutral"]) == (0, 0, 0)
    assert out["splits"] == {"state_at_close": {}, "horizon": {}, "direction": {}}


def test_rows_partition_into_counted_status_bulk_and_approx():
    rows = [row(0.2, usd=20.0), row(-0.3, usd=-30.0), row(0.05, usd=5.0),
            row(status="stale"), row(status="unstamped", price_source="none"),
            row(0.9, date(2026, 9, 30), bulk=True), row(-0.9, date(2026, 9, 30), bulk=True),
            row(1.5, approx=True)]
    out = of.summarise(rows)
    assert out["n_by_status"]["resolved"] == 3
    assert (out["n_by_status"]["stale"], out["n_by_status"]["unstamped"]) == (1, 1)
    assert sum(out["n_by_status"].values()) == 5
    assert (out["bulk_n"], out["bulk_dates"], out["approx_n"], out["counted_n"]) == (
        2, {"2026-09-30": 2}, 1, 3)
    assert out["bulk_n"] + out["approx_n"] + sum(out["n_by_status"].values()) == len(rows)
    assert out["sum_delta_r"] == pytest.approx(-0.05, abs=1e-9)
    assert out["sum_delta_usd"] == pytest.approx(-5.0, abs=1e-9)
    assert (out["helped"], out["hurt"], out["neutral"]) == (1, 1, 1)   # 0.05 sits on the band


def test_the_before_costs_sum_covers_counted_rows_only():
    rows = [row(0.2, gross=0.25), row(-0.3, gross=-0.28), row(0.5, bulk=True, gross=0.6),
            row(0.4, approx=True, gross=0.45)]
    assert of.summarise(rows)["sum_delta_r_gross"] == pytest.approx(-0.03, abs=1e-9)


def test_bulk_dates_one_key_per_day_sorted():
    rows = [row(bulk=True, day=date(2026, 9, 30)), row(bulk=True, day=date(2026, 8, 1)),
            row(bulk=True, day=date(2026, 9, 30))]
    assert list(of.summarise(rows)["bulk_dates"].items()) == [("2026-08-01", 1), ("2026-09-30", 2)]


def test_rows_without_dollars_stay_in_the_r_sum_and_are_counted_missing():
    out = of.summarise([row(0.4, usd=40.0), row(0.6, usd=None)])
    assert out["sum_delta_r"] == pytest.approx(1.0)
    assert out["sum_delta_usd"] == pytest.approx(40.0)
    assert out["usd_missing_n"] == 1


@pytest.mark.parametrize("delta, outcome", [(0.051, "helped"), (0.05, "neutral"),
                                            (-0.05, "neutral"), (-0.051, "hurt")])
def test_the_dead_band_is_frozen_at_five_hundredths(delta, outcome):
    assert of.DEAD_BAND == 0.05
    out = of.summarise([row(delta)])
    assert out[outcome] == 1


def test_splits_cover_state_horizon_and_direction_over_counted_rows():
    rows = [row(0.5, usd=50.0, state="PARTIAL", horizon="4w", direction="bearish"),
            row(-0.2, usd=-20.0, state="ACTIVE", horizon="2w"),
            row(-0.1, usd=None, state="ACTIVE", horizon="2w"),
            row(9.9, state="ACTIVE", bulk=True)]
    splits = of.summarise(rows)["splits"]
    assert splits["state_at_close"] == {
        "ACTIVE": {"n": 2, "sum_delta_r": -0.3, "sum_delta_usd": -20.0},
        "PARTIAL": {"n": 1, "sum_delta_r": 0.5, "sum_delta_usd": 50.0}}
    assert set(splits["horizon"]) == {"2w", "4w"}
    assert splits["direction"]["bearish"]["n"] == 1
    assert splits["direction"]["bullish"]["n"] == 2
```

- [ ] **Step 2: Write the failing verdict and report test**

Create `$WT/tests/analytics/test_override_verdict.py`:

```python
"""v173 §4: the frozen verdict rule, the stored record and its jsonl mirror,
the payload (never evaluates) and build_report."""
import json
from datetime import date, timedelta

import pytest

from swingbot import config
from swingbot.core.analytics import override_fidelity as of
from swingbot.core.analytics import override_verdict as ov
from swingbot.core.backtesting.instrument import stats
from tests.analytics.test_override_fidelity_replay import LAST_DAY, STOP_BAR, frame, plan
from tests.analytics.test_override_summary import row
from tests.backtesting.test_pullback_dryup_witness import pin_code_defaults

W0 = date(2026, 8, 3)
RECORDED_ON = date(2027, 3, 1)
FLAGS = {"stall_exit_enabled": False, "runner_structure_exit": "off"}
CONDITION_KEYS = {"n", "weeks", "open_n", "excluded_share", "evaluable", "waiting_on"}
EVAL_KEYS = {"state", "n", "weeks", "mean_delta_r", "mean_delta_r_gross", "ci",
             "sum_delta_r", "sum_delta_usd", "bar_close_n", "excluded_share"}
RECORD_KEYS = {"ledger_id", "verdict", "recorded_on", "n", "weeks", "mean_delta_r",
               "mean_delta_r_gross", "ci", "sum_delta_r", "sum_delta_usd", "bar_close_n",
               "excluded_share", "engine_flags", "rows"}
VERDICT_KEYS = {"state", "n", "needed", "weeks", "week_floor", "open_n", "excluded_share",
                "evaluable", "waiting_on", "recorded", "recorded_on", "mean_delta_r",
                "mean_delta_r_gross", "ci", "sum_delta_r", "sum_delta_usd", "bar_close_n"}
ROW_KEYS = {"plan_id", "ticker", "horizon", "direction", "state_at_close", "close_date",
            "bulk", "approx", "price_source", "status", "actual_r", "engine_r", "delta_r",
            "delta_r_gross", "actual_usd", "engine_usd", "delta_usd", "engine_exit_reason",
            "outcome", "source"}


@pytest.fixture(autouse=True)
def _pinned(monkeypatch):
    pin_code_defaults(monkeypatch)
    monkeypatch.setattr(config, "STALL_EXIT_ENABLED", False)
    monkeypatch.setattr(config, "RUNNER_STRUCTURE_EXIT", "off")
    monkeypatch.setattr(config, "ADAPTIVE_RUNNER_TRAIL_ENABLED", False)


def spread(n, weeks, delta=0.3, **kw):
    """n counted rows over `weeks` distinct ISO weeks; `delta` may be a
    function of the week number."""
    return [row(delta(i % weeks) if callable(delta) else delta,
                W0 + timedelta(weeks=i % weeks), plan_id=f"p{i}", **kw) for i in range(n)]


def cost_rows(**kw):
    return spread(30, 10, lambda w: -0.5 + 0.02 * w, **kw)


def cost_record():
    rows = cost_rows(usd=-10.0)
    return ov.verdict_record(ov.evaluate_verdict(rows), rows, FLAGS, recorded_on=RECORDED_ON)


def _no_bootstrap(*_a, **_k):
    raise AssertionError("the bootstrap must not run here")


# -- constants and ledger vocabulary ---------------------------------------------

def test_the_rule_constants_are_the_spec_values():
    assert (of.VERDICT_FLOOR, of.WEEK_FLOOR, of.EXCLUDED_CAP, of.DEAD_BAND) == (30, 10, 0.20, 0.05)
    assert of.LEDGER_ID == "v173-override-fidelity"
    assert ov.RESULTS_RECORD == "docs/superpowers/results/v173-override-fidelity.md"
    for gone in ("SPEC_PATH", "ledger_row", "recorded_verdict"):
        assert not hasattr(ov, gone)


def test_the_ledger_accepts_the_three_outcomes_and_never_waiting():
    assert stats.VERDICTS[-3:] == ("COST", "SAVED", "INCONCLUSIVE")
    assert ov.WAITING not in stats.VERDICTS


# -- conditions: every floor, and which ones fail ------------------------------------

@pytest.mark.parametrize("rows, waiting_on", [
    pytest.param(spread(29, 10), ["count"], id="29-rows"),
    pytest.param(spread(30, 9), ["weeks"], id="9-weeks"),
    pytest.param(spread(30, 10) + [row(status="open")], ["open"], id="one-open"),
    pytest.param(spread(30, 10) + [row(status="ambiguous", plan_id=f"x{i}") for i in range(8)],
                 ["excluded"], id="over-the-cap"),
    pytest.param(spread(29, 9) + [row(status="open")]
                 + [row(status="stale", plan_id=f"x{i}") for i in range(8)],
                 ["count", "weeks", "open", "excluded"], id="all-four-in-order"),
    pytest.param(spread(30, 10), [], id="evaluable"),
])
def test_conditions_name_every_failing_floor_in_order(rows, waiting_on):
    out = ov.conditions(rows)
    assert set(out) == CONDITION_KEYS
    assert out["waiting_on"] == waiting_on
    assert out["evaluable"] is (waiting_on == [])


def test_exclusions_above_20_percent_wait_and_exactly_20_percent_does_not():
    over = spread(30, 10) + [row(status="ambiguous", plan_id=f"x{i}") for i in range(8)]
    assert ov.conditions(over)["excluded_share"] == pytest.approx(8 / 38)
    at_cap = spread(40, 10) + [row(status="stale", plan_id=f"x{i}") for i in range(10)]
    assert ov.conditions(at_cap)["excluded_share"] == 0.2
    assert ov.conditions(at_cap)["evaluable"] is True


def test_unstamped_rows_are_eligible_and_count_against_the_cap():
    rows = spread(30, 10) + [row(status="unstamped", price_source="none", plan_id=f"u{i}")
                             for i in range(8)]
    out = ov.conditions(rows)
    assert (out["n"], out["waiting_on"]) == (30, ["excluded"])
    assert len(ov.eligible(rows)) == 38


def test_open_bulk_or_approx_rows_do_not_hold_it():
    rows = spread(30, 10) + [row(status="open", bulk=True), row(status="open", approx=True)]
    assert ov.conditions(rows)["evaluable"] is True


def test_bulk_and_approx_rows_never_count_toward_n():
    rows = spread(29, 10) + [row(bulk=True)] * 5 + [row(approx=True)] * 5
    assert ov.conditions(rows)["n"] == 29
    assert [r.plan_id for r in ov.counted(rows)] == [f"p{i}" for i in range(29)]
    assert len(ov.eligible(rows)) == 29


# -- one evaluation ----------------------------------------------------------------

def test_evaluate_refuses_rows_that_are_not_evaluable():
    with pytest.raises(ValueError, match="count"):
        ov.evaluate_verdict(spread(29, 10))


@pytest.mark.parametrize("delta, state", [
    (lambda w: -0.5 + 0.02 * w, "COST"),
    (lambda w: 0.5 - 0.02 * w, "SAVED"),
    (lambda w: 0.6 if w % 2 == 0 else -0.6, "INCONCLUSIVE"),
])
def test_seeded_delta_sets_give_each_outcome(delta, state):
    rows = spread(30, 10, delta)
    out = ov.evaluate_verdict(rows)
    assert set(out) == EVAL_KEYS
    assert (out["state"], out["n"], out["weeks"]) == (state, 30, 10)
    lo, hi = out["ci"]
    assert lo <= out["mean_delta_r"] <= hi
    assert ov.evaluate_verdict(rows) == out          # seeded: the same draw every time


def test_the_evaluation_carries_the_gross_mean_the_sums_and_bar_close_n():
    rows = cost_rows(usd=-10.0)
    for i in (0, 1, 2):
        rows[i] = row(rows[i].delta_r, rows[i].close_date, usd=-10.0,
                      price_source="bar_close", plan_id=rows[i].plan_id)
    rows += [row(-0.4, approx=True, price_source="bar_close")]      # shown, never counted
    out = ov.evaluate_verdict(rows)
    assert out["mean_delta_r"] == pytest.approx(-0.41, abs=1e-9)    # -0.5 + 0.02 x 4.5
    assert out["mean_delta_r_gross"] == pytest.approx(-0.40, abs=1e-9)
    assert out["sum_delta_r"] == pytest.approx(-12.3, abs=1e-9)
    assert out["sum_delta_usd"] == pytest.approx(-300.0, abs=1e-9)
    assert out["bar_close_n"] == 3
    assert out["excluded_share"] == 0.0


def test_no_dollars_on_any_counted_row_gives_no_dollar_sum():
    assert ov.evaluate_verdict(cost_rows())["sum_delta_usd"] is None


def test_dict_rows_evaluate_like_override_rows():
    rows = cost_rows()
    assert ov.evaluate_verdict([r.to_dict() for r in rows]) == ov.evaluate_verdict(rows)


# -- the stored record and its jsonl mirror ------------------------------------------

def test_the_record_has_the_stored_shape():
    rows = cost_rows(usd=-10.0) + [row(bulk=True), row(status="stale", plan_id="s")]
    verdict = ov.evaluate_verdict(rows)
    record = ov.verdict_record(verdict, rows, FLAGS, recorded_on=RECORDED_ON)
    assert set(record) == RECORD_KEYS
    assert (record["ledger_id"], record["verdict"], record["recorded_on"]) == (
        "v173-override-fidelity", "COST", "2027-03-01")
    for key in ("n", "weeks", "mean_delta_r", "mean_delta_r_gross", "ci", "sum_delta_r",
                "sum_delta_usd", "bar_close_n", "excluded_share"):
        assert record[key] == verdict[key]
    assert record["engine_flags"] == FLAGS
    assert [r["plan_id"] for r in record["rows"]] == [f"p{i}" for i in range(30)]
    assert all(set(r) == ROW_KEYS for r in record["rows"])
    assert json.loads(json.dumps(record)) == record              # JSONB-ready


@pytest.mark.parametrize("verdict", [{"state": "WAITING"}, {"state": "OPEN"}, {}])
def test_only_an_evaluated_outcome_is_recorded(verdict):
    with pytest.raises(ValueError):
        ov.verdict_record(verdict, [], FLAGS, recorded_on=RECORDED_ON)


def test_the_mirror_row_is_a_valid_ledger_line(tmp_path):
    record = cost_record()
    entry = ov.mirror_ledger_row(record)
    stats.validate_ledger_row(entry)
    assert set(entry) == set(stats.LEDGER_FIELDS)
    assert (entry["id"], entry["date"], entry["instrument"], entry["verdict"]) == (
        "v173-override-fidelity", "2027-03-01", "v2", "COST")
    assert (entry["n"], entry["exp_r"], entry["p"], entry["record"]) == (
        30, record["mean_delta_r"], None, ov.RESULTS_RECORD)
    lo, hi = record["ci"]
    assert entry["hypothesis"] == ("Manual overrides vs the v2 engine: mean delta R, "
                                   f"week-cluster bootstrap 95% CI [{lo:.3f}, {hi:.3f}]")
    path = tmp_path / "ledger.jsonl"
    stats.append_ledger_row(entry, path=path)
    assert stats.load_ledger(path) == [entry]
    with pytest.raises(ValueError):
        stats.append_ledger_row(entry, path=path)      # one line per id


# -- verdict_payload: never evaluates -------------------------------------------------

def test_a_recorded_verdict_wins_and_the_live_fields_stay_live(monkeypatch):
    record = cost_record()
    monkeypatch.setattr(stats, "week_cluster_bootstrap", _no_bootstrap)
    live = spread(40, 12, 0.5) + [row(status="open", plan_id="o")]   # live rows now look SAVED
    shown = ov.verdict_payload(live, record)
    assert set(shown) == VERDICT_KEYS
    assert (shown["state"], shown["recorded"], shown["recorded_on"]) == ("COST", True, "2027-03-01")
    for key in ("n", "weeks", "mean_delta_r", "mean_delta_r_gross", "ci", "sum_delta_r",
                "sum_delta_usd", "bar_close_n"):
        assert shown[key] == record[key]
    assert (shown["open_n"], shown["evaluable"], shown["waiting_on"]) == (1, False, ["open"])
    assert shown["excluded_share"] == 0.0
    assert (shown["needed"], shown["week_floor"]) == (30, 10)


def test_without_a_record_the_payload_waits_even_when_evaluable(monkeypatch):
    monkeypatch.setattr(stats, "week_cluster_bootstrap", _no_bootstrap)
    rows = spread(30, 10, 0.5, price_source="bar_close")
    out = ov.verdict_payload(rows, None)
    assert set(out) == VERDICT_KEYS
    assert (out["state"], out["evaluable"], out["waiting_on"], out["recorded"]) == (
        "WAITING", True, [], False)
    assert all(out[k] is None for k in ("recorded_on", "mean_delta_r", "mean_delta_r_gross",
                                        "ci", "sum_delta_r", "sum_delta_usd"))
    assert (out["n"], out["weeks"], out["bar_close_n"]) == (30, 10, 30)


def test_waiting_with_the_count_met_lists_what_it_waits_on(monkeypatch):
    monkeypatch.setattr(stats, "week_cluster_bootstrap", _no_bootstrap)
    out = ov.verdict_payload(spread(30, 9), None)
    assert (out["state"], out["n"], out["evaluable"], out["waiting_on"]) == (
        "WAITING", 30, False, ["weeks"])


# -- build_report ------------------------------------------------------------------

def _book():
    return [plan(plan_id="a", ticker="AAA"),
            plan(plan_id="b", ticker="BBB", reason="manual_bulk",
                 close_at="2026-10-08T18:00:00+00:00"),
            plan(plan_id="c", ticker="AAA", reason="tp1_runner_trail"),   # not an override
            plan(plan_id="d", ticker="BAD")]


def _bars_fn(calls):
    def bars_fn(ticker):
        calls.append(ticker)
        if ticker == "BAD":
            raise OSError("corrupt cache file")
        return frame({19: STOP_BAR})
    return bars_fn


def test_report_payload_shape(monkeypatch):
    monkeypatch.setattr(stats, "week_cluster_bootstrap", _no_bootstrap)
    calls = []
    out = ov.build_report(_book(), {"a": {"id": "t", "shares": 10}}, _bars_fn(calls),
                          LAST_DAY, None, "$")
    assert set(out) == {"rows", "summary", "verdict", "engine_flags", "asof", "currency_symbol"}
    assert (out["asof"], out["currency_symbol"]) == ("2026-10-19", "$")
    assert out["engine_flags"] == FLAGS == ov.engine_flags()
    assert sorted(calls) == ["AAA", "BAD", "BBB"]               # once per ticker
    assert [r["plan_id"] for r in out["rows"]] == ["b", "d", "a"]   # newest close first
    assert set(of.ROW_FIELDS) == ROW_KEYS                       # V173-7's row contract
    assert all(set(r) == ROW_KEYS for r in out["rows"])
    by_id = {r["plan_id"]: r for r in out["rows"]}
    assert by_id["d"]["status"] == "unreplayable"
    assert by_id["b"]["bulk"] is True
    assert by_id["a"]["delta_usd"] is not None and by_id["b"]["delta_usd"] is None
    assert by_id["a"]["delta_r_gross"] is not None
    assert out["summary"]["bulk_dates"] == {"2026-10-08": 1}
    assert set(out["verdict"]) == VERDICT_KEYS
    assert out["verdict"]["state"] == "WAITING"


def test_report_shows_the_stored_record(monkeypatch):
    record = cost_record()
    monkeypatch.setattr(stats, "week_cluster_bootstrap", _no_bootstrap)
    out = ov.build_report(_book(), {}, _bars_fn([]), LAST_DAY, record, "$")
    assert (out["verdict"]["state"], out["verdict"]["recorded_on"]) == ("COST", "2027-03-01")
    assert out["verdict"]["n"] == 30                     # the record's, not the live 1


def test_report_with_no_overrides_is_empty_not_an_error():
    out = ov.build_report([plan(reason="tp1_runner_trail")], {}, lambda t: None, LAST_DAY,
                          None, "$")
    assert out["rows"] == []
    assert out["summary"]["counted_n"] == 0
    assert out["verdict"]["state"] == "WAITING"
```

Notes: `_book()`'s plans `a` and `d` close on 2026-10-07 and `b` on 2026-10-08, so the order is `b` first, then `d` before `a` (same date, `plan_id` descending). In the "all four in order" case 29 counted rows sit in 9 weeks, and 8 stale rows out of 38 eligible (29 + 1 open + 8) is 21%.

- [ ] **Step 3: Run both to verify they fail**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/analytics/test_override_summary.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/analytics/test_override_verdict.py
```

Expected: the first FAILS with `AttributeError: ... has no attribute 'summarise'`. The second fails at collection with `ModuleNotFoundError: No module named 'swingbot.core.analytics.override_verdict'`.

- [ ] **Step 4: Add the three ledger verdicts**

In `$WT/swingbot/core/backtesting/instrument/stats.py`, replace the `VERDICTS` block (the comment lines above it included):

```python
#: v140 appends the idea screen's three verdicts and its instrument; v173
#: appends the override-fidelity outcomes. WAITING is never written: a
#: verdict that is not yet evaluable has no row. Existing rows are untouched
#: (a ledger row is never edited).
VERDICTS = ("PASS", "FAIL", "NO-LIFT", "UNMEASURABLE", "WITHDRAWN", "OPEN",
            "SCREEN-PASS", "SCREEN-FAIL", "SCREEN-UNDERPOWERED",
            "COST", "SAVED", "INCONCLUSIVE")
```

and the pinned tuple in `$WT/tests/backtesting/test_instrument_stats_ledger.py` (`test_fields_and_vocabularies_are_the_plan_set`, lines 20-22):

```python
    assert stats.VERDICTS == ("PASS", "FAIL", "NO-LIFT", "UNMEASURABLE",
                              "WITHDRAWN", "OPEN", "SCREEN-PASS", "SCREEN-FAIL",
                              "SCREEN-UNDERPOWERED", "COST", "SAVED", "INCONCLUSIVE")
```

The research API (`research.py:78`) and the ledger CLI (`preregistration_ledger.py:46`) echo `stats.VERDICTS` and pick the three up unchanged; the research page's tone map is V173-13's.

- [ ] **Step 5: Implement `summarise`**

At the top of `$WT/swingbot/core/analytics/override_fidelity.py` add `from collections import Counter` if missing. Append at the end of the module:

```python
# --------------------------------------------------------------------------
# V173-10: descriptive totals (spec §3). Counted rows are individual,
# not approx, and resolved; bulk and approx rows are shown, never summed.
# --------------------------------------------------------------------------

_SPLIT_KEYS = ("state_at_close", "horizon", "direction")


def _sum_r(rows, field: str = "delta_r") -> float:
    return round(sum(getattr(r, field) for r in rows if getattr(r, field) is not None), 3)


def _sum_usd(rows) -> float:
    return round(sum(r.delta_usd for r in rows if r.delta_usd is not None), 2)


def _split(rows, key: str) -> dict:
    groups: dict = {}
    for r in rows:
        groups.setdefault(getattr(r, key), []).append(r)
    return {value: {"n": len(group), "sum_delta_r": _sum_r(group),
                    "sum_delta_usd": _sum_usd(group)}
            for value, group in sorted(groups.items())}


def _bulk_dates(rows) -> dict[str, int]:
    tally = Counter(r.close_date.isoformat() if r.close_date else "unknown"
                    for r in rows if r.bulk)
    return dict(sorted(tally.items()))


def summarise(rows: list[OverrideRow]) -> dict:
    """N by status, bulk/approx counts, the ΔR sums (net and before costs),
    Σ$ and helped/hurt/neutral over counted rows, and the splits."""
    rows = list(rows)
    eligible = [r for r in rows if not r.bulk and not r.approx]
    counted = [r for r in eligible if r.status == "resolved"]
    by_status = Counter(r.status for r in eligible)
    outcomes = Counter(r.outcome for r in counted)
    return {
        "n_by_status": {status: by_status[status] for status in STATUSES},
        "bulk_n": sum(1 for r in rows if r.bulk),
        "bulk_dates": _bulk_dates(rows),
        "approx_n": sum(1 for r in rows if r.approx and not r.bulk),
        "counted_n": len(counted),
        "sum_delta_r": _sum_r(counted),
        "sum_delta_r_gross": _sum_r(counted, "delta_r_gross"),
        "sum_delta_usd": _sum_usd(counted),
        "usd_missing_n": sum(1 for r in counted if r.delta_usd is None),
        "helped": outcomes["helped"], "hurt": outcomes["hurt"],
        "neutral": outcomes["neutral"],
        "splits": {key: _split(counted, key) for key in _SPLIT_KEYS},
    }
```

- [ ] **Step 6: Implement `override_verdict.py`**

Create `$WT/swingbot/core/analytics/override_verdict.py`. Module docstring (verbatim): 

```python
"""v173 §4: the frozen verdict on manual overrides, its stored record, the
jsonl mirror line, and the report payload.

The rule is frozen in the spec and evaluated once. Population: individual
(not bulk), not approx, resolved rows. It becomes evaluable when there are
>= VERDICT_FLOOR of them over >= WEEK_FLOOR ISO weeks, no eligible row is
still open, and excluded statuses are <= EXCLUDED_CAP of the eligible rows.
The bot's daily job (override_io.run_daily_check) is the only caller of
evaluate_verdict; it stores verdict_record() in preregistration_verdicts,
whose primary key makes the write happen once. Every reader shows that
record and never recomputes it: watching a live interval until it crosses
zero inflates false positives.

Pure: no store, no network, no file reads. build_report takes its inputs
from the caller and never evaluates.
"""
```

Module contents, in this order (signatures and the decisions they carry; bodies follow the Shapes above):

```python
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Callable

import numpy as np
import pandas as pd

from swingbot import config
from swingbot.core.analytics import override_fidelity as ofi
from swingbot.core.backtesting.instrument import stats

log = logging.getLogger(__name__)

RESULTS_RECORD = "docs/superpowers/results/v173-override-fidelity.md"   # created by V173-11
WAITING = "WAITING"
COST, SAVED, INCONCLUSIVE = "COST", "SAVED", "INCONCLUSIVE"
_EVALUATED = (COST, SAVED, INCONCLUSIVE)
_WAITING_ITEMS = ("count", "weeks", "open", "excluded")
_HYPOTHESIS = ("Manual overrides vs the v2 engine: mean delta R, "
               "week-cluster bootstrap 95% CI [{lo:.3f}, {hi:.3f}]")
_RECORDED_FIELDS = ("n", "weeks", "mean_delta_r", "mean_delta_r_gross", "ci",
                    "sum_delta_r", "sum_delta_usd", "bar_close_n")


@dataclass(frozen=True)
class _View:
    """The fields the rule reads, from an OverrideRow or its to_dict() form.
    `entry_date` is the name stats.group_by_week reads."""
    bulk: bool
    approx: bool
    status: str
    price_source: str
    delta_r: float | None
    delta_r_gross: float | None
    delta_usd: float | None
    entry_date: date | None


def _field(row, name: str):
    return row.get(name) if isinstance(row, dict) else getattr(row, name)


def _day(value) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _view(row) -> _View:
    return _View(bulk=bool(_field(row, "bulk")), approx=bool(_field(row, "approx")),
                 status=_field(row, "status"), price_source=_field(row, "price_source"),
                 delta_r=_field(row, "delta_r"), delta_r_gross=_field(row, "delta_r_gross"),
                 delta_usd=_field(row, "delta_usd"),
                 entry_date=_day(_field(row, "close_date")))


def _as_dict(row) -> dict:
    return dict(row) if isinstance(row, dict) else row.to_dict()
```

Then:

- `_is_eligible(view) -> bool` (`not bulk and not approx`), `_is_counted(view) -> bool` (eligible and `status == "resolved"`); `eligible(rows) -> list` and `counted(rows) -> list` return the given rows (not views) that pass, in order.
- `conditions(rows) -> dict`: views; `elig`; `population` (resolved among `elig`); `weeks = len({stats.iso_week_key(v.entry_date) for v in population})`; `open_n` (eligible `open`); `share = excluded / len(elig) if elig else 0.0` over `ofi.EXCLUDED_STATUSES`; a dict of the four checks keyed by `_WAITING_ITEMS` (`count`: `n >= VERDICT_FLOOR`, `weeks`: `>= WEEK_FLOOR`, `open`: `open_n == 0`, `excluded`: `share <= EXCLUDED_CAP`); `waiting_on = [k for k in _WAITING_ITEMS if not checks[k]]`; `evaluable = not waiting_on`.
- `_mean_delta(baseline, _component) -> float | None`: `float(np.mean([v.delta_r for v in baseline])) if baseline else None` (the bootstrap statistic; `None` drops an empty draw).
- `_state_for(lo, hi) -> str`: `hi < 0` → `COST`, `lo > 0` → `SAVED`, else `INCONCLUSIVE`.
- `_sums(population) -> dict`: `mean_delta_r`, `mean_delta_r_gross` (`None` if no gross values), `sum_delta_r`, `sum_delta_usd` (`None` if no counted row has dollars), rounded per Shapes.
- `_bar_close_n(views) -> int`: counted views with `price_source == "bar_close"`.
- `evaluate_verdict(rows) -> dict`:

```python
def evaluate_verdict(rows) -> dict:
    """The one evaluation (only override_io.run_daily_check calls it): the
    week-clustered bootstrap of mean ΔR, seeded, and its 95% interval.
    Raises ValueError unless conditions() holds."""
    cond = conditions(rows)
    if not cond["evaluable"]:
        raise ValueError("override verdict not evaluable; waiting on "
                         + ", ".join(cond["waiting_on"]))
    population = [v for v in map(_view, rows) if _is_counted(v)]
    draws = stats.week_cluster_bootstrap(population, (), _mean_delta,
                                         n_resamples=stats.WEEK_BOOTSTRAP_RESAMPLES,
                                         seed=stats.WEEK_BOOTSTRAP_SEED)
    lo, hi = (float(x) for x in np.percentile(draws, [2.5, 97.5]))
    return {"state": _state_for(lo, hi), "n": cond["n"], "weeks": cond["weeks"],
            **_sums(population), "ci": [round(lo, 3), round(hi, 3)],
            "bar_close_n": _bar_close_n(population),
            "excluded_share": round(cond["excluded_share"], 4)}
```

- `verdict_record(verdict, rows, engine_flags, *, recorded_on) -> dict`: `ValueError` unless `verdict.get("state") in _EVALUATED`; returns `{"ledger_id": ofi.LEDGER_ID, "verdict": verdict["state"], "recorded_on": recorded_on.isoformat(), **{k: verdict[k] for k in (*_RECORDED_FIELDS, "excluded_share")}, "engine_flags": dict(engine_flags), "rows": [_as_dict(r) for r in counted(rows)]}` with `ci` copied as a new list.
- `mirror_ledger_row(record) -> dict`: `lo, hi = record["ci"]`; `{"id": record["ledger_id"], "date": record["recorded_on"], "hypothesis": _HYPOTHESIS.format(lo=lo, hi=hi), "instrument": "v2", "n": int(record["n"]), "exp_r": float(record["mean_delta_r"]), "p": None, "verdict": record["verdict"], "record": RESULTS_RECORD}`; calls `stats.validate_ledger_row(entry)` before returning it. Docstring: "The jsonl line for the standing mirror procedure (results doc, V173-11); no bot code writes the ledger file."
- `verdict_payload(rows, recorded) -> dict`:

```python
def verdict_payload(rows, recorded: dict | None) -> dict:
    """What the API, the script and the report show. Never evaluates: the
    state is the stored record's verdict, or WAITING; the floors stay live."""
    cond = conditions(rows)
    live = {"needed": ofi.VERDICT_FLOOR, "week_floor": ofi.WEEK_FLOOR,
            "open_n": cond["open_n"], "excluded_share": round(cond["excluded_share"], 4),
            "evaluable": cond["evaluable"], "waiting_on": list(cond["waiting_on"])}
    if recorded is not None:
        return {"state": recorded["verdict"], **live, "recorded": True,
                "recorded_on": recorded["recorded_on"],
                **{key: recorded[key] for key in _RECORDED_FIELDS}}
    return {"state": WAITING, **live, "recorded": False, "recorded_on": None,
            "n": cond["n"], "weeks": cond["weeks"], "mean_delta_r": None,
            "mean_delta_r_gross": None, "ci": None, "sum_delta_r": None,
            "sum_delta_usd": None, "bar_close_n": _bar_close_n(map(_view, rows))}
```

- `_bars_for(bars_fn, ticker, cache)`: one read per ticker; any exception logs at WARNING and caches `None` (body below).
- `engine_flags() -> dict`: `{"stall_exit_enabled": bool(config.STALL_EXIT_ENABLED), "runner_structure_exit": str(config.RUNNER_STRUCTURE_EXIT)}` (public: V173-26 stores it in the record).
- `build_report`:

```python
def build_report(plans: list, trades_by_plan: dict[str, dict],
                 bars_fn: Callable[[str], pd.DataFrame | None], asof: date,
                 recorded: dict | None, currency_symbol: str) -> dict:
    """The report payload (index § Report payload). Replays every manual
    close, newest first; the verdict is the stored record's or WAITING."""
    cache: dict = {}
    trades = trades_by_plan or {}
    rows = [ofi.replay_override(p, _bars_for(bars_fn, p.ticker, cache), asof,
                                trades.get(p.plan_id))
            for p in plans if ofi.is_override(p)]
    rows.sort(key=lambda r: (r.close_date or date.min, r.plan_id), reverse=True)
    return {"rows": [r.to_dict() for r in rows], "summary": ofi.summarise(rows),
            "verdict": verdict_payload(rows, recorded), "engine_flags": engine_flags(),
            "asof": asof.isoformat(), "currency_symbol": currency_symbol}
```

`_bars_for`'s body is the one-line-per-branch cache from the brief's runner-path idiom:

```python
def _bars_for(bars_fn: Callable[[str], pd.DataFrame | None], ticker: str,
              cache: dict) -> pd.DataFrame | None:
    """One cache read per ticker; an unreadable file is an unreplayable row."""
    if ticker not in cache:
        try:
            cache[ticker] = bars_fn(ticker)
        except Exception as exc:   # noqa: BLE001 -- one bad file never fails the report
            log.warning("override_verdict: bars for %s unreadable: %s", ticker, exc)
            cache[ticker] = None
    return cache[ticker]
```

- [ ] **Step 7: Run the new tests and the ledger tests**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/analytics/test_override_summary.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/analytics/test_override_verdict.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/backtesting/test_instrument_stats_ledger.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/admin/test_api_v1_research.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/analytics/test_override_fidelity_replay.py
```

Expected: all PASS, `0 failed`, `0 xfailed`. Each seeded evaluation draws 10,000 resamples over 10 weeks. If `test_override_verdict.py` takes more than about 20 s, report it; do not lower the resample count (it is the pre-registered `stats.WEEK_BOOTSTRAP_RESAMPLES`).

If the INCONCLUSIVE case comes out COST or SAVED, the bootstrap is not pooling weeks: check that `_View.entry_date` carries the row's `close_date`. Do not change the seeded deltas. `test_api_v1_research.py` asserts `body["verdicts"] == list(stats.VERDICTS)` (line 71), so it passes unchanged.

- [ ] **Step 8: Complexity**

```bash
python -m radon cc -s -n C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/swingbot/core/analytics/override_fidelity.py E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/swingbot/core/analytics/override_verdict.py E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/swingbot/core/backtesting/instrument/stats.py
```

Expected: no output (every function below grade C). If `summarise`, `conditions` or `_sums` grades C, move one comprehension into a named helper: the result stays identical and the tests above stay green unchanged.

- [ ] **Step 9: Commit on the branch (two scoped commits)**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides add swingbot/core/backtesting/instrument/stats.py tests/backtesting/test_instrument_stats_ledger.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides commit -m "feat(v173): ledger verdicts COST, SAVED, INCONCLUSIVE"
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides add swingbot/core/analytics/override_fidelity.py swingbot/core/analytics/override_verdict.py tests/analytics/test_override_summary.py tests/analytics/test_override_verdict.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides commit -m "feat(v173): override summary, the frozen verdict rule, its stored record and mirror line, build_report"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

The last command checks the main tree stayed clean of branch edits.
