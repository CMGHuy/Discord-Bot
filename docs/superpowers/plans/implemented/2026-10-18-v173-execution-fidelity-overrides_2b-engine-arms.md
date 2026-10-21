# v173 Execution fidelity, part 2b: the engine arm and the cost-basis arms

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Pull one task with `grep -n "^### Task V173-8:" -A 600 <this file>`; never read the file whole.

**Spec:** [`docs/superpowers/specs/2026-10-18-v173-execution-fidelity-overrides-design.md`](../specs/2026-10-18-v173-execution-fidelity-overrides-design.md) §3 (replay core: never resume, one cost basis, the override session) and `## Plan panel review` (indicators from the real frame, truncation test, before-costs figure)
**Bump:** bot minor; ui minor (applied once, in V173-17)
**Edge:** none (integrity)
**Index:** [`2026-10-18-v173-execution-fidelity-overrides_0-index.md`](2026-10-18-v173-execution-fidelity-overrides_0-index.md) carries the Goal, `## Global Constraints`, `## Parallelisation`, `## Where to work` (`$WT`, `$R`), the task ledger, `## Handoff` and `## Revision 2026-10-19`. Every task below implicitly includes those Global Constraints.

Tasks: V173-8 (moved here from part 2 on 2026-10-19 and rewritten). It runs after V173-7 (same module) and needs V173-6 (`fill_bar_exit`, `tp1_index`) and V173-21 (`walk_v2(..., indicator_df=)`), all in part 2. Part 3 (V173-9, V173-22) builds `replay_override` on the names created here.

`$WT = E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides`. Every path below is under `$WT`; commands spell it out in full because shell variables do not persist between Bash calls.

**Tests never touch a database** (Global Constraints): synthetic bars from `tests.helpers.make_ohlcv`, `TradePlanV2` objects built in the test, no store.

# Phase 2: Replay core (continued)

### Task V173-8: Engine path from the fill, `leg_kind`, both arms through `costs.book`, dollar risk

**Model:** opus — exit-engine replay and cost basis feeding a frozen verdict

**Files:**
- Modify: `swingbot/core/analytics/override_fidelity.py` (created by V173-7: extend the import block, append the engine and arm functions at the end)
- Create: `tests/analytics/test_override_fidelity_arms.py`

**Interfaces:**
- Consumes:
  - V173-6: `exit_sim_v2.fill_bar_exit(df, j, fill, plan, instrument) -> ExitResult | None`; `ExitResult.tp1_index` (a plain class attribute: lost by `dataclasses.replace()`/`asdict()`).
  - V173-21: `walk_v2(df, entry_index, entry_price, plan, max_holding_days, instrument, *, scale_out, indicator_df=None)`; `ValueError` when `indicator_df`'s index or length differs from `df`'s.
  - V173-7: `override_fidelity` module and its constants; test helper `tests.analytics.test_override_fidelity_sessions.override_plan`.
  - Existing: `exit_sim._hold_cap_bars` (`exit_sim.py:613`), `strategy_types.HORIZONS`, `contract.resolve` (`contract.py:130`), `contract.CostModel`, `costs.book` (`costs.py:41`), `time_exit.TIME_EXIT_REASON` (`"time_exit"`).
