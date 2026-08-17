"""Parity + golden tests for the sizing builders extracted from
backtest._trade_plan_at into plan_engine (Tasks 8-13)."""
import numpy as np
import pytest

from swingbot import config
from swingbot.core.market.indicators import atr
from swingbot.core.planning.plan_engine import (
    STRUCTURE_BUFFER_ATR,
    _atr_plan,
    _elliott_plan,
    _fibonacci_plan,
    _safe_atr_value,
    _sr_plan,
    atr_target_candidates,
    elliott_target_candidates,
    fib_target_candidates,
    sr_target_candidates,
)
from swingbot.core.market.strategy_types import HORIZONS

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


# --- golden asserts (Task 11) -------------------------------------------------

ATR_FALLBACK_STRATEGIES = (
    "EMA Crossover", "VWAP", "RSI", "MACD", "MA Ribbon",
    "Break & Retest", "RSI Divergence", "Volume Profile",
)


def test_atr_plan_stop_is_atr_multiple_capped_by_max_risk_pct():
    # Stop derivation is untouched by v31 -- same golden value as before.
    close, atr_val, h = 100.0, 2.0, "4w"
    mult = HORIZONS[h]["atr_stop_multiple"]
    exp_risk = min(mult * atr_val, close * HORIZONS[h]["max_risk_pct"] / 100)
    candidates = atr_target_candidates(close, atr_val, "bullish")
    result = _atr_plan(close, atr_val, "bullish", h, "MACD", candidate_levels=candidates)
    assert result is not None
    stop, tp = result
    assert stop == pytest.approx(close - exp_risk)


def test_atr_plan_bearish_mirror():
    candidates = atr_target_candidates(100.0, 2.0, "bearish")
    result = _atr_plan(100.0, 2.0, "bearish", "4w", "MACD", candidate_levels=candidates)
    assert result is not None
    stop, tp = result
    assert stop > 100.0 and tp < 100.0


@pytest.mark.parametrize("direction", ["bullish", "bearish"])
@pytest.mark.parametrize("strategy", ATR_FALLBACK_STRATEGIES)
@pytest.mark.parametrize("horizon_key", ["2w", "4w", "3m"])
def test_atr_plan_target_is_an_atr_band_at_or_past_the_floor(horizon_key, strategy, direction):
    entry, atr_val = 100.0, 2.0
    candidates = atr_target_candidates(entry, atr_val, direction)
    result = _atr_plan(entry, atr_val, direction, horizon_key, strategy,
                       candidate_levels=candidates)
    assert result is not None, f"{strategy}/{horizon_key}/{direction} must qualify"
    stop, tp = result
    risk = abs(entry - stop)
    reward = abs(tp - entry)
    assert 1.5 - 1e-9 <= reward / risk <= 2.5 + 1e-9
    cap = entry + risk * config.MAX_RISK_REWARD_RATIO if direction == "bullish" \
        else entry - risk * config.MAX_RISK_REWARD_RATIO
    assert any(abs(tp - c) < 1e-6 for c in candidates) or tp == pytest.approx(cap)


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
    # v31 Task 10: same pattern as Tasks 8-9 -- tp is no longer
    # parity-matched against backtest._trade_plan_at's old volume-strength
    # arithmetic (backtest.py doesn't thread candidate_levels yet; Task 12).
    # STOP is unchanged (doesn't depend on volume_ratio at all) so it's
    # checked against the same fixed-percent formula directly; tp against
    # the RR band.
    hk = "3m"
    h = HORIZONS[hk]
    entry, atr_val = _entry_atr(df, atr_series)
    expected_stop = entry * (1 - h["sr_stop_pct"] / 100)

    candidates = sr_target_candidates(df, I, h, entry, ratio)
    result = _sr_plan(entry, ratio, "bullish", hk, candidate_levels=candidates)
    assert result is not None, "fixture must produce a qualifying S/R target"
    stop, tp = result
    assert stop == pytest.approx(expected_stop, abs=1e-9)
    risk = abs(entry - stop)
    assert config.MIN_RISK_REWARD_RATIO * risk - 1e-6 <= abs(tp - entry) <= \
        config.MAX_RISK_REWARD_RATIO * risk + 1e-6


