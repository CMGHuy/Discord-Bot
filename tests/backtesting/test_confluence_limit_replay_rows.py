"""v212 replay module, part 2: entry rows for the reference and every cell --
a fill, a TP1 cancel, a drop, a gap through the stop, the touch sensitivity
-- and the window filter on replay_entries."""
import pytest

from swingbot.core.backtesting import confluence_limit_replay as clr
from tests.backtesting.test_confluence_limit_replay import (  # noqa: F401  (autouse fixture)
    DIP, GAP_UNDER_STOP, I, TO_TP1, _frictions, frame, ref_plan)


def _rows(df, ref=None, touch=False):
    ref = ref or ref_plan()
    rows = clr.entry_rows(df, I, ref, clr.arm_plans(ref, min_rr=1.5), touch=touch)
    return {row["arm"]: row for row in rows}


def test_instrument_is_v2_fills_with_zero_costs():
    costs = clr.REPLAY_INSTRUMENT.cost_model
    assert clr.REPLAY_INSTRUMENT.fill_model.market_entry == "next_open"
    assert (costs.slippage_bps, costs.stop_slippage_bps, costs.commission_per_share) == (0, 0, 0)


def test_every_arm_gets_a_row_with_the_same_pairing_key():
    rows = _rows(frame(DIP, TO_TP1))
    assert set(rows) == {"ref", *clr.CELLS}
    assert {row["key"] for row in rows.values()} == {"XYZ|4w|2021-01-29|bullish"}
    assert {row["market"] for row in rows.values()} == {100.0}


def test_reference_fills_at_the_next_open_and_stops():
    ref = _rows(frame(DIP, TO_TP1))["ref"]
    assert (ref["filled"], ref["entry"], ref["fill_date"]) == (True, 100.0, "2021-02-01")
    assert (ref["outcome"], ref["r_gross"]) == ("loss", pytest.approx(-1.0))
    assert ref["r_net"] < ref["r_gross"]
    assert ref["early_stop"] is True and ref["limit"] is None


def test_a_filled_arm_books_a_win():
    half = _rows(frame(DIP, TO_TP1))["f0.5"]
    assert (half["filled"], half["entry"], half["outcome"]) == (True, 98.5, "win")
    assert (half["entry_date"], half["fill_date"]) == ("2021-01-29", "2021-02-01")
    assert (half["limit"], half["stop_loss"]) == (98.5, 96.75)
    assert half["stop_pct"] == pytest.approx(1.7766, abs=1e-3)
    assert half["r_gross"] > half["r_net"] > 0
    assert half["early_stop"] is False and half["gap_stopped"] is False
    assert half["fill_rule"] == "trade_through"


def test_tp1_first_cancels_and_a_drop_carries_its_reason():
    rows = _rows(frame(DIP, TO_TP1))
    two_thirds, third = rows["f0.667"], rows["f0.333"]
    assert (two_thirds["filled"], two_thirds["outcome"]) == (False, "not_triggered")
    assert (two_thirds["exit_reason"], two_thirds["r_net"]) == ("limit_tp1_cancel", None)
    assert (third["outcome"], third["dropped"], third["r_net"]) == (
        "dropped", "limit_stop_beyond_cap", None)


def test_touch_sensitivity_fills_a_bare_touch_and_leaves_the_reference():
    rows = _rows(frame(DIP, TO_TP1), touch=True)
    assert (rows["f0.667"]["filled"], rows["f0.667"]["entry"]) == (True, 98.0)
    assert rows["f0.667"]["fill_rule"] == "touch"
    assert rows["ref"] == {**_rows(frame(DIP, TO_TP1))["ref"], "fill_rule": "touch"}


def test_gap_through_the_stop_is_a_realised_fill_at_the_open():
    rows = _rows(frame(GAP_UNDER_STOP))
    half = rows["f0.5"]
    assert (half["filled"], half["entry"], half["gap_stopped"]) == (True, 96.0, True)
    assert (half["outcome"], half["exit_reason"]) == ("loss", "filled_stopped_gap")
    assert half["fill_date"] == half["exit_date"] == "2021-02-01"
    assert half["r_gross"] == pytest.approx(0.0)
    assert -0.1 < half["r_net"] < 0.0                    # frictions only, never -1R
    assert half["gap_stop_r_from_limit"] < -1.0          # the pessimistic from-L reading
    assert rows["ref"]["filled"] is False                # the market plan's own gap cancel


