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


@pytest.mark.parametrize("rows", [{OV_IDX: BE_WICK}, {16: BE_WICK, OV_IDX: BE_WICK},
                                  {OV_IDX: BE_BODY}, {}])
def test_the_breakeven_check_reads_nothing_after_the_override_bar(rows):
    """Truncation (no-lookahead gate): cutting every bar after the override
    session never changes rule A's breakeven answer."""
    df = frame({**rows, 18: BE_WICK, 19: BE_BODY})
    cut = df.iloc[:OV_IDX + 1]
    assert (of._be_only_on_real_bar(plan(), df, FILL_IDX, OV_IDX)
            == of._be_only_on_real_bar(plan(), cut, FILL_IDX, OV_IDX))


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
