import pytest

from swingbot.core.edge.context import FEATURE_KEYS, entry_context
from tests.market.structure_fixtures import wavy_frame

STRUCTURE_NEW = ("structure_state", "structure_aligned", "last_pivot_held", "hh_failed",
                 "vol_trend_10_50", "range_trend_10_50", "progress_atr_10", "absorption_bar",
                 "absorption_count_10", "pullback_vol_ratio", "pullback_depth_frac", "pullback_bars_ratio",
                 "impulse_atr_per_bar", "impulse_range_decay")
FILLED_DEAD = ("swing_high_atr", "swing_low_atr")
ASOF = {"regime2_state": "bull_quiet", "rs_pctile": 64.0, "sector_pctile": None, "rs_combined": 61.0}
WITNESS = {
    "stop_atr": 3.389932, "stop_pct": 5.588532, "planned_rr": 2.0, "horizon_key": "2w",
    "atr_pctile_250": 36.0, "vol_ratio_20": 1.115516, "rsi_14": 19.789007, "adx_14": 42.545477,
    "bb_width_pctile_250": None, "gap_p90_pct": 0.0, "gap_fragile": False, "dow": 0,
    "regime2_state": "bull_quiet", "rs_pctile": 64.0, "sector_pctile": None, "rs_combined": 61.0,
}


def _context(df, direction):
    close = float(df["Close"].iloc[-1])
    sign = 1 if direction == "bullish" else -1
    return entry_context(df, direction=direction, horizon_key="2w",
                         stop=close - sign * 6.0, target=close + sign * 12.0, asof=ASOF)


@pytest.mark.parametrize("direction,htf_aligned", [("bullish", False), ("bearish", True)])
def test_pre_existing_keys_are_unchanged(direction, htf_aligned):
    out = _context(wavy_frame(), direction)
    kept = {key: out[key] for key in WITNESS}
    assert kept == WITNESS
    assert (out["direction"], out["htf_aligned"]) == (direction, htf_aligned)
