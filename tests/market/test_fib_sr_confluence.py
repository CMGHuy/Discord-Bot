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
    df = _frame()
    monkeypatch.setattr(config, "FIB_SR_CONFLUENCE_ATR", 0.0, raising=False)
    bull0, bear0 = ef.fibonacci_entries(df, "4w")
    monkeypatch.delattr(config, "FIB_SR_CONFLUENCE_ATR", raising=False)
    bull1, bear1 = ef.fibonacci_entries(df, "4w")      # attribute absent -> treated as 0
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
    df = _frame(600)
    monkeypatch.setattr(config, "FIB_SR_CONFLUENCE_ATR", 0.0, raising=False)
    bull0, bear0 = ef.fibonacci_entries(df, "4w")
    monkeypatch.setattr(config, "FIB_SR_CONFLUENCE_ATR", 0.5, raising=False)
    bull1, bear1 = ef.fibonacci_entries(df, "4w")
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
