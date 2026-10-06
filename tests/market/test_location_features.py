# tests/market/test_location_features.py
"""v125: location, leg-phase and zone-quality features (market/location.py)."""
import numpy as np
import pytest

from swingbot.core.market import levels
from swingbot.core.market import location as lo
from swingbot.core.market import structure as st
from swingbot.core.market.indicators import atr
from swingbot.core.market.levels_lifecycle import classify_levels
from tests.conftest import make_ohlcv
from tests.market.structure_fixtures import BROKEN, UP, frame, wavy_frame

IMPULSE = UP + [135]            # closes through the last confirmed SH (130) without forming a new pivot


def _atr14(df):
    return float(atr(df, 14).iloc[-1])


def _mock_levels(monkeypatch, below=(), above=()):
    """Pin build_level_map so zone answers are exact. Nearest-first, like the real one."""
    supports = [levels.Level(p, ["test"]) for p in sorted(below, reverse=True)]
    resistances = [levels.Level(p, ["test"]) for p in sorted(above)]
    monkeypatch.setattr(lo, "build_level_map", lambda df, h, price: (supports, resistances))


def _departure_frame(after, before=60, level=100.0):
    """`before` flat bars ON the level (High == Low == Close), then the `after` closes."""
    return make_ohlcv(np.r_[np.full(before, level), np.asarray(after, dtype=float)], spread_pct=0.0)


# --- range_pos / leg_phase (latest confirmed swing range) --------------------

def test_mid_range_close_is_about_half():
    # last SH 130 (High 130.65), last SL 124 (Low 123.38), close 127
    out = lo.location_features(frame(UP), "bullish", "2w")
    assert out["range_pos"] == round(3.62 / 7.27, 6)
    assert out["leg_phase"] == "pullback"


def test_bearish_mid_range_mirror():
    # mirrored: last SH 126 (High 126.63), last SL 120 (Low 119.4), close 123
    out = lo.location_features(frame(UP, mirror=True), "bearish", "2w")
    assert out["range_pos"] == round(3.63 / 7.23, 6)
    assert out["leg_phase"] == "pullback"


@pytest.mark.parametrize("mirror,direction", [(False, "bullish"), (True, "bearish")])
def test_close_beyond_the_last_swing_high_is_impulse(mirror, direction):
    out = lo.location_features(frame(IMPULSE, mirror=mirror), direction, "2w")
    assert out["leg_phase"] == "impulse"
    assert out["range_pos"] > 1.0                  # not clipped


@pytest.mark.parametrize("mirror,direction", [(False, "bullish"), (True, "bearish")])
def test_close_through_the_last_swing_low_is_broken(mirror, direction):
    out = lo.location_features(frame(BROKEN, mirror=mirror), direction, "2w")
    assert out["leg_phase"] == "broken"
    assert out["range_pos"] < 0.0                  # not clipped


def test_counter_direction_reads_the_same_range_from_the_other_side():
    df = frame(UP)
    bull, bear = lo.swing_location(df, "bullish"), lo.swing_location(df, "bearish")
    assert bull["range_pos"] + bear["range_pos"] == pytest.approx(1.0, abs=1e-6)
    assert bear["leg_phase"] == "pullback"


@pytest.mark.parametrize("direction", ["bullish", "bearish"])
def test_swing_location_matches_the_full_frame_pivots_on_every_cut(direction):
    df = wavy_frame()
    full = st.confirmed_pivots(df)
    for t in range(lo.MIN_BARS, len(df)):
        got = lo.swing_location(df.iloc[:t + 1], direction)
        sh, sl = full["last_sh"].iloc[t], full["last_sl"].iloc[t]
        close = float(df["Close"].iloc[t])
        if np.isnan(sh) or np.isnan(sl):
            assert got == {"range_pos": None, "leg_phase": None}, t
            continue
        raw = (close - sl) / (sh - sl) if direction == "bullish" else (sh - close) / (sh - sl)
        assert got["range_pos"] == (round(raw, 6) if sh > sl else None), t