- Produces (in `override_fidelity.py`; V173-9, V173-22 and V173-23 build `replay_override` from these):
  - `INSTRUMENT = contract.resolve("v2")`.
  - `GROSS_COST_MODEL = CostModel(commission_per_share=0.0, slippage_bps=0.0, stop_slippage_bps=0.0)`: the "before costs" basis. Descriptive only: it feeds `delta_r_gross` and never the verdict decision.
  - `hold_cap_bars(plan) -> int` = `exit_sim._hold_cap_bars(plan, HORIZONS[plan.horizon_key]["max_holding_days"])`, the cap `simulate_exit_v2` uses.
  - `engine_frame(df, ov_idx: int) -> pd.DataFrame`: a copy of `df` whose bar `ov_idx` has `High = max(Open, Close)` and `Low = min(Open, Close)`; every other bar and the input frame are unchanged.
  - `engine_path(plan, df, fill_idx: int, *, indicator_df: pd.DataFrame | None = None) -> ExitResult`: `fill_bar_exit(df, fill_idx, plan.entry_price, plan, INSTRUMENT)`, and when that is `None`, `walk_v2(df, fill_idx, plan.entry_price, plan, hold_cap_bars(plan), INSTRUMENT, scale_out=plan.tp1_fraction < 1.0, indicator_df=indicator_df)`. The plan's original `stop_loss` is the stop, as at the fill. V173-9 calls it twice: `engine_path(plan, df, fill_idx)` on the **real** frame (parity, ambiguity) and `engine_path(plan, engine_frame(df, ov_idx), fill_idx, indicator_df=df)` for the **engine arm**, so ATR and structure come from the real bars while the exit checks see the clamped override bar. Its body carries the `tp1_index` guard comment.
  - `leg_kind(reason: str) -> str`: `"target"` for `tp1`, `runner_tp2`; `"close"` for `timeout`, `runner_timeout`, `acceptance_exit`, `stall_exit`, `runner_progress_stall`, `time_exit`; `"stop"` for every other reason (`stop`, `breakeven_stop`, `runner_be`, `runner_trail`, ...). It matches the kind `walk_v2` books each reason with.
  - `live_tp1_leg(plan) -> dict | None`: `{"fraction": plan.tp1_fraction, "exit_price": <legs_realized "tp1" leg's exit_price>, "reason": "tp1", "kind": "target"}`, or `None` when the plan has no realised TP1 leg with a price.
  - `actual_r(plan, exit_price: float, state: str, *, cost_model=None) -> float` and `engine_r(plan, result: ExitResult, state: str, *, cost_model=None) -> float`: each **one** `costs.book(<model>, direction=plan.direction, entry_price=plan.entry_price, stop_loss=plan.stop_loss, legs=[...])` call, per the Global Constraints "One cost basis". `cost_model=None` is the v2 model (net); `cost_model=GROSS_COST_MODEL` is the before-costs figure. Both raise `ValueError` when the entry is at or beyond the stop, when a PARTIAL plan has no `live_tp1_leg`, or (`engine_r`) when the result has no leg left to book. V173-9 maps any `ValueError` here to `unreplayable`.
  - `dollar_risk(plan, trade: dict | None) -> float | None` = `float(trade["shares"]) * abs(plan.entry_price - plan.stop_loss)`; `None` with no trade, no or unparseable `shares`, a missing price, or a non-positive result.
  - `to_usd(r: float | None, risk: float | None) -> float | None` = `round(r * risk, 2)`, `None` if either is `None`.

**What the arms mean.**

- **Actual arm.** The human's exit. On a PARTIAL plan it is the live TP1 leg plus a remainder of `1 - tp1_fraction` at the override price. On an ACTIVE plan it is the whole position at the override price. The manual leg is booked as kind `"stop"`: 10 bps, a market order taken at a moment the engine did not choose.
- **Engine arm.** The replay's legs, each booked with the kind the engine itself gives that reason. On a PARTIAL plan the replay's own `tp1` leg is dropped and the **live** TP1 leg is used, so both arms share one TP1 leg and the delta is decided by the remainder alone. The remaining legs are re-scaled so their fractions sum to the remainder. In the normal case (one runner leg of `1 - tp1_fraction`) the scale is exactly 1.
- **Two frames, one set of indicators.** The engine arm walks `engine_frame(df, ov_idx)`: the override session's high and low are shrunk to its open-close body, because the human acted somewhere inside that session and the engine must not be shown its range as a later path. Shrinking that bar must not also shrink the runner's ATR(14) and structure pivots for every later bar, or one wide override bar would move every later trailing stop. So the engine walk gets `indicator_df=<real frame>` (V173-21): exit checks read the clamped bar, indicators read the real one. A test pins it: on a runner whose override bar has a wide high that touches nothing, the engine arm with real indicators equals the real-frame walk (3.565R); only without them does it drift (3.697R).
- **Cost parity.** Both arms share entry, stop, entry slippage and the TP1 leg. So when the actual exit price equals the engine's exit price on a **stop-kind** engine exit (stop, breakeven, runner trail), `delta_r` is exactly 0. When the engine exit is a target or a close, the same price still differs by the slippage gap (5 bps against the manual leg's 10). That gap is a real cost of exiting by hand, not a bias, and a test pins it so nobody "fixes" it.
- **Before costs.** The same two `costs.book` calls on `GROSS_COST_MODEL` (no slippage, no commission) give `actual_r`/`engine_r` before costs; V173-9 stores their difference as `delta_r_gross`. Gross is never below net for the same legs (costs only subtract), which a test pins on a stop exit.
- **No lookahead, pinned twice.** Bars before the fill: on the single-leg paths (stop, TP1, timeout) no bar before the fill is read. On a runner, the chandelier trail reads ATR(14) and the structure frame, which can reach up to 13 sessions back from the trailing bar. That is past data, exactly as in every backtest, never lookahead, so the pre-fill invariance test is pinned on a single-leg plan (§ Handoff). Bars after the exit: dropping every bar after the engine's exit (`df.iloc[:exit_index + 1]`) leaves `engine_r` and the exit index identical, on a stop, a TP1 and an ATR-priced runner trail, the last one on the clamped frame with real indicators.

- [ ] **Step 1: Write the failing test**

Create `$WT/tests/analytics/test_override_fidelity_arms.py`:

