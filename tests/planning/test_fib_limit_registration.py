"""v131: the masked `Fibonacci Limit` strategy -- entries, plan shape and sizing."""
import numpy as np
import pytest

from swingbot import config
from swingbot.core.backtesting import backtest
from swingbot.core.market import entry_filters as ef
from swingbot.core.market.indicators import atr
from swingbot.core.market.strategy_types import FIB_LIMIT, STRATEGY_GATES
from swingbot.core.planning import builders, params
from swingbot.core.planning.stop_scope import stop_ceiling
from tests.market.test_fib_sr_confluence import _trending_frame

HZ = "2w"
UNMASKED = {"directions": ("bullish",)}


def _frame():
    return _trending_frame(400, 0.06, seed=2)


def _arm_bars(df, horizon=HZ):
    return [int(t) for t in np.nonzero(ef.fibonacci_limit_setups(df, horizon)["arm"].to_numpy())[0]]


def test_ships_masked_and_out_of_the_backtest_strategy_list():
    assert STRATEGY_GATES[FIB_LIMIT] == {"directions": ()}
    assert FIB_LIMIT not in backtest.ALL_STRATEGIES
    bullish, bearish = ef.entries_for(FIB_LIMIT, _frame(), HZ)
    assert not bullish.any() and not bearish.any()


def test_the_masked_entry_function_skips_the_order_book(monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("masked strategy walked the order book")
    monkeypatch.setattr(ef, "fibonacci_limit_setups", boom)
    bullish, _ = ef.ENTRY_FUNCS[FIB_LIMIT](_frame(), HZ)
    assert not bullish.any()


def test_unmasked_entries_are_the_arming_bars_bullish_only():
    df = _frame()
    with ef.gate_override(FIB_LIMIT, UNMASKED):
        bullish, bearish = ef.entries_for(FIB_LIMIT, df, HZ)
    assert [int(t) for t in np.nonzero(bullish.to_numpy())[0]] == _arm_bars(df)
    assert bullish.any() and not bearish.any()


def test_plan_shape_and_exits_are_fibonacci_s_on_a_resting_limit():
    shape = builders.plan_shape_for(FIB_LIMIT)
    assert shape == {"entry_type": "limit", "expiry_bars": 5, "tp1_fraction": 0.5,
                     "breakeven_trigger_fraction": 0.5, "limit_price": "fib_zone"}
    assert shape["expiry_bars"] == ef.DEFAULT_PARAMS[FIB_LIMIT]["N"]
    assert params.exit_params_for(FIB_LIMIT) == params.exit_params_for("Fibonacci") == {
        "trail_atr_mult": 3.0, "tp2": False}
    assert builders.limit_pricer_for(FIB_LIMIT) is builders.LIMIT_PRICERS["fib_zone"]


def test_the_plan_is_priced_entirely_from_the_limit(monkeypatch):
    monkeypatch.setattr(config, "LEVEL_LIFECYCLE_STOPS_ENABLED", False)
    df = _frame()
    setups = ef.fibonacci_limit_setups(df, HZ)
    built = 0
    for t in _arm_bars(df):
        plan = builders.build_strategy_plan(df, t, ticker="T", strategy=FIB_LIMIT,
                                            horizon_key=HZ, direction="bullish")
        if plan is None:
            continue
        built += 1
        limit = float(setups["limit_price"].iloc[t])
        atr_val = builders._safe_atr_value(limit, float(atr(df, 14).iloc[t]))
        raw_stop = float(setups["swing_low"].iloc[t]) - params.STRUCTURE_BUFFER_ATR * atr_val
        ceiling = stop_ceiling(FIB_LIMIT, "bullish", HZ)[0]
        assert plan.trigger_price == pytest.approx(limit) and plan.entry_price is None
        assert plan.stop_loss == pytest.approx(max(raw_stop, limit * (1 - ceiling / 100)))
        risk = limit - plan.stop_loss
        assert 1.5 - 1e-9 <= (plan.tp1 - limit) / risk <= 2.5 + 1e-9
        assert plan.limit_cancel_level == float(setups["swing_high"].iloc[t])
        assert plan.limit_strict_fill is True and plan.expiry_bars == 5
    assert built >= 1, "fixture must build at least one plan"


def test_no_bearish_plan():
    df = _frame()
    t = _arm_bars(df)[0]
    assert builders.build_strategy_plan(df, t, ticker="T", strategy=FIB_LIMIT,
                                        horizon_key=HZ, direction="bearish") is None


def test_backtest_and_live_constructors_agree():
    df = _frame()
    atr_series = backtest.atr(df, 14)
    for t in _arm_bars(df):
        live = builders.build_strategy_plan(df, t, ticker="T", strategy=FIB_LIMIT,
                                            horizon_key=HZ, direction="bullish")
        bt = backtest._v1_plan_levels(df, t, "bullish", FIB_LIMIT, HZ, atr_series)
        if live is None:
            assert bt is None
            continue
        assert bt == pytest.approx((live.trigger_price, live.stop_loss, live.tp1))


def test_run_backtest_scores_fills_from_the_limit_and_records_every_order():
    df = _frame()
    with ef.gate_override(FIB_LIMIT, UNMASKED):
        summary = backtest.run_backtest("T", df, FIB_LIMIT, HZ, exit_model="v2", scale_out=True)
    assert summary.limit_orders, "fixture must place at least one order"
    assert {order["status"] for order in summary.limit_orders} <= {"filled", "expired", "cancelled"}
    filled = [order for order in summary.limit_orders if order["status"] == "filled"]
    assert len(filled) == len(summary.trades)
    for order, trade in zip(filled, summary.trades):
        assert trade.entry_date == order["signal_date"]
        assert trade.entry == pytest.approx(order["limit_price"], abs=1e-4)
        assert order["fill_price"] <= order["limit_price"] + 1e-9
        assert order["fill_date"] > order["signal_date"]


def test_truncation_invariance_of_the_built_plan():
    """No lookahead in the plan: the plan at t is the same from df.iloc[:t+1]."""
    df = _frame()
    for t in _arm_bars(df):
        full = builders.build_strategy_plan(df, t, ticker="T", strategy=FIB_LIMIT,
                                            horizon_key=HZ, direction="bullish")
        cut = builders.build_strategy_plan(df.iloc[:t + 1], t, ticker="T", strategy=FIB_LIMIT,
                                           horizon_key=HZ, direction="bullish")
        assert (full is None) == (cut is None)
        if full is not None:
            assert (cut.trigger_price, cut.stop_loss, cut.tp1, cut.limit_cancel_level) == pytest.approx(
                (full.trigger_price, full.stop_loss, full.tp1, full.limit_cancel_level))


@pytest.mark.parametrize("scale", [20.0, 0.05])
def test_arming_is_price_scale_invariant(scale):
    """The masked entry is trivially scale-invariant in test_spot_scaling_parity;
    pin the unmasked arming rule here."""
    df = _frame()
    scaled = df.copy()
    scaled[["Open", "High", "Low", "Close"]] *= scale
    assert _arm_bars(scaled) == _arm_bars(df)
