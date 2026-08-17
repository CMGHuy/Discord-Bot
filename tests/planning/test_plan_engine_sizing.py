"""Parity + golden tests for the sizing builders extracted from
backtest._trade_plan_at into plan_engine (Tasks 8-13)."""
import numpy as np
import pytest

from swingbot import config
from swingbot.core.backtesting import backtest
from swingbot.core.market.indicators import atr
from swingbot.core.planning.plan_engine import (
    STRUCTURE_BUFFER_ATR,
    _atr_plan,
    _elliott_plan,
    _fibonacci_plan,
    _safe_atr_value,
    _sr_plan,
    fib_target_candidates,
)
from swingbot.core.market.strategy_types import HORIZONS, STRATEGY_RR_OVERRIDE

from tests.helpers import make_ohlcv

I = 79  # reference bar


@pytest.fixture(autouse=True)
def _lifecycle_off(monkeypatch):
    """Pin the level-lifecycle flags OFF for this module.

    These are parity tests between `backtest._trade_plan_at` and the bare
    sizing builders it delegates to (`_atr_plan`, `_fibonacci_plan`, ...).
    The lifecycle deliberately POST-PROCESSES a builder's output --
    `_trade_plan_at` calls `apply_level_lifecycle` after sizing -- so with
    LEVEL_LIFECYCLE_STOPS_ENABLED default-on (2026-08-08) the two sides
    legitimately differ and the parity assertion stops meaning anything.

    Pinning the flag keeps these tests proving what they were written to
    prove: that the builders extracted out of `_trade_plan_at` are faithful.
    Agreement between the two plan paths WITH the lifecycle on is a different
    property, covered by tests/test_levels_lifecycle_wiring.py.
    """
    monkeypatch.setattr("swingbot.config.LEVEL_LIFECYCLE_STOPS_ENABLED", False,
                        raising=False)
    monkeypatch.setattr("swingbot.config.LEVEL_LIFECYCLE_TARGETS_ENABLED", False,
                        raising=False)


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
    # v31 Task 8: tp is no longer parity-matched against
    # backtest._trade_plan_at's old STRATEGY_RR_OVERRIDE/min_structure_rr
    # arithmetic (replaced by select_structural_target against real fib
    # levels). backtest._trade_plan_at itself is NOT yet updated (that's
    # Task 12) -- it still unconditionally unpacks _fibonacci_plan's return
    # as a 2-tuple, which now raises whenever the builder declines (returns
    # None), so it can no longer supply a live reference here. STOP is
    # verified against a hand-computed golden value using the same
    # buffer/max-risk-pct formula Task 8 keeps byte-for-byte -- same pattern
    # test_atr_plan_bullish_golden uses. tp is either None (no fib level
    # clears the floor) or within [MIN_RISK_REWARD_RATIO,
    # MAX_RISK_REWARD_RATIO] times risk -- the assertion that names the bug.
    hk = "4w"
    lookback = HORIZONS[hk]["fib_lookback"]
    sh = df["High"].rolling(lookback).max()
    sl = df["Low"].rolling(lookback).min()
    entry, atr_val = _entry_atr(df, atr_series)
    swing_high, swing_low = float(sh.iloc[I]), float(sl.iloc[I])
    is_bull = direction == "bullish"
    buffer = STRUCTURE_BUFFER_ATR * atr_val
    expected_stop = swing_low - buffer if is_bull else swing_high + buffer
    max_risk_amount = entry * (HORIZONS[hk]["max_risk_pct"] / 100)
    if abs(entry - expected_stop) > max_risk_amount:
        expected_stop = entry - max_risk_amount if is_bull else entry + max_risk_amount

    candidates = fib_target_candidates(df, I, HORIZONS[hk], entry)
    result = _fibonacci_plan(entry, atr_val, swing_high, swing_low,
                             direction, hk, candidate_levels=candidates)
    assert result is not None, "fixture must produce a qualifying fib target"
    stop, tp = result
    assert stop == pytest.approx(expected_stop, abs=1e-9)
    risk = abs(entry - stop)
    assert config.MIN_RISK_REWARD_RATIO * risk - 1e-6 <= abs(tp - entry) <= \
        config.MAX_RISK_REWARD_RATIO * risk + 1e-6


def test_fibonacci_targets_only_fibonacci_levels(df, atr_series):
    hk = "4w"
    direction = "bullish"
    entry, atr_val = _entry_atr(df, atr_series)
    lookback = HORIZONS[hk]["fib_lookback"]
    sh = df["High"].rolling(lookback).max()
    sl = df["Low"].rolling(lookback).min()
    candidates = fib_target_candidates(df, I, HORIZONS[hk], entry)
    result = _fibonacci_plan(entry, atr_val, float(sh.iloc[I]), float(sl.iloc[I]),
                             direction, hk, candidate_levels=candidates)
    assert result is not None, "fixture must produce a qualifying fib target"
    stop, tp = result
    risk = abs(entry - stop)
    cap = entry + risk * config.MAX_RISK_REWARD_RATIO
    assert any(abs(tp - c) < 1e-6 for c in candidates) or tp == pytest.approx(cap)


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
