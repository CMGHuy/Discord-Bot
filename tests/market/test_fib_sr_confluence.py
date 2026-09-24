"""v102: Fibonacci x Rolling S/R confluence filter."""
import numpy as np
import pandas as pd
import pytest

from swingbot import config
from swingbot.core.market import entry_filters as ef
from swingbot.core.market.strategy_types import HORIZONS
from tests.helpers import make_ohlcv


def _frame(n=300):
    rng = np.random.default_rng(7)
    closes = 100 + np.cumsum(rng.normal(0, 1, n))
    return make_ohlcv(list(closes), start="2015-01-02")


def _trending_frame(n, drift, seed, amp=3.0, period=18):
    """A trend + oscillation frame that actually fires Fibonacci pullback/bounce
    signals (an undrifted random walk from _frame() never does): seed=2/drift
    up fires bullish, seed=11/drift down fires bearish -- found by search, not
    hand-tuned indicator math."""
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    closes = 100 + drift * t + amp * np.sin(2 * np.pi * t / period) + rng.normal(0, 0.3, n)
    return make_ohlcv(list(closes), start="2015-01-02")


def _bull_signal_frame():
    return _trending_frame(400, 0.06, seed=2)


def _bear_signal_frame():
    return _trending_frame(400, -0.06, seed=11)


def _reference_no_confluence(df, horizon_key):
    """A standalone re-implementation of fibonacci_entries' pre-v102 body (no
    confluence term), so the bit-identity tests below check the current
    flag-off output against an independent formula, not against another
    invocation of the same (already-patched) function."""
    from swingbot.core.market.entry_filters import (
        FIB_TOLERANCE_PCT, _params, _rolling_argmax_pos, _rolling_argmin_pos,
    )
    p = _params("Fibonacci", None)
    h = HORIZONS[horizon_key]
    lookback = h["fib_lookback"]
    g = ef.compute_shared_gates(df)
    close, high, low = df["Close"], df["High"], df["Low"]

    swing_high = high.rolling(lookback).max()
    swing_low = low.rolling(lookback).min()
    rng = swing_high - swing_low

    hi_pos = _rolling_argmax_pos(high, lookback)
    lo_pos = _rolling_argmin_pos(low, lookback)
    up_impulse = (hi_pos > lo_pos)
    down_impulse = (lo_pos > hi_pos)

    levels = pd.DataFrame({r: swing_high - r * rng for r in p["ratios"]})
    nearest_distance = levels.sub(close, axis=0).abs().min(axis=1)
    distance_pct = (nearest_distance / rng * 100).replace([np.inf, -np.inf], np.nan)
    is_testing = (distance_pct <= FIB_TOLERANCE_PCT) & rng.gt(0)

    pulled_back_bull = close.shift(5) > close.shift(1)
    bouncing_bull = close > close.shift(1)
    pulled_back_bear = close.shift(5) < close.shift(1)
    bouncing_bear = close < close.shift(1)
    upper_half = close >= (high + low) / 2
    lower_half = close <= (high + low) / 2

    rsi14 = g["rsi14"]
    bullish = (is_testing & up_impulse & pulled_back_bull & bouncing_bull & upper_half
               & g["bull_regime"] & g["trend50_bull"]
               & rsi14.between(*p["rsi_bull"])
               & g["atr_floor"] & g["atr_calm"] & g["vol_ok"]).fillna(False)
    bearish = (is_testing & down_impulse & pulled_back_bear & bouncing_bear & lower_half
               & g["bear_regime"] & g["trend50_bear"]
               & rsi14.between(*p["rsi_bear"])
               & g["atr_floor"] & g["atr_calm"] & g["vol_ok"]).fillna(False)
    return bullish, bearish


def _inputs(df, horizon="4w"):
    h = HORIZONS[horizon]
    lb = h["fib_lookback"]
    swing_high, swing_low = df["High"].rolling(lb).max(), df["Low"].rolling(lb).min()
    rng = swing_high - swing_low
    levels = pd.DataFrame({r: swing_high - r * rng for r in (0.382, 0.5, 0.618)})
    atr14 = ef.compute_shared_gates(df)["atr14"]
    return h, levels, df["Close"], atr14


def test_flag_zero_keeps_every_bar(monkeypatch):
    monkeypatch.setattr(config, "FIB_SR_CONFLUENCE_ATR", 0.0, raising=False)
    df = _frame()
    out = ef._fib_sr_confluence(df, *_inputs(df))
    assert out.all()


