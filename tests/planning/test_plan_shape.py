"""v113: one plan shape per strategy, read by the live builder and the backtest alike."""
import pytest

from swingbot import config
from swingbot.core.market.strategy_types import BREAKEVEN_TRIGGER_FRACTION
from swingbot.core.planning import builders, params
from swingbot.core.planning.plan_types import PlanStatus

LIMIT = {"entry_type": "limit", "expiry_bars": 1, "tp1_fraction": 1.0, "breakeven_trigger_fraction": 1.0}


@pytest.fixture(autouse=True)
def pins(monkeypatch):
    monkeypatch.setattr(config, "LEVEL_LIFECYCLE_STOPS_ENABLED", False, raising=False)
    monkeypatch.setattr(config, "DATA_DRIVEN_STOPS_ENABLED", False, raising=False)


def test_unlisted_strategies_keep_todays_shape():
    assert builders.plan_shape_for("MACD") == {
        "entry_type": "market", "expiry_bars": 5, "tp1_fraction": 0.5,
        "breakeven_trigger_fraction": BREAKEVEN_TRIGGER_FRACTION}


def test_a_listed_shape_overrides_only_its_keys(monkeypatch):
    monkeypatch.setitem(params.PLAN_SHAPES, "Probe", {"entry_type": "limit", "expiry_bars": 1})
    shape = builders.plan_shape_for("Probe")
    assert (shape["entry_type"], shape["expiry_bars"], shape["tp1_fraction"]) == ("limit", 1, 0.5)


def test_the_live_builder_uses_the_shape(market_df, monkeypatch):
    monkeypatch.setitem(params.PLAN_SHAPES, "RSI Divergence", dict(LIMIT))
    plan = next(p for i in range(400, 700)
                if (p := builders.build_strategy_plan(market_df, i, ticker="X", strategy="RSI Divergence",
                                                      horizon_key="4w", direction="bullish")) is not None)
    assert (plan.entry_type, plan.expiry_bars, plan.tp1_fraction, plan.breakeven_trigger_fraction,
            plan.entry_price, plan.status) == ("limit", 1, 1.0, 1.0, None, PlanStatus.PENDING)


def test_the_backtest_uses_the_shape(market_df, monkeypatch):
    from swingbot.core.backtesting import backtest as bt
    monkeypatch.setitem(params.PLAN_SHAPES, "Probe", dict(LIMIT))
    plan = bt._bt_plan(market_df, 500, ticker="X", strategy="Probe", horizon_key="4w",
                       direction="bullish", entry=100.0, stop_loss=98.0, take_profit=103.0,
                       tp2=None, trail_atr_mult=2.5)
    assert (plan.entry_type, plan.expiry_bars, plan.tp1_fraction,
            plan.breakeven_trigger_fraction, plan.entry_price) == ("limit", 1, 1.0, 1.0, None)
    default = bt._bt_plan(market_df, 500, ticker="X", strategy="MACD", horizon_key="4w",
                          direction="bullish", entry=100.0, stop_loss=98.0, take_profit=103.0,
                          tp2=None, trail_atr_mult=2.5)
    assert (default.entry_type, default.expiry_bars, default.tp1_fraction, default.entry_price) == (
        "market", 5, 0.5, 100.0)