def test_sr_target_is_structure_or_band_never_a_risk_multiple(df, atr_series):
    hk = "3m"
    h = HORIZONS[hk]
    entry, atr_val = _entry_atr(df, atr_series)
    for ratio in (0.5, 1.0, 2.5, np.nan):
        candidates = sr_target_candidates(df, I, h, entry, ratio)
        result = _sr_plan(entry, ratio, "bullish", hk, candidate_levels=candidates)
        assert result is not None, f"fixture must qualify for ratio={ratio}"
        stop, tp = result
        risk = abs(entry - stop)
        cap = entry + risk * config.MAX_RISK_REWARD_RATIO
        assert any(abs(tp - c) < 1e-6 for c in candidates) or tp == pytest.approx(cap)


@pytest.mark.parametrize("direction", ["bullish", "bearish"])
def test_elliott_parity(df, atr_series, direction):
    # v31 Task 9: same pattern as test_fibonacci_parity -- tp is no longer
    # parity-matched against backtest._trade_plan_at's old R:R-override
    # arithmetic (backtest.py only extracts entry_levels[i]["wave2"] today
    # and doesn't thread candidate_levels; that's Task 12). STOP is checked
    # against a hand-computed golden value; tp against the RR band.
    hk = "4w"
    is_bull = direction == "bullish"
    entry, atr_val = _entry_atr(df, atr_series)
    # Waves positioned relative to the real fixture entry (not fixed
    # absolutes) so the projections land meaningfully beyond entry on the
    # trade-direction side regardless of the fixture's price scale.
    if is_bull:
        wave1, wave0, wave2 = entry + 5.0, entry - 20.0, entry - 5.0
    else:
        wave1, wave0, wave2 = entry - 5.0, entry + 20.0, entry + 5.0
    entry_level = {"wave0": wave0, "wave1": wave1, "wave2": wave2}
    buffer = STRUCTURE_BUFFER_ATR * atr_val
    expected_stop = wave2 - buffer if is_bull else wave2 + buffer
    max_risk_amount = entry * (HORIZONS[hk]["max_risk_pct"] / 100)
    if abs(entry - expected_stop) > max_risk_amount:
        expected_stop = entry - max_risk_amount if is_bull else entry + max_risk_amount

    candidates = elliott_target_candidates(entry_level, direction)
    result = _elliott_plan(entry, atr_val, wave2, direction, hk, candidate_levels=candidates)
    assert result is not None, "fixture must produce a qualifying wave-3 target"
    stop, tp = result
    assert stop == pytest.approx(expected_stop, abs=1e-9)
    risk = abs(entry - stop)
    assert config.MIN_RISK_REWARD_RATIO * risk - 1e-6 <= abs(tp - entry) <= \
        config.MAX_RISK_REWARD_RATIO * risk + 1e-6


def test_elliott_targets_wave_projections(df, atr_series):
    hk = "4w"
    entry, atr_val = _entry_atr(df, atr_series)
    for direction, wave1, wave0, wave2 in (
        ("bullish", entry + 5.0, entry - 20.0, entry - 5.0),
        ("bearish", entry - 5.0, entry + 20.0, entry + 5.0),
    ):
        entry_level = {"wave0": wave0, "wave1": wave1, "wave2": wave2}
        candidates = elliott_target_candidates(entry_level, direction)
        result = _elliott_plan(entry, atr_val, wave2, direction, hk, candidate_levels=candidates)
        assert result is not None, f"fixture must qualify for {direction}"
        stop, tp = result
        risk = abs(entry - stop)
        cap = entry + risk * config.MAX_RISK_REWARD_RATIO if direction == "bullish" \
            else entry - risk * config.MAX_RISK_REWARD_RATIO
        assert any(abs(tp - c) < 1e-6 for c in candidates) or tp == pytest.approx(cap)
