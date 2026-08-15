import numpy as np
import pandas as pd
import pytest

from tests.conftest import make_ohlcv
from swingbot.core.edge.frictions import apply_frictions, commission_r


def test_slippage_direction_golden():
    assert apply_frictions(100.0, "buy", 5) == pytest.approx(100.05)
    assert apply_frictions(100.0, "sell", 5) == pytest.approx(99.95)
    assert apply_frictions(100.0, "buy", 0) == 100.0


def test_commission_r_golden():
    # $1 per side, $100 risk basis -> 2 x 1/100 = 0.02R round trip
    assert commission_r(risk_dollars=100.0, commission=1.0) == pytest.approx(0.02)


def test_backtest_frictions_reduce_r(monkeypatch):
    import swingbot.core.backtesting.backtest as bt
    df = make_ohlcv(np.full(80, 100.0), spread_pct=1.0)
    bull = pd.Series(False, index=df.index); bull.iloc[40] = True
    bear = pd.Series(False, index=df.index)
    monkeypatch.setattr(bt, "_vectorized_entries", lambda *a, **k: (bull, bear))
    clean = bt.run_backtest("TEST", df, "EMA Crossover", "2w", frictions=False)
    real = bt.run_backtest("TEST", df, "EMA Crossover", "2w", frictions=True)
    assert clean.trades and real.trades
    # same bars, worse arithmetic: friction expectancy strictly lower
    assert real.expectancy_r < clean.expectancy_r


def test_frictions_off_is_bit_identical_to_before(monkeypatch):
    import swingbot.core.backtesting.backtest as bt
    df = make_ohlcv(np.full(80, 100.0), spread_pct=1.0)
    bull = pd.Series(False, index=df.index); bull.iloc[40] = True
    monkeypatch.setattr(bt, "_vectorized_entries",
                        lambda *a, **k: (bull, pd.Series(False, index=df.index)))
    s = bt.run_backtest("TEST", df, "EMA Crossover", "2w", frictions=False)
    t = s.trades[0]
    assert t.entry == 100.0  # unslipped fill preserved when off