def test_flag_zero_leaves_fibonacci_entries_bit_identical(monkeypatch):
    """Flag-off output must match an independent (non-confluence) formula on
    frames that actually fire signals in each direction -- not merely equal
    itself across two calls, which would hold even if both were broken."""
    df_bull, df_bear = _bull_signal_frame(), _bear_signal_frame()
    monkeypatch.setattr(config, "FIB_SR_CONFLUENCE_ATR", 0.0, raising=False)
    bull0, _ = ef.fibonacci_entries(df_bull, "4w")
    _, bear0 = ef.fibonacci_entries(df_bear, "4w")
    assert bull0.any() and bear0.any(), "test frames must actually fire signals"
    ref_bull, _ = _reference_no_confluence(df_bull, "4w")
    _, ref_bear = _reference_no_confluence(df_bear, "4w")
    pd.testing.assert_series_equal(bull0, ref_bull)
    pd.testing.assert_series_equal(bear0, ref_bear)

    monkeypatch.delattr(config, "FIB_SR_CONFLUENCE_ATR", raising=False)
    bull1, _ = ef.fibonacci_entries(df_bull, "4w")     # attribute absent -> treated as 0
    _, bear1 = ef.fibonacci_entries(df_bear, "4w")
    pd.testing.assert_series_equal(bull0, bull1)
    pd.testing.assert_series_equal(bear0, bear1)


def test_keeps_within_tolerance_and_drops_just_outside(monkeypatch):
    df = _frame()
    h, levels, close, atr14 = _inputs(df)
    i = 250
    lb = h["sr_lookback"]
    support = float(df["Low"].rolling(lb).min().shift(1).iloc[i])
    resistance = float(df["High"].rolling(lb).max().shift(1).iloc[i])
    arr = levels.iloc[i].to_numpy()
    tested = arr[np.argmin(np.abs(arr - close.iloc[i]))]
    gap = min(abs(tested - support), abs(tested - resistance))
    assert gap > 0, "pick another bar: a zero gap makes the 'just outside' tolerance non-positive"
    tol_hit = gap / float(atr14.iloc[i]) + 1e-9
    monkeypatch.setattr(config, "FIB_SR_CONFLUENCE_ATR", tol_hit, raising=False)
    assert bool(ef._fib_sr_confluence(df, h, levels, close, atr14).iloc[i]) is True
    monkeypatch.setattr(config, "FIB_SR_CONFLUENCE_ATR", tol_hit * 0.999 - 1e-9, raising=False)
    assert bool(ef._fib_sr_confluence(df, h, levels, close, atr14).iloc[i]) is False


def test_filter_only_removes_signals(monkeypatch):
    df_bull, df_bear = _bull_signal_frame(), _bear_signal_frame()
    monkeypatch.setattr(config, "FIB_SR_CONFLUENCE_ATR", 0.0, raising=False)
    bull0, _ = ef.fibonacci_entries(df_bull, "4w")
    _, bear0 = ef.fibonacci_entries(df_bear, "4w")
    assert bull0.any() and bear0.any(), "test frames must actually fire signals"
    monkeypatch.setattr(config, "FIB_SR_CONFLUENCE_ATR", 0.5, raising=False)
    bull1, _ = ef.fibonacci_entries(df_bull, "4w")
    _, bear1 = ef.fibonacci_entries(df_bear, "4w")
    assert not (bull1 & ~bull0).any() and not (bear1 & ~bear0).any()


def test_no_lookahead(monkeypatch):
    monkeypatch.setattr(config, "FIB_SR_CONFLUENCE_ATR", 0.75, raising=False)
    df = _frame()
    i = 250
    base = ef._fib_sr_confluence(df, *_inputs(df))
    poisoned = df.copy()
    poisoned.iloc[i + 1:, :4] = poisoned.iloc[i + 1:, :4] * 5
    again = ef._fib_sr_confluence(poisoned, *_inputs(poisoned))
    pd.testing.assert_series_equal(base.iloc[:i + 1], again.iloc[:i + 1])


def test_nan_warmup_bars_are_dropped_not_raised(monkeypatch):
    monkeypatch.setattr(config, "FIB_SR_CONFLUENCE_ATR", 1.0, raising=False)
    df = _frame(60)                       # shorter than fib_lookback + sr_lookback warm-up
    out = ef._fib_sr_confluence(df, *_inputs(df))
    assert out.dtype == bool and not out.iloc[:30].any()