```python
"""v173 §3: the engine path from the live fill and the two cost-basis arms.

Every net figure is booked through the real v2 instrument (resolve("v2"): 5 bps
entry and target/close slippage, 10 bps stop slippage, no commission). With
entry 100 and stop 95 the slipped entry is 100.05 and the risk 5.05, so e.g.
a manual exit at 104 is (104 * 0.999 - 100.05) / 5.05 = 0.762R; before costs
it is (104 - 100) / 5 = 0.8R. Expected numbers were computed with costs.book
and walk_v2 (pin_code_defaults: RUNNER_STRUCTURE_EXIT "off", stall exit off)
before this module existed.
"""
import dataclasses

import pytest

from swingbot.core.analytics import override_fidelity as of
from swingbot.core.backtesting.instrument.contract import resolve
from swingbot.core.planning.exit_sim import ExitResult
from tests.analytics.test_override_fidelity_sessions import override_plan
from tests.backtesting.test_pullback_dryup_witness import pin_code_defaults
from tests.helpers import make_ohlcv

ENTRY = (100.0, 100.5, 99.5, 100.0)
FLAT = (100.0, 100.5, 99.5, 100.0)
TP1_BAR = (105.0, 111.0, 104.0, 110.0)
TP2_BAR = (112.0, 121.0, 111.0, 120.0)
STOP_BAR = (96.0, 96.5, 94.0, 95.0)
#: Bar 18 of `_stop_trail_bars` (rising[15]): the override session in the frame tests.
OV_IDX = 18


@pytest.fixture(autouse=True)
def _pinned(monkeypatch):
    pin_code_defaults(monkeypatch)      # STALL_EXIT_ENABLED, RUNNER_STRUCTURE_EXIT at code defaults


def _active(**kw):
    return override_plan(**kw)


def _partial(tp1_price=110.0, **kw):
    plan = override_plan(partial=True, **kw)
    return dataclasses.replace(plan, legs_realized=[
        {"fraction": 0.5, "exit_price": tp1_price, "r": 2.0, "reason": "tp1"}])


def _trail_bars():
    """TP1 on bar 2, twenty rising bars that ratchet the trail, then a gap down
    that fills at its open (125), whatever the trail level."""
    rising = [(110.0 + i, 111.0 + i, 109.0 + i, 110.5 + i) for i in range(20)]
    return make_ohlcv([ENTRY, FLAT, TP1_BAR, *rising, (125.0, 125.5, 100.0, 101.0)])


def _stop_trail_bars(*, spike=False, tail=0):
    """TP1 on bar 2, twenty rising bars, then bar 23 opens at 129 (above the
    trail) and trades through it: the runner exits AT the trailing stop, so
    its price depends on ATR. `spike` widens bar 18's high to 150 (a range
    that touches neither the trail nor TP2, but lifts ATR for later bars);
    `tail` adds flat bars after the exit."""
    rising = [(110.0 + i, 111.0 + i, 109.0 + i, 110.5 + i) for i in range(20)]
    if spike:
        rising[15] = (125.0, 150.0, 124.0, 125.5)
    after = [(101.0, 102.0, 100.0, 101.0)] * tail
    return make_ohlcv([ENTRY, FLAT, TP1_BAR, *rising, (129.0, 129.5, 100.0, 101.0), *after])


# --- instrument, gross model and hold cap ----------------------------------------

def test_the_replay_books_on_the_v2_instrument():
    assert of.INSTRUMENT is resolve("v2")
    model = of.INSTRUMENT.cost_model
    assert (model.slippage_bps, model.stop_slippage_bps, model.commission_per_share) == (
        5.0, 10.0, 0.0)


def test_the_gross_model_books_no_cost_at_all():
    model = of.GROSS_COST_MODEL
    assert (model.slippage_bps, model.stop_slippage_bps, model.commission_per_share) == (
        0.0, 0.0, 0.0)


def test_hold_cap_bars_is_the_simulators_cap():
    assert of.hold_cap_bars(_active()) == 28                    # HORIZONS["4w"]
    assert of.hold_cap_bars(_active(horizon_key="1w")) == 7
    assert of.hold_cap_bars(_active(hold_cap_bars=10)) == 10    # the plan's own cap wins


# --- engine_frame ----------------------------------------------------------------

def test_engine_frame_clamps_only_the_override_bar_and_leaves_the_input_alone():
    df = make_ohlcv([ENTRY, (101.0, 108.0, 96.0, 103.0), FLAT])
    frame = of.engine_frame(df, 1)
    assert frame.iloc[1][["Open", "High", "Low", "Close"]].tolist() == [101.0, 103.0, 101.0, 103.0]
    assert frame.iloc[0].tolist() == df.iloc[0].tolist()
    assert frame.iloc[2].tolist() == df.iloc[2].tolist()
    assert df.iloc[1][["High", "Low"]].tolist() == [108.0, 96.0]
    assert frame.index.equals(df.index)          # walkable with indicator_df=df


# --- engine_path ----------------------------------------------------------------

def test_engine_path_checks_the_fill_bar_first():
    res = of.engine_path(_active(), make_ohlcv([(100.0, 101.0, 94.0, 96.0), FLAT]), 0)
    assert (res.outcome, res.entry_index, res.exit_index, res.r_total) == ("loss", 0, 0, -1.019)


def test_engine_path_walks_from_the_fill_index():
    res = of.engine_path(_active(), make_ohlcv([FLAT, ENTRY, FLAT, FLAT]), 1)
    assert (res.outcome, res.entry_index, res.exit_index) == ("timeout", 1, 3)
    assert res.legs[0]["reason"] == "timeout"


def test_engine_path_stops_at_the_hold_cap():
    res = of.engine_path(_active(hold_cap_bars=2), make_ohlcv([ENTRY, *[FLAT] * 6]), 0)
    assert (res.outcome, res.exit_index) == ("timeout", 2)


def test_engine_path_scales_out_only_when_the_plan_keeps_a_runner():
    df = make_ohlcv([ENTRY, FLAT, TP1_BAR, TP2_BAR])
    single = of.engine_path(_active(), df, 0)
    runner = of.engine_path(_active(tp1_fraction=0.5, tp2=120.0), df, 0)
    assert [leg["reason"] for leg in single.legs] == ["tp1"]
    assert [leg["reason"] for leg in runner.legs] == ["tp1", "runner_tp2"]
    assert single.tp1_index == runner.tp1_index == 2


def test_tp1_index_is_read_from_the_returned_result_never_a_copy():
    """The guard in engine_path: replace() and asdict() drop the attribute."""
    res = of.engine_path(_active(), make_ohlcv([ENTRY, FLAT, TP1_BAR]), 0)
    assert res.tp1_index == 2
    assert dataclasses.replace(res).tp1_index is None
    assert "tp1_index" not in dataclasses.asdict(res)


def test_bars_before_the_fill_never_change_a_single_leg_engine_r():
    quiet = make_ohlcv([*[(50.0, 51.0, 49.0, 50.0)] * 5, ENTRY, FLAT, TP1_BAR])
    wild = make_ohlcv([*[(80.0, 90.0, 70.0, 85.0)] * 5, ENTRY, FLAT, TP1_BAR])
    a = of.engine_r(_active(), of.engine_path(_active(), quiet, 5), "ACTIVE")
    b = of.engine_r(_active(), of.engine_path(_active(), wild, 5), "ACTIVE")
    assert a == b == 1.959


def test_engine_path_refuses_an_indicator_frame_on_another_index():
    df = make_ohlcv([ENTRY, FLAT, TP1_BAR])
    with pytest.raises(ValueError):
        of.engine_path(_active(), df, 0, indicator_df=df.iloc[:-1])


# --- the engine frame takes its indicators from the real bars ---------------------

def test_clamping_a_wide_override_bar_leaves_the_atr_driven_trail_unchanged():
    plan = _partial(tp2=200.0)
    df = _stop_trail_bars(spike=True)
    real = of.engine_path(plan, df, 0)
    engine = of.engine_path(plan, of.engine_frame(df, OV_IDX), 0, indicator_df=df)
    assert (real.runner_outcome, real.exit_index, real.r_total) == ("runner_trail", 23, 3.565)
    assert (engine.runner_outcome, engine.exit_index, engine.r_total) == (
        "runner_trail", 23, 3.565)
    assert engine.legs == real.legs
    assert of.engine_r(plan, engine, "PARTIAL") == 3.565


def test_without_real_indicators_the_clamped_bar_would_move_the_trail():
    """Why indicator_df matters: the clamped bar's smaller range lowers ATR,
    lifts the trail and books a different runner exit."""
    plan = _partial(tp2=200.0)
    df = _stop_trail_bars(spike=True)
    drifted = of.engine_path(plan, of.engine_frame(df, OV_IDX), 0)
    assert (drifted.runner_outcome, drifted.exit_index, drifted.r_total) == (
        "runner_trail", 23, 3.697)


# --- truncation after the engine exit: no lookahead --------------------------------

@pytest.mark.parametrize("bars", [
    [ENTRY, FLAT, STOP_BAR, FLAT, FLAT],
    [ENTRY, FLAT, TP1_BAR, FLAT, FLAT],
])
def test_dropping_the_bars_after_the_exit_leaves_engine_r_identical(bars):
    plan = _active()
    df = make_ohlcv(bars)
    full = of.engine_path(plan, df, 0)
    cut = of.engine_path(plan, df.iloc[:full.exit_index + 1], 0)
    assert cut.exit_index == full.exit_index == 2
    assert of.engine_r(plan, cut, "ACTIVE") == of.engine_r(plan, full, "ACTIVE")


def test_truncation_on_the_engine_frame_with_real_indicators():
    """The ATR-priced trail on the clamped frame, walked on the full data and
    on the data cut right after its exit: the same exit, the same R."""
    plan = _partial(tp2=200.0)
    df = _stop_trail_bars(tail=4)
    full = of.engine_path(plan, of.engine_frame(df, OV_IDX), 0, indicator_df=df)
    cut_df = df.iloc[:full.exit_index + 1]
    cut = of.engine_path(plan, of.engine_frame(cut_df, OV_IDX), 0, indicator_df=cut_df)
    assert (full.runner_outcome, full.exit_index) == ("runner_trail", 23)
    assert cut.exit_index == full.exit_index and cut.legs == full.legs
    assert of.engine_r(plan, cut, "PARTIAL") == of.engine_r(plan, full, "PARTIAL") == 3.691


# --- leg_kind ---------------------------------------------------------------------

@pytest.mark.parametrize("reason, kind", [
    ("tp1", "target"), ("runner_tp2", "target"),
    ("timeout", "close"), ("runner_timeout", "close"), ("acceptance_exit", "close"),
    ("stall_exit", "close"), ("runner_progress_stall", "close"), ("time_exit", "close"),
    ("stop", "stop"), ("breakeven_stop", "stop"), ("runner_be", "stop"),
    ("runner_trail", "stop"), ("entry_gap_scratch", "stop"),
])
def test_leg_kind_matches_the_engines_booking(reason, kind):
    assert of.leg_kind(reason) == kind


# --- live_tp1_leg -------------------------------------------------------------------

def test_live_tp1_leg_reads_the_realised_tp1_price():
    assert of.live_tp1_leg(_partial(tp1_price=110.4)) == {
        "fraction": 0.5, "exit_price": 110.4, "reason": "tp1", "kind": "target"}


def test_live_tp1_leg_is_none_without_a_priced_tp1_leg():
    assert of.live_tp1_leg(_active()) is None
    plan = dataclasses.replace(_partial(), legs_realized=[{"fraction": 0.5, "reason": "tp1"}])
    assert of.live_tp1_leg(plan) is None


# --- actual_r -----------------------------------------------------------------------

def test_actual_r_active_books_the_whole_position_as_a_stop_kind_exit():
    assert of.actual_r(_active(), 104.0, "ACTIVE") == 0.762


def test_actual_r_partial_books_the_live_tp1_leg_and_the_remainder_together():
    # 0.5 * (110 * 0.9995 - 100.05) / 5.05 + 0.5 * 0.76158 = 1.360
    assert of.actual_r(_partial(), 104.0, "PARTIAL") == 1.36


def test_actual_r_refuses_an_entry_at_the_stop():
    with pytest.raises(ValueError):
        of.actual_r(_active(entry_price=95.0), 96.0, "ACTIVE")


def test_actual_r_refuses_a_partial_plan_without_a_tp1_leg():
    with pytest.raises(ValueError):
        of.actual_r(_active(tp1_fraction=0.5), 104.0, "PARTIAL")


# --- engine_r -------------------------------------------------------------------------

def test_engine_r_rebooks_an_active_result_to_its_own_r_total():
    for bars in ([ENTRY, FLAT, TP1_BAR], [ENTRY, STOP_BAR], [ENTRY, FLAT, FLAT]):
        res = of.engine_path(_active(), make_ohlcv(bars), 0)
        assert of.engine_r(_active(), res, "ACTIVE") == res.r_total


def test_engine_r_keeps_both_legs_of_an_active_plan_that_reaches_tp1_later():
    plan = _active(tp1_fraction=0.5, tp2=120.0)
    res = of.engine_path(plan, make_ohlcv([ENTRY, FLAT, TP1_BAR, TP2_BAR]), 0)
    assert of.engine_r(plan, res, "ACTIVE") == res.r_total == 2.949


def test_engine_r_partial_uses_the_live_tp1_leg_and_the_replays_runner():
    plan = _partial()
    res = of.engine_path(plan, make_ohlcv([ENTRY, FLAT, TP1_BAR, TP2_BAR]), 0)
    assert res.runner_outcome == "runner_tp2"
    assert of.engine_r(plan, res, "PARTIAL") == res.r_total == 2.949


def test_the_tp1_leg_is_shared_so_its_price_never_moves_the_delta():
    df = make_ohlcv([ENTRY, FLAT, TP1_BAR, TP2_BAR])
    deltas = []
    for tp1_price in (110.0, 111.0):
        plan = _partial(tp1_price=tp1_price)
        res = of.engine_path(plan, df, 0)
        deltas.append(round(of.actual_r(plan, 104.0, "PARTIAL")
                            - of.engine_r(plan, res, "PARTIAL"), 3))
    assert deltas == [-1.589, -1.589]


def test_engine_r_refuses_a_partial_result_with_no_runner_leg():
    lone_tp1 = ExitResult(outcome="win", runner_outcome=None, entry_index=0, exit_index=2,
                          entry_price=100.0, r_total=1.959,
                          legs=[{"fraction": 1.0, "exit_price": 110.0, "r": 1.959,
                                 "reason": "tp1"}])
    with pytest.raises(ValueError):
        of.engine_r(_partial(), lone_tp1, "PARTIAL")


# --- before costs (descriptive only) ------------------------------------------------------

def test_gross_figures_book_the_same_legs_without_costs():
    plan = _partial()
    res = of.engine_path(plan, make_ohlcv([ENTRY, FLAT, TP1_BAR, TP2_BAR]), 0)
    gross = of.GROSS_COST_MODEL
    assert of.actual_r(_active(), 104.0, "ACTIVE", cost_model=gross) == 0.8
    assert of.actual_r(plan, 104.0, "PARTIAL", cost_model=gross) == 1.4
    assert of.engine_r(plan, res, "PARTIAL", cost_model=gross) == 3.0


def test_gross_is_never_below_net_on_a_stop_exit():
    plan = _active()
    res = of.engine_path(plan, make_ohlcv([ENTRY, STOP_BAR]), 0)
    net = of.engine_r(plan, res, "ACTIVE")
    gross = of.engine_r(plan, res, "ACTIVE", cost_model=of.GROSS_COST_MODEL)
    assert (net, gross) == (-1.019, -1.0) and gross >= net
    assert of.actual_r(plan, 95.0, "ACTIVE", cost_model=of.GROSS_COST_MODEL) >= of.actual_r(
        plan, 95.0, "ACTIVE")


def test_cost_model_none_is_the_v2_model():
    plan = _active()
    assert of.actual_r(plan, 104.0, "ACTIVE", cost_model=None) == of.actual_r(
        plan, 104.0, "ACTIVE", cost_model=of.INSTRUMENT.cost_model) == 0.762


# --- cost parity ------------------------------------------------------------------------

def test_cost_parity_on_a_stop_exit_gives_zero_delta():
    plan = _active()
    res = of.engine_path(plan, make_ohlcv([ENTRY, STOP_BAR]), 0)
    exit_price = res.legs[0]["exit_price"]
    assert exit_price == 95.0
    assert of.actual_r(plan, exit_price, "ACTIVE") - of.engine_r(plan, res, "ACTIVE") == 0


def test_cost_parity_on_a_runner_trail_gives_zero_delta():
    plan = _partial(tp2=200.0)
    res = of.engine_path(plan, _trail_bars(), 0)
    assert res.runner_outcome == "runner_trail"
    exit_price = res.legs[1]["exit_price"]
    assert of.actual_r(plan, exit_price, "PARTIAL") == of.engine_r(plan, res, "PARTIAL")


def test_a_manual_exit_at_the_engines_tp2_price_still_pays_the_stop_slippage():
    """Target kind slips 5 bps, the manual leg 10: a real cost of exiting by hand."""
    plan = _partial()
    res = of.engine_path(plan, make_ohlcv([ENTRY, FLAT, TP1_BAR, TP2_BAR]), 0)
    assert of.actual_r(plan, 120.0, "PARTIAL") == 2.943
    assert of.engine_r(plan, res, "PARTIAL") == 2.949


# --- dollars ------------------------------------------------------------------------------

def test_dollar_risk_is_record_shares_times_the_initial_risk():
    assert of.dollar_risk(_active(), {"shares": 10}) == 50.0
    assert of.dollar_risk(_active(), {"shares": "7.5"}) == 37.5
    bear = _active(direction="bearish", stop_loss=105.0, tp1=90.0)
    assert of.dollar_risk(bear, {"shares": 10}) == 50.0


@pytest.mark.parametrize("trade", [None, {}, {"shares": None}, {"shares": "n/a"},
                                   {"shares": 0}])
def test_dollar_risk_is_none_without_usable_shares(trade):
    assert of.dollar_risk(_active(), trade) is None


def test_to_usd():
    assert of.to_usd(0.762, 50.0) == 38.1
    assert of.to_usd(-1.019, 37.5) == -38.21
    assert of.to_usd(None, 50.0) is None
    assert of.to_usd(0.5, None) is None
```

