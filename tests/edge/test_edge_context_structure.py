import pytest

from swingbot.core.edge.context import FEATURE_KEYS, entry_context
from swingbot.core.market.structure import STRUCTURE_KEYS, structure_features
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


def test_feature_keys_append_the_new_keys_in_order():
    assert FEATURE_KEYS[:20] == (
        "stop_atr", "stop_pct", "planned_rr", "swing_high_atr", "swing_low_atr", "horizon_key", "direction",
        "atr_pctile_250", "vol_ratio_20", "rsi_14", "adx_14", "bb_width_pctile_250", "htf_aligned",
        "gap_p90_pct", "gap_fragile", "dow", "regime2_state", "rs_pctile", "sector_pctile", "rs_combined")
    assert FEATURE_KEYS[20:] == STRUCTURE_NEW
    assert set(STRUCTURE_KEYS) <= set(FEATURE_KEYS)


@pytest.mark.parametrize("direction", ["bullish", "bearish"])
def test_snapshot_carries_structure_features(direction):
    df = wavy_frame()
    out = _context(df, direction)
    assert set(out) == set(FEATURE_KEYS)
    expected = structure_features(df, direction)
    assert {key: out[key] for key in STRUCTURE_KEYS} == expected
    assert out["swing_high_atr"] is not None and out["swing_low_atr"] is not None


@pytest.mark.parametrize("bars", [10, 40, 59])
def test_short_frames_leave_every_new_key_none(bars):
    out = _context(wavy_frame().iloc[:bars], "bullish")
    assert set(out) == set(FEATURE_KEYS)
    assert all(out[key] is None for key in STRUCTURE_NEW + FILLED_DEAD)


def test_live_stamp_carries_the_new_keys():
    from types import SimpleNamespace

    from swingbot.core.planning.params import stamp_entry_context
    df = wavy_frame()
    close = float(df["Close"].iloc[-1])
    plan = SimpleNamespace(direction="bearish", horizon_key="2w", stop_loss=close + 6.0,
                           tp1=close - 12.0, entry_context=None)
    stamp_entry_context(plan, df, ASOF)
    assert plan.entry_context["structure_state"] == structure_features(df, "bearish")["structure_state"]
    assert set(plan.entry_context) == set(FEATURE_KEYS)