def test_no_confirmed_swing_gives_none():
    df = make_ohlcv(np.linspace(100, 160, 80), spread_pct=1.0)       # straight line: no pivot at all
    assert lo.swing_location(df, "bullish") == {"range_pos": None, "leg_phase": None}


# --- zone_dist_atr / room_atr / zone_state / zone_touches --------------------

def test_price_sitting_on_a_support(monkeypatch):
    df = frame(UP)
    close, a = float(df["Close"].iloc[-1]), _atr14(df)
    _mock_levels(monkeypatch, below=[close - 0.1 * a, close - 4 * a], above=[close + 2 * a])
    out = lo.location_features(df, "bullish", "2w")
    assert out["zone_dist_atr"] == pytest.approx(0.1, abs=1e-6)
    assert out["room_atr"] == pytest.approx(2.0, abs=1e-6)


def test_bearish_zone_is_the_nearest_resistance(monkeypatch):
    df = frame(UP, mirror=True)
    close, a = float(df["Close"].iloc[-1]), _atr14(df)
    _mock_levels(monkeypatch, below=[close - 2 * a], above=[close + 0.1 * a, close + 5 * a])
    out = lo.location_features(df, "bearish", "2w")
    assert out["zone_dist_atr"] == pytest.approx(0.1, abs=1e-6)
    assert out["room_atr"] == pytest.approx(2.0, abs=1e-6)


def test_no_level_on_a_side_gives_none_for_that_side_only(monkeypatch):
    df = frame(UP)
    _mock_levels(monkeypatch, below=[], above=[float(df["Close"].iloc[-1]) + 1.0])
    out = lo.location_features(df, "bullish", "2w")
    assert out["zone_dist_atr"] is None and out["zone_state"] is None
    assert out["zone_touches"] is None and out["zone_departure_atr"] is None
    assert out["room_atr"] is not None and out["range_pos"] is not None


def test_an_untouched_support_is_fresh(monkeypatch):
    _mock_levels(monkeypatch, below=[60.0])
    out = lo.location_features(frame(UP), "bullish", "2w")
    assert (out["zone_state"], out["zone_touches"], out["zone_departure_atr"]) == ("fresh", 0, None)


def test_a_retested_swing_low_is_tested_and_counted(monkeypatch):
    df = frame(UP)
    level = float(df["Low"].iloc[80])          # the 124 trough's Low, 123.38; last touched at bar 80
    _mock_levels(monkeypatch, below=[level])
    out = lo.location_features(df, "bullish", "2w")
    state = classify_levels(df, len(df) - 1, [level], horizon_key="2w")[0]
    assert (out["zone_state"], out["zone_touches"]) == ("tested", state.touches)
    assert out["zone_touches"] == 5
    # best close in bars 81..88 is the entry close 127: (127 - 123.38) / ATR14
    assert out["zone_departure_atr"] == pytest.approx(3.62 / _atr14(df), abs=1e-6)


def test_real_level_map_is_built_on_the_frame_given():
    df = wavy_frame()
    close, a = float(df["Close"].iloc[-1]), _atr14(df)
    supports, resistances = levels.build_level_map(df, lo.HORIZONS["2w"], close)
    bull = lo.location_features(df, "bullish", "2w")
    bear = lo.location_features(df, "bearish", "2w")
    assert bull["zone_dist_atr"] == pytest.approx((close - supports[0].price) / a, abs=1e-6)
    assert bull["room_atr"] == pytest.approx((resistances[0].price - close) / a, abs=1e-6)
    assert (bear["zone_dist_atr"], bear["room_atr"]) == (bull["room_atr"], bull["zone_dist_atr"])


# --- zone_departure_atr ------------------------------------------------------

def test_touch_then_a_three_atr_close_away():
    df = _departure_frame([100.5, 101.5, 103.0, 102.0, 101.0])
    assert lo.zone_departure_atr(df, len(df) - 1, 100.0, "bullish", 1.0) == 3.0