The 3.565, 3.697 and 3.691 figures were taken from `walk_v2` on these exact bars under `pin_code_defaults` (the real spiked frame, the clamped frame walked on its own indicators, and the un-spiked frame). The runner exits on bar 23 at the trailing stop itself (the bar opens at 129, above it), so its price, and therefore its R, moves with ATR. The gross figures: 0.8 = (104 - 100) / 5; 1.4 = 0.5 × 2 + 0.5 × 0.8; 3.0 = 0.5 × 2 + 0.5 × 4.

- [ ] **Step 2: Run it to verify it fails**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/analytics/test_override_fidelity_arms.py
```

Expected: FAIL, every test with `AttributeError: module 'swingbot.core.analytics.override_fidelity' has no attribute ...` (`INSTRUMENT`, `engine_path`, ...).

- [ ] **Step 3: Extend the import block**

In `$WT/swingbot/core/analytics/override_fidelity.py`, replace the two `swingbot` import lines written by V173-7:

```python
from swingbot.core.market.session import RTH_OPEN, US_MARKET_TZ, nyse_calendar, session_close
from swingbot.core.planning.plan_types import PlanStatus
```

with:

```python
from swingbot.core.backtesting.instrument import contract, costs
from swingbot.core.market.session import RTH_OPEN, US_MARKET_TZ, nyse_calendar, session_close
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.planning import exit_sim
from swingbot.core.planning.exit_sim import ExitResult
from swingbot.core.planning.exit_sim_v2 import fill_bar_exit, walk_v2
from swingbot.core.planning.plan_types import PlanStatus
from swingbot.core.planning.time_exit import TIME_EXIT_REASON
```

`contract.CostModel` is the dataclass `V2_COSTS` is built from (`exit_sim_v2.py` imports it from the same module).

- [ ] **Step 4: Append the engine path and the arms**

Append to the end of `$WT/swingbot/core/analytics/override_fidelity.py`:

```python
# --- the engine path and the two arms (V173-8) ---------------------------------

