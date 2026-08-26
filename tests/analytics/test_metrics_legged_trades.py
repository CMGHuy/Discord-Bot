import pytest

from swingbot.core.analytics.metrics import r_multiple, trade_return_pct
from swingbot.core.tracking.risk_metrics import _trade_return_pct


def _legged_trade() -> dict:
    return {
        "direction": "bullish",
        "entry": 100.0,
        "stop_loss": 95.0,
        # The final runner leg is near breakeven; pricing this field alone
        # drops the TP1 gain from every analytics surface.
        "exit_price": 100.25,
        "legs": [
            {"fraction": 0.5, "r": 2.0, "exit_price": 110.0},
            {"fraction": 0.5, "r": 0.05, "exit_price": 100.25},
        ],
    }


def test_legged_trade_blends_r_and_return_instead_of_pricing_runner_only():
    trade = _legged_trade()

    assert r_multiple(trade) == pytest.approx(1.02)
    # 0.5 * +10% at TP1 plus 0.5 * +0.25% on the runner.
    assert trade_return_pct(trade) == pytest.approx(5.125)
    assert _trade_return_pct(trade) == pytest.approx(5.125)


def test_legged_trade_derives_r_from_a_leg_exit_when_r_is_missing():
    trade = _legged_trade()
    trade["legs"][0].pop("r")

    assert r_multiple(trade) == pytest.approx(1.02)


def test_no_legs_preserves_the_existing_single_exit_formulas_exactly():
    trade = {
        "direction": "bearish",
        "entry": 100.0,
        "stop_loss": 105.0,
        "exit_price": 96.0,
        "legs": [],
    }

    assert r_multiple(trade) == 0.8
    assert trade_return_pct(trade) == 4.0
    assert _trade_return_pct(trade) == 4.0
