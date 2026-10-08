"""v131: PLAN_SHAPES' optional "limit_price" key, honoured by both plan constructors."""
import pandas as pd
import pytest

from swingbot import config
from swingbot.core.backtesting import backtest
from swingbot.core.market import entry_filters as ef
from swingbot.core.planning import builders, params
from swingbot.core.planning.plan_types import PlanStatus
from tests.helpers import make_ohlcv

PROBE = "Probe Limit"
HZ = "4w"


def _probe_price(df, index, horizon_key, direction):
    """2% under the bar's close, or no order on an odd bar."""
    return None if index % 2 else float(df["Close"].iloc[index]) * 0.98


def _probe_cancel(df, index, horizon_key, direction):
    return float(df["High"].iloc[index]) * 1.05


SEEN = []


def _probe_branch(inputs):
    """Stop 1% and target 3% from whatever entry the constructor hands in."""
    SEEN.append(inputs.close)
    return inputs.close * 0.99, inputs.close * 1.03, [inputs.close * 1.03], None


@pytest.fixture
def probe(monkeypatch):
    SEEN.clear()
    monkeypatch.setattr(config, "LEVEL_LIFECYCLE_STOPS_ENABLED", False)
    monkeypatch.setitem(params.PLAN_SHAPES, PROBE, {
        "entry_type": "limit", "expiry_bars": 3, "tp1_fraction": 0.5,
        "breakeven_trigger_fraction": 0.5, "limit_price": "probe"})
    monkeypatch.setitem(builders.LIMIT_PRICERS, "probe",
                        builders.LimitPricer(price=_probe_price, cancel_level=_probe_cancel))
    monkeypatch.setitem(builders._STRUCTURAL_BRANCHES, PROBE, _probe_branch)
    return PROBE


def _frame(n=80):
    return make_ohlcv([100.0 + 0.1 * k for k in range(n)], start="2020-01-02")


def test_build_strategy_plan_enters_at_the_limit_and_prices_from_it(probe):
    df = _frame()
    plan = builders.build_strategy_plan(df, 60, ticker="T", strategy=probe,
                                        horizon_key=HZ, direction="bullish")
    limit = float(df["Close"].iloc[60]) * 0.98
    assert SEEN == [pytest.approx(limit)]
    assert (plan.entry_type, plan.entry_price, plan.status) == ("limit", None, PlanStatus.PENDING)
    assert plan.trigger_price == pytest.approx(limit)
    assert plan.stop_loss == pytest.approx(limit * 0.99) and plan.tp1 == pytest.approx(limit * 1.03)
    assert plan.expiry_bars == 3
    assert plan.limit_cancel_level == pytest.approx(float(df["High"].iloc[60]) * 1.05)
    assert plan.limit_strict_fill is True


def test_no_limit_price_means_no_plan_in_either_constructor(probe):
    df = _frame()
    assert builders.build_strategy_plan(df, 61, ticker="T", strategy=probe,
                                        horizon_key=HZ, direction="bullish") is None
    assert backtest._v1_plan_levels(df, 61, "bullish", probe, HZ, backtest.atr(df, 14)) is None


def test_the_backtest_constructor_prices_the_same_plan(probe):
    df = _frame()
    live = builders.build_strategy_plan(df, 60, ticker="T", strategy=probe,
                                        horizon_key=HZ, direction="bullish")
    entry, stop, target = backtest._v1_plan_levels(df, 60, "bullish", probe, HZ, backtest.atr(df, 14))
    assert (entry, stop, target) == pytest.approx((live.trigger_price, live.stop_loss, live.tp1))
    plan = backtest._bt_plan(df, 60, ticker="T", strategy=probe, horizon_key=HZ,
                             direction="bullish", entry=entry, stop_loss=stop,
                             take_profit=target, tp2=None, trail_atr_mult=3.0)
    assert (plan.entry_type, plan.trigger_price, plan.expiry_bars) == ("limit", entry, 3)
    assert plan.limit_cancel_level == pytest.approx(live.limit_cancel_level)
    assert plan.limit_strict_fill is True