#: The instrument every arm is booked on: v2 fills and costs, as the sim.
INSTRUMENT = contract.resolve("v2")
#: "Before costs": the same legs with no slippage and no commission. Shown
#: next to the net figure, never used by the verdict decision (spec §4).
GROSS_COST_MODEL = contract.CostModel(commission_per_share=0.0, slippage_bps=0.0,
                                      stop_slippage_bps=0.0)

_TARGET_REASONS = frozenset({"tp1", "runner_tp2"})
_CLOSE_REASONS = frozenset({"timeout", "runner_timeout", "acceptance_exit", "stall_exit",
                            "runner_progress_stall", TIME_EXIT_REASON})


def hold_cap_bars(plan) -> int:
    """The walk length simulate_exit_v2 gives this plan."""
    return exit_sim._hold_cap_bars(plan, HORIZONS[plan.horizon_key]["max_holding_days"])


def engine_frame(df: pd.DataFrame, ov_idx: int) -> pd.DataFrame:
    """`df` with the override session's range shrunk to its open-close body.

    The human acted somewhere inside that session; the engine is never shown
    the session's high or low as a later path (spec §3, no lookahead). A
    touch of the real range is caught as `ambiguous` instead. Walk the result
    with `indicator_df=df` so ATR and structure still read the real bar."""
    frame = df.copy()
    open_, close = float(frame["Open"].iat[ov_idx]), float(frame["Close"].iat[ov_idx])
    frame.iloc[ov_idx, frame.columns.get_loc("High")] = max(open_, close)
    frame.iloc[ov_idx, frame.columns.get_loc("Low")] = min(open_, close)
    return frame


