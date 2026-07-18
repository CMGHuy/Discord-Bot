"""Task 98: RSI Divergence confirmation-quality gate.

The live detector is a ROLLING hidden-divergence formulation (no discrete
swing points), so reclaim strength is measured from the recent 20-bar swing
low toward the 20-bar range midpoint (close_frac ~0.758 on this fixture,
REPL-tuned and frozen). Volume ratio at the reclaim bar is 1.46 with
vol_mult=1.5 and 1.00 with vol_mult=1.0."""
import numpy as np

from swingbot.core.entry_filters import rsi_divergence_entries
from tests.conftest import make_ohlcv

OFF = {"min_volume_ratio": None, "min_reclaim_strength": None}


def _divergence_frame(vol_mult=1.5):
    """Uptrend -> momentum fade (price holds above the 50-SMA while RSI
    decays to a lower low) -> reclaim bar. Shape frozen from REPL tuning:
    the ungated function fires exactly on the last bar."""
    base = list(100 * 1.003 ** np.arange(300))
    top = base[-1]
    fade, lvl = [], top
    for i in range(20):
        lvl = lvl - 0.8 * (1 if i % 2 == 0 else -0.35) * top / 100
        fade.append(lvl)
    reclaim = fade[-1] + 1.6 * top / 100
    closes = base + fade + [reclaim]
    vols = [1_000_000.0] * (len(closes) - 1) + [1_000_000.0 * vol_mult]
    return make_ohlcv(closes, spread_pct=2.0, volumes=vols)


def test_fixture_fires_ungated():
    bull, _ = rsi_divergence_entries(_divergence_frame(), "4w", params=OFF)
    assert bull.iloc[-1]


def test_low_volume_reclaim_suppressed_when_gated():
    df = _divergence_frame(vol_mult=1.0)     # passes vol_ok (>=0.9) but not 1.2
    bull_off, _ = rsi_divergence_entries(df, "4w", params=OFF)
    bull_on, _ = rsi_divergence_entries(
        df, "4w", params={"min_volume_ratio": 1.2, "min_reclaim_strength": 0.5})
    assert bull_off.iloc[-1]
    assert not bull_on.iloc[-1]
    assert bull_on.sum() <= bull_off.sum()


def test_strong_volume_deep_reclaim_passes():
    df = _divergence_frame(vol_mult=1.5)     # ratio 1.46 >= 1.2, frac 0.758 >= 0.5
    bull_on, _ = rsi_divergence_entries(
        df, "4w", params={"min_volume_ratio": 1.2, "min_reclaim_strength": 0.5})
    bull_off, _ = rsi_divergence_entries(df, "4w", params=OFF)
    assert bull_on.iloc[-1] == bull_off.iloc[-1]


def test_shallow_reclaim_suppressed():
    df = _divergence_frame()                 # frac 0.758 < 0.9 -> rejected
    bull_on, _ = rsi_divergence_entries(
        df, "4w", params={"min_volume_ratio": None, "min_reclaim_strength": 0.9})
    assert not bull_on.iloc[-1]


def test_gate_off_is_byte_identical():
    df = _divergence_frame()
    a, _ = rsi_divergence_entries(df, "4w")
    b, _ = rsi_divergence_entries(df, "4w", params=OFF)
    assert (a == b).all()


def test_no_lookahead():
    df = _divergence_frame()
    params = {"min_volume_ratio": 1.2, "min_reclaim_strength": 0.5}
    full, _ = rsi_divergence_entries(df, "4w", params=params)
    trunc, _ = rsi_divergence_entries(df.iloc[:-1], "4w", params=params)
    assert (full.iloc[:-1] == trunc).all()
