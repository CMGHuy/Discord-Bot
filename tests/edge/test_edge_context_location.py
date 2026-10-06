"""v125: entry_context carries plan provenance and location features."""
import numpy as np
import pytest

from swingbot.core.edge.context import entry_context
from tests.conftest import make_ohlcv

ASOF = {"regime2_state": "bull_quiet", "rs_pctile": 64.0, "sector_pctile": None, "rs_combined": 61.0}
_COMMON = {
    "stop_atr": 3.389932, "stop_pct": 5.588532, "planned_rr": 2.0, "swing_high_atr": 3.127987,
    "swing_low_atr": -2.005931, "horizon_key": "2w", "atr_pctile_250": 36.0, "vol_ratio_20": 1.115516,
    "rsi_14": 19.789007, "adx_14": 42.545477, "bb_width_pctile_250": None, "gap_p90_pct": 0.0,
    "gap_fragile": False, "dow": 0, "regime2_state": "bull_quiet", "rs_pctile": 64.0, "sector_pctile": None,
    "rs_combined": 61.0, "structure_state": "down", "vol_trend_10_50": 1.086677, "range_trend_10_50": 0.914935,
    "absorption_bar": False, "absorption_count_10": 0, "impulse_range_decay": None,
}
WITNESS = {
    "bullish": {**_COMMON, "direction": "bullish", "htf_aligned": False, "structure_aligned": False,
                "last_pivot_held": False, "hh_failed": True, "progress_atr_10": -2.531944,
                "pullback_vol_ratio": 1.197042, "pullback_depth_frac": 3.19318,
                "pullback_bars_ratio": 2.666667, "impulse_atr_per_bar": 0.374019},
    "bearish": {**_COMMON, "direction": "bearish", "htf_aligned": True, "structure_aligned": True,
                "last_pivot_held": True, "hh_failed": False, "progress_atr_10": 2.531944,
                "pullback_vol_ratio": None, "pullback_depth_frac": None,
                "pullback_bars_ratio": None, "impulse_atr_per_bar": None},
}


def _wavy(n=300):
    i = np.arange(n)
    closes = 100 + 0.05 * i + 6 * np.sin(i / 7.0) + 2 * np.sin(i / 2.3)
    return make_ohlcv(closes, spread_pct=1.5, volumes=1_000_000 + 300_000 * np.sin(i / 3.1) + 5_000 * i)


def _context(df, direction, **kwargs):
    close = float(df["Close"].iloc[-1])
    sign = 1 if direction == "bullish" else -1
    return entry_context(df, direction=direction, horizon_key="2w",
                         stop=close - sign * 6.0, target=close + sign * 12.0, asof=ASOF, **kwargs)


@pytest.mark.parametrize("direction", ["bullish", "bearish"])
def test_pre_existing_keys_are_unchanged(direction):
    out = _context(_wavy(), direction)
    assert {key: out[key] for key in WITNESS[direction]} == WITNESS[direction]
    assert len(WITNESS[direction]) == 34
