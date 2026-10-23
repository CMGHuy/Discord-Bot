import numpy as np
import pandas as pd
import pytest

from tests.conftest import make_ohlcv
from swingbot.core.edge.frictions import (BORROW_RATE_ANNUAL, apply_frictions, borrow_r,
                                          commission_r)


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


def test_borrow_rate_is_half_a_percent_a_year():
    assert BORROW_RATE_ANNUAL == 0.005


def test_borrow_r_golden_value():
    # $100 short for 73 calendar days at 0.5%/yr = $0.10; over $2 risk = 0.05R
    assert borrow_r(100.0, 2.0, 73) == pytest.approx(0.05, rel=1e-12)


def test_borrow_r_is_the_spec_expression_bit_for_bit():
    entry, risk, days = 87.375, 3.125, 11
    assert borrow_r(entry, risk, days) == entry * 0.005 / 365.0 * days / risk


def test_borrow_is_zero_for_a_same_day_exit():
    assert borrow_r(100.0, 2.0, 0) == 0.0


def test_borrow_counts_calendar_days_over_a_weekend():
    # Friday entry, Monday exit: three calendar days, not one session
    friday, monday = pd.Timestamp("2015-03-06"), pd.Timestamp("2015-03-09")
    days = (monday - friday).days
    assert days == 3
    assert borrow_r(100.0, 2.0, days) == pytest.approx(3 * borrow_r(100.0, 2.0, 1), rel=1e-12)


def test_borrow_r_is_vectorised_elementwise():
    entry = np.array([100.0, 50.0, 80.0])
    risk = np.array([2.0, 1.0, 4.0])
    days = np.array([0.0, 7.0, 30.0])
    out = borrow_r(entry, risk, days)
    assert isinstance(out, np.ndarray) and out.shape == (3,)
    assert out.tolist() == [borrow_r(e, r, d) for e, r, d in zip(entry, risk, days)]


def test_borrow_r_grows_with_price_and_time_and_shrinks_with_risk():
    base = borrow_r(100.0, 2.0, 10)
    assert borrow_r(200.0, 2.0, 10) == pytest.approx(2 * base)
    assert borrow_r(100.0, 2.0, 20) == pytest.approx(2 * base)
    assert borrow_r(100.0, 4.0, 10) == pytest.approx(base / 2)