def engine_path(plan, df: pd.DataFrame, fill_idx: int, *,
                indicator_df: pd.DataFrame | None = None) -> ExitResult:
    """The plan left alone: the fill-bar stop check, then the v2 walk, from
    the live fill bar at the live fill price with the original stop. Never a
    mid-trade resume: the engine is deterministic, so replaying the whole
    trade is the counterfactual. `indicator_df` (same index as `df`) feeds
    only the runner's ATR and structure: the engine arm passes the real
    frame while walking the clamped one."""
    # tp1_index guard (v173): ExitResult.tp1_index is a plain class attribute,
    # not a dataclass field, so dataclasses.replace() returns a copy with the
    # default None and asdict() leaves it out. Callers read it from the object
    # returned here; never copy, re-build or serialise the result first.
    entry = float(plan.entry_price)
    early = fill_bar_exit(df, fill_idx, entry, plan, INSTRUMENT)
    if early is not None:
        return early
    return walk_v2(df, fill_idx, entry, plan, hold_cap_bars(plan), INSTRUMENT,
                   scale_out=plan.tp1_fraction < 1.0, indicator_df=indicator_df)


def leg_kind(reason: str) -> str:
    """The costs.EXIT_KINDS kind walk_v2 books a leg of this reason with."""
    if reason in _TARGET_REASONS:
        return "target"
    return "close" if reason in _CLOSE_REASONS else "stop"


