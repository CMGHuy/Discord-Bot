import numpy as np
import pandas as pd

import swingbot.core.backtesting.backtest as bt
from swingbot.core.edge.context import FEATURE_KEYS, entry_context
from tests.conftest import make_ohlcv


def _forced(monkeypatch, df, bar, **kwargs):
    bull = pd.Series(False, index=df.index)
    bear = pd.Series(False, index=df.index)
    bull.iloc[bar] = True
    monkeypatch.setattr(bt, "_vectorized_entries", lambda *args, **kw: (bull, bear))
    return bt.run_backtest("TEST", df, "EMA Crossover", "2w", **kwargs)


def test_v1_and_v2_trades_carry_context(monkeypatch):
    closes = np.full(120, 100.0); closes[81:] = 104.0
    df = make_ohlcv(closes, spread_pct=1.0)
    for kwargs in ({"exit_model": "v1"}, {"exit_model": "v2", "scale_out": True}):
        summary = _forced(monkeypatch, df, 80, frictions=False, **kwargs)
        assert summary.trades, kwargs
        context = summary.trades[0].context
        assert set(context) == set(FEATURE_KEYS)
        assert context["direction"] == "bullish" and context["regime2_state"] is None


def test_context_uses_only_bars_to_entry_and_joins_asof(monkeypatch):
    closes = np.full(120, 100.0); closes[81:] = 104.0
    df = make_ohlcv(closes, spread_pct=1.0)
    asof = pd.DataFrame({"regime2_state": ["bear_quiet"] * 120, "rs_pctile": 12.5,
                         "sector_pctile": np.nan, "rs_combined": 12.5}, index=df.index)
    summary = _forced(monkeypatch, df, 80, frictions=False, asof=asof)
    trade = summary.trades[0]
    direct = entry_context(df.iloc[:81], direction="bullish", horizon_key="2w",
                           stop=trade.stop_loss, target=trade.take_profit,
                           asof={"regime2_state": "bear_quiet", "rs_pctile": 12.5,
                                 "sector_pctile": None, "rs_combined": 12.5})
    assert trade.context == direct
