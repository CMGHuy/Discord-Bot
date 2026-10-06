"""v125: entry_context carries plan provenance and location features."""
import numpy as np
import pytest

from swingbot import config
from swingbot.core.edge.context import FEATURE_KEYS, PROVENANCE_KEYS, entry_context, plan_provenance
from swingbot.core.market import structure as st
from swingbot.core.market.location import LOCATION_KEYS, location_features
from tests.conftest import make_ohlcv
from tests.market.structure_fixtures import BROKEN, MIXED, UP, frame, pullback_frame, slowing_pullback_frame, wavy_frame

V125_NEW = ("target_capped", "stop_clamped", "zone_dist_atr", "room_atr", "range_pos", "leg_phase",
            "zone_state", "zone_touches", "zone_departure_atr")

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


def test_feature_keys_append_the_nine_v125_keys_in_order():
    assert len(FEATURE_KEYS) == 43
    assert FEATURE_KEYS[34:] == V125_NEW
    assert FEATURE_KEYS[:34] == tuple(dict.fromkeys(FEATURE_KEYS[:34]))     # no key moved or duplicated
    assert set(LOCATION_KEYS) | set(PROVENANCE_KEYS) == set(V125_NEW)


@pytest.mark.parametrize("direction", ["bullish", "bearish"])
def test_snapshot_carries_location_features(direction):
    df = _wavy()
    out = _context(df, direction, entry=float(df["Close"].iloc[-1]))
    assert set(out) == set(FEATURE_KEYS)
    assert {key: out[key] for key in LOCATION_KEYS} == location_features(df, direction, "2w")
    assert out["zone_state"] == "tested" and out["leg_phase"] in ("broken", "impulse")


@pytest.mark.parametrize("direction", ["bullish", "bearish"])
def test_snapshot_provenance_reads_the_planned_entry_and_config_cap(direction, monkeypatch):
    monkeypatch.setattr(config, "MAX_RISK_REWARD_RATIO", 2.5)
    monkeypatch.setattr(config, "CLAMP_STOP_TO_HARD_CAP", True)
    df = _wavy()
    sign = 1 if direction == "bullish" else -1
    entry = 100.0
    out = entry_context(df, direction=direction, horizon_key="2w", stop=entry - sign * 1.75,
                        target=entry + sign * 1.75 * 2.5, asof=ASOF, entry=entry)
    assert (out["target_capped"], out["stop_clamped"]) == (True, True)
    assert {key: out[key] for key in PROVENANCE_KEYS} == plan_provenance(entry, entry - sign * 1.75,
                                                                           entry + sign * 4.375, 2.5)


def test_without_entry_both_flags_are_none():
    out = _context(_wavy(), "bullish")
    assert out["target_capped"] is None and out["stop_clamped"] is None
    assert out["zone_dist_atr"] is not None                  # location does not need the entry


@pytest.mark.parametrize("bars", [10, 40, 59])
def test_short_frames_leave_every_new_key_none(bars):
    out = _context(_wavy().iloc[:bars], "bullish")
    assert set(out) == set(FEATURE_KEYS)
    assert all(out[key] is None for key in V125_NEW)


def test_short_frame_with_an_entry_still_flags_the_plan(monkeypatch):
    """The flags are arithmetic on entry/stop/tp1 and read no bars."""
    monkeypatch.setattr(config, "CLAMP_STOP_TO_HARD_CAP", True)
    monkeypatch.setattr(config, "MAX_RISK_REWARD_RATIO", 2.5)
    out = entry_context(_wavy().iloc[:10], direction="bullish", horizon_key="2w",
                        stop=98.25, target=104.375, asof=None, entry=100.0)
    assert all(out[key] is None for key in LOCATION_KEYS)
    assert (out["target_capped"], out["stop_clamped"]) == (True, True)


def test_no_v125_key_duplicates_a_v121_key_on_the_fixtures():
    fixtures = [frame(UP), frame(MIXED), frame(BROKEN), pullback_frame(), slowing_pullback_frame(),
                wavy_frame(), _wavy()]
    for direction in ("bullish", "bearish"):
        rows = [(location_features(f, direction, "2w"), st.structure_features(f, direction)) for f in fixtures]
        for new in LOCATION_KEYS:
            for old in st.STRUCTURE_KEYS:
                assert not all(loc[new] == struct[old] for loc, struct in rows), (direction, new, old)


def test_live_stamp_passes_the_trigger_as_entry(monkeypatch):
    from swingbot.core.planning.params import stamp_entry_context
    from swingbot.core.planning.plan_types import PlanStatus, TradePlanV2
    monkeypatch.setattr(config, "MAX_RISK_REWARD_RATIO", 2.5)
    df = _wavy()
    plan = TradePlanV2(plan_id="p", ticker="AAPL", created_at="2026-10-02", source="confluence",
                       strategy="S/R Confluence", horizon_key="2w", direction="bullish",
                       entry_type="stop_entry", trigger_price=100.0, entry_price=None, expiry_bars=5,
                       stop_loss=98.0, tp1=105.0, tp1_fraction=0.5, tp2=None,
                       breakeven_trigger_fraction=0.5, trail_atr_mult=2.0, quality_score=0,
                       quality_breakdown=[], badge="WEAK", badge_stats={}, status=PlanStatus.PENDING)
    stamp_entry_context(plan, df, ASOF)
    assert set(plan.entry_context) == set(FEATURE_KEYS)
    assert plan.entry_context["target_capped"] is True        # 100 + 2.0 * 2.5 = 105, from the TRIGGER
    assert plan.entry_context["stop_clamped"] is False


def test_live_stamp_on_a_plan_without_a_trigger_keeps_the_snapshot():
    """Duck-typed plans (v121's stamp test uses a SimpleNamespace) must not blank the snapshot."""
    from types import SimpleNamespace

    from swingbot.core.planning.params import stamp_entry_context
    df = _wavy()
    close = float(df["Close"].iloc[-1])
    plan = SimpleNamespace(direction="bearish", horizon_key="2w", stop_loss=close + 6.0,
                           tp1=close - 12.0, entry_context=None)
    stamp_entry_context(plan, df, ASOF)
    assert set(plan.entry_context) == set(FEATURE_KEYS)
    assert plan.entry_context["target_capped"] is None
