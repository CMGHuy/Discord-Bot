import pandas as pd

from swingbot.core.scanning import strategy_pass as sp
from tests.helpers import make_ohlcv


def test_returns_last_completed_bar_signals_only(monkeypatch):
    df = make_ohlcv([100 + i * .1 for i in range(400)], start="2024-06-03")

    def fake(strategy, frame, horizon_key, params=None, regimes=None):
        off = pd.Series(False, index=frame.index)
        bull, bear = off.copy(), off.copy()
        if strategy == "MACD": bull.iloc[-1] = True
        if strategy == "RSI": bear.iloc[-2] = True
        return bull, bear

    monkeypatch.setattr(sp, "entries_for", fake)
    monkeypatch.setattr(sp.market_context, "has_context", lambda _: True)
    assert ("MACD", "bullish") in sp.strategy_signals(df, "3m", spy_df=df)
    assert all(strategy != "RSI" for strategy, _ in sp.strategy_signals(df, "3m", spy_df=df))