def test_bearish_departure_mirror():
    df = _departure_frame([99.5, 98.5, 97.0, 98.0, 99.0])
    assert lo.zone_departure_atr(df, len(df) - 1, 100.0, "bearish", 1.0) == 3.0


def test_departure_window_is_capped_at_t_and_reads_nothing_after_it():
    df = _departure_frame([100.5, 101.5, 103.0, 102.0, 101.0])
    poisoned = df.copy()
    poisoned.iloc[62:, :4] = 1_000.0
    assert lo.zone_departure_atr(df, 61, 100.0, "bullish", 1.0) == 1.5
    assert lo.zone_departure_atr(poisoned, 61, 100.0, "bullish", 1.0) == 1.5
    assert lo.zone_departure_atr(df.iloc[:62], 61, 100.0, "bullish", 1.0) == 1.5


def test_departure_counts_only_ten_bars_after_the_touch():
    df = _departure_frame(100.0 + np.arange(1, 13))        # closes 101 .. 112; last touch is bar 59
    assert lo.zone_departure_atr(df, len(df) - 1, 100.0, "bullish", 1.0) == 10.0


def test_a_touch_on_the_entry_bar_itself_is_not_the_last_touch():
    df = _departure_frame([103.0, 104.0, 100.0])           # bar t = 62 sits on the level
    assert lo.zone_departure_atr(df, 62, 100.0, "bullish", 1.0) == 4.0


def test_departure_is_signed_when_price_fell_through():
    df = _departure_frame([99.8, 99.0, 98.0])              # bar 60 still touches (tol 0.25)
    assert lo.zone_departure_atr(df, 62, 100.0, "bullish", 1.0) == -1.0


def test_no_touch_no_level_or_no_atr_gives_none():
    df = _departure_frame([100.5, 101.5, 103.0])
    assert lo.zone_departure_atr(df, 62, 50.0, "bullish", 1.0) is None
    assert lo.zone_departure_atr(df, 62, None, "bullish", 1.0) is None
    assert lo.zone_departure_atr(df, 62, 100.0, "bullish", 0.0) is None


def test_departure_is_truncation_stable_on_every_cut():
    df = wavy_frame()
    for t in range(1, len(df)):
        poisoned = df.copy()
        poisoned.iloc[t + 1:, :4] = 1_000.0
        expected = lo.zone_departure_atr(df.iloc[:t + 1], t, 104.0, "bullish", 1.0)
        assert lo.zone_departure_atr(df, t, 104.0, "bullish", 1.0) == expected, t
        assert lo.zone_departure_atr(poisoned, t, 104.0, "bullish", 1.0) == expected, t


# --- degenerate frames -------------------------------------------------------

def test_short_frame_returns_all_none():
    out = lo.location_features(frame(UP).iloc[:59], "bullish", "2w")
    assert set(out) == set(lo.LOCATION_KEYS)
    assert all(value is None for value in out.values())
    assert lo.location_features(frame(UP).iloc[:60], "bullish", "2w")["zone_dist_atr"] is not None


def test_flat_prices_have_no_atr_and_return_all_none():
    out = lo.location_features(make_ohlcv(np.full(80, 100.0), spread_pct=0.0), "bullish", "2w")
    assert all(value is None for value in out.values())


def test_nan_bars_do_not_raise():
    df = frame(UP).copy()
    df.iloc[40:42, df.columns.get_loc("High")] = np.nan
    df.iloc[50, df.columns.get_loc("Close")] = np.nan
    out = lo.location_features(df, "bullish", "2w")
    assert set(out) == set(lo.LOCATION_KEYS)


def test_unknown_horizon_leaves_level_keys_none_and_does_not_raise():
    out = lo.location_features(frame(UP), "bullish", "no-such-horizon")
    assert out["zone_dist_atr"] is None and out["room_atr"] is None and out["zone_state"] is None
    assert out["leg_phase"] == "pullback"


def test_keys_are_disjoint_from_v121_structure_keys():
    assert not set(lo.LOCATION_KEYS) & set(st.STRUCTURE_KEYS)
