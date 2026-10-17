"""v157 FC3: instrument/costs.py -- slippage and commission to R, booked once."""
import pytest

from swingbot.core.backtesting.instrument import costs
from swingbot.core.backtesting.instrument.contract import V2_COSTS, ZERO_COSTS, CostModel


def _leg(exit_price, kind, fraction=1.0, reason="x"):
    return {"fraction": fraction, "exit_price": exit_price, "reason": reason, "kind": kind}


def test_slip_moves_a_buy_up_and_a_sell_down():
    assert costs.slip(100.0, buy=True, bps=5.0) == pytest.approx(100.05)
    assert costs.slip(100.0, buy=False, bps=10.0) == pytest.approx(99.9)
    assert costs.slip(100.0, buy=True, bps=0.0) == 100.0


def test_stop_exits_pay_the_stop_rate_and_everything_else_the_base_rate():
    assert costs.exit_bps(V2_COSTS, "stop") == 10.0
    assert costs.exit_bps(V2_COSTS, "target") == 5.0
    assert costs.exit_bps(V2_COSTS, "close") == 5.0


def test_unknown_exit_kind_is_refused():
    with pytest.raises(ValueError, match="exit kind"):
        costs.exit_bps(V2_COSTS, "gap")


def test_zero_costs_book_the_gross_price_r():
    r_total, legs = costs.book(ZERO_COSTS, direction="bullish", entry_price=100.0,
                               stop_loss=95.0, legs=[_leg(93.0, "stop", reason="stop")])
    assert r_total == -1.4
    assert legs == [{"fraction": 1.0, "exit_price": 93.0, "r": -1.4, "reason": "stop"}]


def test_bullish_stop_loss_pays_entry_and_stop_slippage():
    # entry 100 * 1.0005 = 100.05; exit 95 * 0.999 = 94.905; risk 100.05 - 95 = 5.05
    r_total, legs = costs.book(V2_COSTS, direction="bullish", entry_price=100.0,
                               stop_loss=95.0, legs=[_leg(95.0, "stop")])
    assert r_total == round((94.905 - 100.05) / 5.05, 3) == -1.019
    assert legs[0]["exit_price"] == 95.0                     # raw price kept


def test_bullish_target_pays_the_base_rate_both_sides():
    # exit 110 * 0.9995 = 109.945
    r_total, _ = costs.book(V2_COSTS, direction="bullish", entry_price=100.0,
                            stop_loss=95.0, legs=[_leg(110.0, "target")])
    assert r_total == round((109.945 - 100.05) / 5.05, 3) == 1.959


def test_bearish_slippage_is_mirrored():
    # short: sells 100 * 0.9995 = 99.95; buys back the 105 stop at 105 * 1.001 = 105.105
    r_total, _ = costs.book(V2_COSTS, direction="bearish", entry_price=100.0,
                            stop_loss=105.0, legs=[_leg(105.0, "stop")])
    assert r_total == round(-(105.105 - 99.95) / (105.0 - 99.95), 3) == -1.021


def test_commission_is_a_round_trip_per_share_in_r():
    model = CostModel(commission_per_share=0.05, slippage_bps=0.0, stop_slippage_bps=0.0)
    r_total, legs = costs.book(model, direction="bullish", entry_price=100.0,
                               stop_loss=95.0, legs=[_leg(110.0, "target")])
    assert r_total == round((10.0 - 0.10) / 5.0, 3) == 1.98
    assert legs[0]["r"] == 1.98


def test_r_total_sums_unrounded_leg_r_and_rounds_once():
    # risk 3: leg r 0.00333 and 0.02000. Summing the rounded legs gives 0.011;
    # the unrounded sum, rounded once, gives 0.012.
    r_total, legs = costs.book(ZERO_COSTS, direction="bullish", entry_price=100.0,
                               stop_loss=97.0,
                               legs=[_leg(100.01, "target", 0.5), _leg(100.06, "close", 0.5)])
    assert [leg["r"] for leg in legs] == [0.003, 0.02]
    assert round(0.5 * 0.003 + 0.5 * 0.02, 3) == 0.011
    assert r_total == 0.012


def test_scale_out_legs_book_each_leg_at_its_own_kind():
    r_total, legs = costs.book(V2_COSTS, direction="bullish", entry_price=100.0,
                               stop_loss=95.0,
                               legs=[_leg(110.0, "target", 0.5, "tp1"),
                                     _leg(104.0, "stop", 0.5, "runner_be")])
    r1 = (110.0 * 0.9995 - 100.05) / 5.05
    r2 = (104.0 * 0.999 - 100.05) / 5.05
    assert [leg["r"] for leg in legs] == [round(r1, 3), round(r2, 3)]
    assert r_total == round(0.5 * r1 + 0.5 * r2, 3)
    assert [leg["reason"] for leg in legs] == ["tp1", "runner_be"]


def test_an_entry_at_or_beyond_the_stop_is_refused():
    with pytest.raises(ValueError, match="at or beyond the stop"):
        costs.book(ZERO_COSTS, direction="bullish", entry_price=95.0, stop_loss=95.0,
                   legs=[_leg(95.0, "stop")])
    with pytest.raises(ValueError, match="at or beyond the stop"):
        costs.book(ZERO_COSTS, direction="bearish", entry_price=106.0, stop_loss=105.0,
                   legs=[_leg(105.0, "stop")])
