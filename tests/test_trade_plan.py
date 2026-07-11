import numpy as np
import pytest

from tests.conftest import make_trend_df


def _fake_result(strategy, horizon="4w", trend="bullish", close=100.0):
    from swingbot.core.strategy_types import HORIZONS, SignalResult
    return SignalResult(
        ticker="TEST", strategy=strategy, horizon_key=horizon,
        horizon_label=HORIZONS[horizon]["label"], trend=trend,
        triggered=True, close=close, details={},
    )


def test_compute_trade_plan_is_deprecated():
    from swingbot.core.trade_plan import compute_trade_plan
    df = make_trend_df(300, +0.1)
    with pytest.warns(DeprecationWarning):
        compute_trade_plan(_fake_result("VWAP", close=float(df["Close"].iloc[-1])), df)


def test_atr_sized_plan_uses_strategy_rr_override():
    from swingbot.core.trade_plan import compute_trade_plan
    from swingbot.core.strategy_types import STRATEGY_RR_OVERRIDE

    df = make_trend_df(300, +0.1)
    result = _fake_result("EMA Crossover", close=float(df["Close"].iloc[-1]))
    plan = compute_trade_plan(result, df)
    reward = abs(plan.take_profit - plan.entry)
    risk = abs(plan.entry - plan.stop_loss)
    assert reward / risk == pytest.approx(STRATEGY_RR_OVERRIDE["EMA Crossover"], rel=0.01)


def test_plan_carries_management_note():
    from swingbot.core.trade_plan import compute_trade_plan, MANAGEMENT_NOTE
    df = make_trend_df(300, +0.1)
    plan = compute_trade_plan(_fake_result("VWAP", close=float(df["Close"].iloc[-1])), df)
    assert plan.management_note == MANAGEMENT_NOTE
    assert "stop to entry" in MANAGEMENT_NOTE


def test_fibonacci_plan_uses_strategy_rr_override():
    from swingbot.core.trade_plan import compute_trade_plan
    from swingbot.core.strategy_types import HORIZONS, SignalResult, STRATEGY_RR_OVERRIDE

    df = make_trend_df(300, +0.1)
    close = float(df["Close"].iloc[-1])
    result = SignalResult(
        ticker="TEST", strategy="Fibonacci", horizon_key="4w",
        horizon_label=HORIZONS["4w"]["label"], trend="bullish",
        triggered=True, close=close,
        details={"Swing high": close * 1.3, "Swing low": close * 0.7},
    )
    plan = compute_trade_plan(result, df)
    reward = abs(plan.take_profit - plan.entry)
    risk = abs(plan.entry - plan.stop_loss)
    assert reward / risk == pytest.approx(STRATEGY_RR_OVERRIDE["Fibonacci"], rel=0.01)


def test_support_resistance_plan_uses_strategy_rr_override():
    from swingbot.core.trade_plan import compute_trade_plan
    from swingbot.core.strategy_types import HORIZONS, SignalResult, STRATEGY_RR_OVERRIDE

    df = make_trend_df(300, +0.1)
    close = float(df["Close"].iloc[-1])
    result = SignalResult(
        ticker="TEST", strategy="Support/Resistance", horizon_key="4w",
        horizon_label=HORIZONS["4w"]["label"], trend="bullish",
        triggered=True, close=close,
        details={"Resistance": close * 0.99, "Support": close * 0.9, "Volume ratio": 2.0},
    )
    plan = compute_trade_plan(result, df)
    reward = abs(plan.take_profit - plan.entry)
    risk = abs(plan.entry - plan.stop_loss)
    assert reward / risk == pytest.approx(STRATEGY_RR_OVERRIDE["Support/Resistance"], rel=0.01)
