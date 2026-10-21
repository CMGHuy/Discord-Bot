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
