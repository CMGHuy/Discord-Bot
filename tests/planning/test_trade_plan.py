import pytest
from swingbot.core.strategy_types import SignalResult
from swingbot.core.trade_plan import compute_trade_plan
from swingbot.core.plan_engine import build_strategy_plan
from tests.helpers import make_ohlcv


def _result(df, strategy="MACD"):
    return SignalResult(ticker="AAPL", strategy=strategy, horizon_key="4w",
                        horizon_label="4-week swing", trend="bullish",
                        triggered=True, close=float(df["Close"].iloc[-1]))


def test_shim_warns_and_matches_plan_engine():
    df = make_ohlcv([100 + i * 0.5 for i in range(80)])
    with pytest.warns(DeprecationWarning):
        legacy = compute_trade_plan(_result(df), df)
    v2 = build_strategy_plan(df, len(df) - 1, ticker="AAPL", strategy="MACD",
                             horizon_key="4w", direction="bullish")
    assert legacy.stop_loss == pytest.approx(v2.stop_loss)
    assert legacy.take_profit == pytest.approx(v2.tp1)