def live_tp1_leg(plan) -> dict | None:
    """The realised TP1 leg as a raw costs.book leg; both arms share it."""
    leg = next((leg for leg in plan.legs_realized or [] if leg.get("reason") == "tp1"), None)
    if leg is None or leg.get("exit_price") is None:
        return None
    return {"fraction": float(plan.tp1_fraction), "exit_price": float(leg["exit_price"]),
            "reason": "tp1", "kind": "target"}


def _remainder(plan, state: str) -> float:
    """The position the override closed (plan_manager.py:1115)."""
    return 1.0 - float(plan.tp1_fraction) if state == PlanStatus.PARTIAL else 1.0


def _tp1_legs(plan, state: str) -> list[dict]:
    if state != PlanStatus.PARTIAL:
        return []
    leg = live_tp1_leg(plan)
    if leg is None:
        raise ValueError(f"{plan.plan_id}: PARTIAL at close but no realised tp1 leg")
    return [leg]


def _book(plan, legs: list[dict], cost_model=None) -> float:
    """One costs.book call: the plan's entry and original stop, every leg.
    `cost_model` None is the v2 model; GROSS_COST_MODEL gives before costs."""
    entry, stop = float(plan.entry_price), float(plan.stop_loss)
    sign = 1 if plan.direction == "bullish" else -1
    if (entry - stop) * sign <= 0:
        raise ValueError(f"{plan.plan_id}: entry {entry} is at or beyond the stop {stop}")
    model = INSTRUMENT.cost_model if cost_model is None else cost_model
    r_total, _ = costs.book(model, direction=plan.direction,
                            entry_price=entry, stop_loss=stop, legs=legs)
    return r_total


