from swingbot.core.planning.plan_engine import build_strategy_plan
from tests.helpers import make_ohlcv


def test_build_strategy_plan_produces_a_correctly_ordered_bullish_plan():
    """Was test_shim_warns_and_matches_plan_engine, a parity check between
    the now-deleted swingbot.core.trade_plan.compute_trade_plan shim and
    plan_engine.build_strategy_plan (Task 14 of the v27 repo restructure --
    the shim was a thin adapter that called build_strategy_plan and reshaped
    its output, so the parity it proved is no longer checkable once it's
    gone). What's left is the real behaviour the shim's assertions were
    actually pinning: a bullish plan's stop sits below the trigger, which
    sits below the target."""
    df = make_ohlcv([100 + i * 0.5 for i in range(80)])
    plan = build_strategy_plan(df, len(df) - 1, ticker="AAPL", strategy="MACD",
                               horizon_key="4w", direction="bullish")
    assert plan is not None
    assert plan.stop_loss < plan.trigger_price < plan.tp1
