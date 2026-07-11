"""Parity + golden tests for the sizing builders extracted from
backtest._trade_plan_at into plan_engine (Tasks 8-13)."""
import numpy as np
import pytest

from swingbot.core import backtest
from swingbot.core.indicators import atr
from swingbot.core.plan_engine import (
    _atr_plan,
    _elliott_plan,
    _fibonacci_plan,
    _safe_atr_value,
    _sr_plan,
)
from swingbot.core.strategy_types import HORIZONS, STRATEGY_RR_OVERRIDE

from tests.helpers import make_ohlcv

I = 79  # reference bar


@pytest.fixture(scope="module")
def df():
    return make_ohlcv([100 + i * 0.5 for i in range(80)])


@pytest.fixture(scope="module")
def atr_series(df):
    return atr(df, 14)


def _entry_atr(df, atr_series):
    entry = float(df["Close"].iloc[I])
    return entry, _safe_atr_value(entry, float(atr_series.iloc[I]))


# --- golden asserts (Task 8) -------------------------------------------------

def test_atr_plan_bullish_golden():
    close, atr_val, h = 100.0, 2.0, "4w"
    stop, tp1 = _atr_plan(close, atr_val, "bullish", h, "MACD")
    mult = HORIZONS[h]["atr_stop_multiple"]
    rr = STRATEGY_RR_OVERRIDE["MACD"]
    exp_risk = min(mult * atr_val, close * HORIZONS[h]["max_risk_pct"] / 100)
    assert stop == pytest.approx(close - exp_risk)
    assert tp1 == pytest.approx(close + rr * exp_risk)


def test_atr_plan_bearish_mirror():
    stop, tp1 = _atr_plan(100.0, 2.0, "bearish", "4w", "MACD")
    assert stop > 100.0 and tp1 < 100.0


def test_rr_floor_applies():
    stop, tp1 = _atr_plan(100.0, 2.0, "bullish", "4w", "MACD")
    assert (tp1 - 100.0) / (100.0 - stop) >= 0.30 - 1e-9


# --- characterization parity vs backtest._trade_plan_at (Tasks 8-11) ---------

@pytest.mark.parametrize("direction", ["bullish", "bearish"])
@pytest.mark.parametrize("hk", ["4w", "3m"])
def test_atr_parity(df, atr_series, direction, hk):
    ref_entry, ref_stop, ref_tp = backtest._trade_plan_at(
        df, I, direction, "MACD", hk, atr_series)
    entry, atr_val = _entry_atr(df, atr_series)
    stop, tp = _atr_plan(entry, atr_val, direction, hk, "MACD")
    assert (stop, tp) == pytest.approx((ref_stop, ref_tp), abs=1e-9)


@pytest.mark.parametrize("direction", ["bullish", "bearish"])
def test_fibonacci_parity(df, atr_series, direction):
    hk = "4w"
    lookback = HORIZONS[hk]["fib_lookback"]
    sh = df["High"].rolling(lookback).max()
    sl = df["Low"].rolling(lookback).min()
    ref_entry, ref_stop, ref_tp = backtest._trade_plan_at(
        df, I, direction, "Fibonacci", hk, atr_series, sh, sl)
    entry, atr_val = _entry_atr(df, atr_series)
    stop, tp = _fibonacci_plan(entry, atr_val, float(sh.iloc[I]), float(sl.iloc[I]),
                               direction, hk)
    assert (stop, tp) == pytest.approx((ref_stop, ref_tp), abs=1e-9)


@pytest.mark.parametrize("ratio", [0.5, 1.0, 2.5, np.nan])
def test_sr_parity(df, atr_series, ratio):
    hk = "3m"
    vr = df["Close"] * 0 + ratio  # constant series
    ref_entry, ref_stop, ref_tp = backtest._trade_plan_at(
        df, I, "bullish", "Support/Resistance", hk, atr_series,
        volume_ratio_series=vr)
    entry, atr_val = _entry_atr(df, atr_series)
    stop, tp = _sr_plan(entry, ratio, "bullish", hk)
    assert (stop, tp) == pytest.approx((ref_stop, ref_tp), abs=1e-9)


@pytest.mark.parametrize("direction", ["bullish", "bearish"])
def test_elliott_parity(df, atr_series, direction):
    hk = "4w"
    wave2 = 95.0 if direction == "bullish" else 145.0
    entry_levels = {I: {"wave2": wave2}}
    ref_entry, ref_stop, ref_tp = backtest._trade_plan_at(
        df, I, direction, "Elliott Wave", hk, atr_series, entry_levels=entry_levels)
    entry, atr_val = _entry_atr(df, atr_series)
    stop, tp = _elliott_plan(entry, atr_val, wave2, direction, hk)
    assert (stop, tp) == pytest.approx((ref_stop, ref_tp), abs=1e-9)