def test_run_backtest_records_every_placed_order_and_scores_from_the_fill(probe, monkeypatch):
    bars = [(100.0, 100.5, 99.5, 100.0)] * 60
    bars += [(100.0, 100.5, 99.5, 100.0)]          # bar 60: signal, limit 98.0, stop 97.02
    bars += [(99.0, 99.2, 97.9, 98.5)]             # bar 61: trades through 98.0 -> fill
    bars += [(98.5, 101.0, 98.4, 100.9)] * 3       # target 100.94 reached on bar 62
    bars += [(100.0, 100.5, 99.5, 100.0)] * 15
    df = make_ohlcv(bars, start="2020-01-02")
    fired = pd.Series(False, index=df.index)
    fired.iloc[60] = True
    monkeypatch.setitem(ef.ENTRY_FUNCS, probe, lambda d, hk, p=None: (fired.copy(), fired & False))
    summary = backtest.run_backtest("T", df, probe, HZ, exit_model="v2", scale_out=False)
    [trade] = summary.trades
    assert trade.entry == pytest.approx(98.0) and trade.outcome == "win"
    assert trade.r_multiple == pytest.approx((98.0 * 1.03 - 98.0) / (98.0 - 98.0 * 0.99), abs=1e-3)
    [order] = summary.limit_orders
    assert order["status"] == "filled" and order["fill_price"] == pytest.approx(98.0)
    assert order["signal_date"] == str(df.index[60].date())
    assert order["fill_date"] == str(df.index[61].date())
    assert order["same_bar_new_high"] is False


def test_an_unfilled_order_is_recorded_and_produces_no_trade(probe, monkeypatch):
    df = make_ohlcv([(100.0, 100.5, 99.5, 100.0)] * 80, start="2020-01-02")
    fired = pd.Series(False, index=df.index)
    fired.iloc[60] = True
    monkeypatch.setitem(ef.ENTRY_FUNCS, probe, lambda d, hk, p=None: (fired.copy(), fired & False))
    summary = backtest.run_backtest("T", df, probe, HZ, exit_model="v2", scale_out=True)
    assert summary.trades == []
    assert [order["status"] for order in summary.limit_orders] == ["expired"]


def test_an_unregistered_pricer_name_fails_loudly(monkeypatch):
    monkeypatch.setitem(params.PLAN_SHAPES, PROBE, {"entry_type": "limit", "limit_price": "nope"})
    with pytest.raises(KeyError):
        builders.limit_pricer_for(PROBE)


def test_a_strategy_without_the_key_keeps_its_entry_reference_and_defaults():
    df = _frame()
    assert builders.limit_pricer_for("RSI") is None
    assert builders.plan_entry_reference(df, 60, "RSI", HZ, "bullish") == float(df["Close"].iloc[60])
    assert builders.limit_order_fields(df, 60, "RSI", HZ, "bullish") == {}


def test_the_v113_fade_limit_keeps_its_touch_fill_and_records_no_orders():
    from swingbot.core.market.strategy_types import FADE_STRATEGY
    from tests.market.test_fib_sr_confluence import _trending_frame
    df = _trending_frame(400, -0.06, seed=11)
    plan = backtest._bt_plan(df, 300, ticker="T", strategy=FADE_STRATEGY, horizon_key="1w",
                             direction="bearish", entry=100.0, stop_loss=102.0,
                             take_profit=98.0, tp2=None, trail_atr_mult=2.5)
    assert (plan.entry_type, plan.limit_cancel_level, plan.limit_strict_fill) == ("limit", None, False)
    with ef.gate_override(FADE_STRATEGY, {"cells": frozenset({("bearish", "1w")})}):
        summary = backtest.run_backtest("T", df, FADE_STRATEGY, "1w", exit_model="v2", scale_out=True)
    assert summary.limit_orders == []