def test_atr_reads_bars_up_to_the_signal_only():
    calm, wild = _rows(frame(DIP, TO_TP1))["ref"], _rows(frame(GAP_UNDER_STOP))["ref"]
    assert calm["atr14_pct"] == pytest.approx(0.2) == wild["atr14_pct"]


def test_replay_entries_window_and_cells(monkeypatch):
    monkeypatch.setattr(clr, "replay_scenarios", lambda *a, **k: [(I, ref_plan())])
    df = frame(DIP, TO_TP1)
    assert clr.replay_entries("XYZ", df, ["4w"], ("2021-02-01", None)) == []
    assert len(clr.replay_entries("XYZ", df, ["4w"], ("2021-01-29", "2021-01-29"))) == 4
    one = clr.replay_entries("XYZ", df, ["4w"], (None, None), cells=(0.5,))
    assert [row["arm"] for row in one] == ["ref", "f0.5"]
    touched = clr.replay_entries("XYZ", df, ["4w"], (None, None), touch=True)
    assert {row["fill_rule"] for row in touched} == {"touch"}


def test_partial_legs_weight_the_gross_r_by_their_fraction():
    half = _rows(frame(DIP, TO_TP1))["f0.5"]           # TP1 104 on half, TP2 106 on half
    assert half["r_gross"] == pytest.approx((0.5 * 5.5 + 0.5 * 7.5) / 1.75)
    assert half["planned_rr"] == pytest.approx(5.5 / 1.75)


def _stub(entry_index, exit_index, legs, outcome="loss", entry_price=100.0):
    from types import SimpleNamespace
    return SimpleNamespace(entry_index=entry_index, exit_index=exit_index, outcome=outcome,
                           entry_price=entry_price,
                           legs=[{"fraction": f, "exit_price": px, "reason": "stop"}
                                 for f, px in legs])


@pytest.mark.parametrize("exit_index,early", [(20, True), (22, True), (23, False)])
def test_early_stop_is_a_loss_fewer_than_three_bars_after_the_fill(exit_index, early):
    scores = clr._scores(frame(DIP, TO_TP1), ref_plan(), _stub(20, exit_index, [(1.0, 98.25)]))
    assert scores["early_stop"] is early


def test_a_quick_win_is_never_an_early_stop():
    res = _stub(20, 20, [(1.0, 104.0)], outcome="win")
    assert clr._scores(frame(DIP, TO_TP1), ref_plan(), res)["early_stop"] is False


def test_a_short_books_its_gross_r_against_the_price():
    scores = clr._scores(frame(DIP, TO_TP1), ref_plan("bearish"), _stub(20, 21, [(1.0, 101.75)]))
    assert scores["r_gross"] == pytest.approx(-1.0)
    assert scores["r_net"] < -1.0


def test_wick_through_flags_a_stop_bar_that_closed_back_above():
    rows, gap = _rows(frame(DIP, TO_TP1)), _rows(frame(GAP_UNDER_STOP))
    assert rows["ref"]["wick_through"] is True          # low 98.0 < 98.25, close 99.0 above
    assert gap["f0.5"]["wick_through"] is False         # gap exit, not a stop leg
    assert rows["f0.5"]["wick_through"] is False        # a win


def test_the_reference_is_simulated_without_touch(monkeypatch):
    seen = []
    real = clr.simulate_exit_v2

    def spy(df, i, plan, instrument, **kw):
        seen.append((plan.entry_type, kw["touch_fill"]))
        return real(df, i, plan, instrument, **kw)

    monkeypatch.setattr(clr, "simulate_exit_v2", spy)
    _rows(frame(DIP, TO_TP1), touch=True)
    assert seen[0] == ("market", False)
    assert {flag for _, flag in seen[1:]} == {True}


def test_a_no_trade_result_is_unfilled_and_carries_no_r():
    res = _stub(None, None, [], outcome="no_trade", entry_price=None)
    row = clr._row(frame(DIP, TO_TP1), I, ref_plan(), "ref", ref_plan(), res, False)
    assert (row["filled"], row["entry"], row["fill_date"], row["r_net"]) == (
        False, None, None, None)
