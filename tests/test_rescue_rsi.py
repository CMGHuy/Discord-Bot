"""Task 95: RSI range-regime rescue gate (ADX + Bollinger). Fixture shapes
were REPL-tuned until the ungated function fires exactly once, then frozen:
the 'trend' frame fires with ADX ~56 (gate must suppress), the 'range'
frame fires with ADX ~19 inside the bands (gate must pass)."""
import numpy as np
import pytest

from swingbot.core.entry_filters import adx_series, rsi_entries
from tests.conftest import make_ohlcv

GATED = {"max_adx": 25, "require_bb_range": True}


def _trend_frame():
    """Strong steady uptrend, sharp-ish dip, V-bounce -> entry bar ADX ~56."""
    base = list(100 * 1.004 ** np.arange(420))
    top = base[-1]
    dip = [top * (1 - 0.009) ** (i + 1) for i in range(16)]
    bot = dip[-1]
    bounce = [bot * 1.012 ** (i + 1) for i in range(4)]
    return make_ohlcv(base + dip + bounce, spread_pct=1.0)


def _range_frame():
    """Bar-to-bar zigzag (directional movement cancels -> ADX ~19) with a
    slight up-drift for the 200-SMA slope gate, gentle dip, sharp bounce."""
    base = [100 + 0.03 * i + 0.8 * (-1) ** i for i in range(400)]
    top = base[-1]
    dip = [top - 0.5 * (i + 1) for i in range(16)]
    bot = dip[-1]
    bounce = [bot + 2.0 * (i + 1) for i in range(4)]
    return make_ohlcv(base + dip + bounce, spread_pct=3.0)


def test_adx_series_golden():
    # Expected value computed offline once with the textbook Wilder
    # formulation (EWM alpha=1/period) and hardcoded.
    df = make_ohlcv([100, 101, 103, 102, 104, 107, 106, 108, 111, 110,
                     112, 115, 114, 116, 119, 118, 120, 123, 122, 124],
                    spread_pct=2.0)
    assert adx_series(df).iloc[-1] == pytest.approx(83.209088, abs=1e-4)


def test_adx_regime_separation():
    trend_adx = adx_series(_trend_frame())
    range_adx = adx_series(_range_frame())
    assert trend_adx.iloc[-1] > 40          # sustained directional movement
    assert range_adx.iloc[-10:].max() < 25  # zigzag cancels out


def test_trending_frame_suppressed_when_gated():
    df = _trend_frame()
    bull_off, _ = rsi_entries(df, "4w")
    bull_on, _ = rsi_entries(df, "4w", params=GATED)
    assert bull_off.any(), "fixture must fire ungated (tune shape first)"
    assert not bull_on.any()


def test_range_frame_passes_gate():
    df = _range_frame()
    bull_off, _ = rsi_entries(df, "4w")
    bull_on, _ = rsi_entries(df, "4w", params=GATED)
    assert bull_off.any(), "fixture must fire ungated (tune shape first)"
    assert (bull_on == bull_off).all()      # low-ADX, in-band entry survives


def test_gate_off_is_byte_identical():
    df = _trend_frame()
    a, _ = rsi_entries(df, "4w")
    b, _ = rsi_entries(df, "4w",
                       params={"max_adx": None, "require_bb_range": False})
    assert (a == b).all()


def test_no_lookahead():
    df = _range_frame()
    full, _ = rsi_entries(df, "4w", params=GATED)
    trunc, _ = rsi_entries(df.iloc[:-1], "4w", params=GATED)
    assert (full.iloc[:-1] == trunc).all()