def actual_r(plan, exit_price: float, state: str, *, cost_model=None) -> float:
    """The override as booked: the live TP1 leg (PARTIAL) plus the closed
    remainder at `exit_price`, a stop-kind exit (a market order by hand)."""
    manual = {"fraction": _remainder(plan, state), "exit_price": float(exit_price),
              "reason": "manual", "kind": "stop"}
    return _book(plan, [*_tp1_legs(plan, state), manual], cost_model)


def engine_r(plan, result: ExitResult, state: str, *, cost_model=None) -> float:
    """The replay as booked: the live TP1 leg (PARTIAL; the replay's own tp1
    leg is dropped) plus the replay's remainder legs, re-scaled to the
    remainder, each with the kind the engine books its reason with."""
    partial = state == PlanStatus.PARTIAL
    own = [leg for leg in result.legs if not (partial and leg.get("reason") == "tp1")]
    total = sum(float(leg["fraction"]) for leg in own)
    if total <= 0:
        raise ValueError(f"{plan.plan_id}: the engine result has no leg to book")
    scale = _remainder(plan, state) / total
    legs = [{"fraction": float(leg["fraction"]) * scale, "exit_price": float(leg["exit_price"]),
             "reason": leg["reason"], "kind": leg_kind(leg["reason"])} for leg in own]
    return _book(plan, [*_tp1_legs(plan, state), *legs], cost_model)


def dollar_risk(plan, trade: dict | None) -> float | None:
    """Dollars at risk at the fill: the linked paper trade's record shares
    times the initial risk per share (the v170 convention). None when the
    trade or its shares are missing: the row then shows R only."""
    if not trade or trade.get("shares") is None:
        return None
    if plan.entry_price is None or plan.stop_loss is None:
        return None
    try:
        shares = float(trade["shares"])
    except (TypeError, ValueError):
        return None
    risk = shares * abs(float(plan.entry_price) - float(plan.stop_loss))
    return risk if risk > 0 else None


def to_usd(r: float | None, risk: float | None) -> float | None:
    """R in dollars; None when either side is unknown."""
    if r is None or risk is None:
        return None
    return round(r * risk, 2)
```

Paper-trade `shares` are stored positive for both directions (`performance.py:477-480` applies the direction sign separately), so one formula serves bulls and bears.

- [ ] **Step 5: Run the new test, the V173-7 test and the V173-21 test**

```bash
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/analytics/test_override_fidelity_arms.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/analytics/test_override_fidelity_sessions.py
python E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/scripts/dev/testrun.py file tests/planning/test_exit_sim_v2_indicator_frame.py
```

Expected: all three PASS, `0 failed`, `0 xfailed`.

If a numeric expectation is off by 0.001, do not loosen it to `approx`. Recompute it with `costs.book(resolve("v2").cost_model, ...)` (or `walk_v2` on the same bars under `pin_code_defaults`) in a scratch script in the session scratchpad. A mismatch means the legs, kinds or frames differ from the ones described above, and that is the bug to fix. If `test_clamping_a_wide_override_bar_leaves_the_atr_driven_trail_unchanged` gives 3.697, `indicator_df` is not reaching `walk_v2`: check `engine_path`, then V173-21.

- [ ] **Step 6: Purity and complexity**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides grep -n "open(\|requests\|PlanStore\|TradeLog\|data_store\|cached_daily_bars\|get_current_price" -- swingbot/core/analytics/override_fidelity.py
python -m radon cc -s -n C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides/swingbot/core/analytics/override_fidelity.py
```

Expected: the `grep` finds nothing (the module does no I/O; bars are read only by `override_io`, V173-26). The `radon` call prints nothing.

- [ ] **Step 7: Commit on the branch**

```bash
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides add swingbot/core/analytics/override_fidelity.py tests/analytics/test_override_fidelity_arms.py
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-18-v173-execution-fidelity-overrides commit -m "feat(v173): replay an override from its fill on real indicators and book both arms net and gross"
git -C E:/Documents/Private/Projects/Discord-Bot status --short
```

The last command checks the main tree stayed clean of branch edits.

