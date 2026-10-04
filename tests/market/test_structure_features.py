# tests/market/test_structure_features.py
import numpy as np
import pytest

from swingbot.core.market import structure as st
from swingbot.core.market.indicators import atr
from tests.conftest import make_ohlcv
from tests.market.structure_fixtures import (BROKEN, MIXED, UP, frame, pullback_frame, short_impulse_frame,
                                               slowing_pullback_frame)


@pytest.mark.parametrize("mirror,direction", [(False, "bullish"), (True, "bearish")])
def test_clean_trend_is_aligned_and_held(mirror, direction):
    out = st.structure_features(frame(UP, mirror=mirror), direction)
    assert out["structure_state"] == ("down" if mirror else "up")
    assert out["structure_aligned"] is True
    assert out["last_pivot_held"] is True
    assert out["hh_failed"] is False
    assert out["progress_atr_10"] > 0


@pytest.mark.parametrize("mirror,direction", [(False, "bearish"), (True, "bullish")])
def test_counter_trend_direction_is_not_aligned(mirror, direction):
    out = st.structure_features(frame(UP, mirror=mirror), direction)
    assert out["structure_aligned"] is False
    assert out["hh_failed"] is True
    assert out["progress_atr_10"] < 0


@pytest.mark.parametrize("mirror,direction", [(False, "bullish"), (True, "bearish")])
def test_lower_high_is_mixed_and_hh_failed(mirror, direction):
    out = st.structure_features(frame(MIXED, mirror=mirror), direction)
    assert out["structure_state"] == "mixed"
    assert out["structure_aligned"] is False
    assert out["hh_failed"] is True
    assert out["last_pivot_held"] is True


@pytest.mark.parametrize("mirror,direction", [(False, "bullish"), (True, "bearish")])
def test_close_through_last_pivot_is_not_held(mirror, direction):
    assert st.structure_features(frame(BROKEN, mirror=mirror), direction)["last_pivot_held"] is False


def test_swing_distances_fill_the_dead_keys():
    df = frame(UP)
    out = st.structure_features(df, "bullish")
    pivots = st.confirmed_pivots(df).iloc[-1]
    atr14 = float(atr(df, 14).iloc[-1])
    close = float(df["Close"].iloc[-1])
    assert out["swing_high_atr"] == pytest.approx((pivots["last_sh"] - close) / atr14, abs=1e-6)
    assert out["swing_low_atr"] == pytest.approx((close - pivots["last_sl"]) / atr14, abs=1e-6)
    assert out["swing_high_atr"] == st.structure_features(df, "bearish")["swing_high_atr"]


def test_progress_is_direction_signed():
    df = frame(UP)
    assert st.structure_features(df, "bearish")["progress_atr_10"] == \
        -st.structure_features(df, "bullish")["progress_atr_10"]


def test_pullback_on_half_the_impulse_volume():
    df = pullback_frame()
    assert st.pullback_vol_ratio(df, "bullish") == 0.5
    assert st.structure_features(df, "bullish")["pullback_vol_ratio"] == 0.5


def test_bearish_pullback_mirror():
    df = pullback_frame()
    mirrored = make_ohlcv((250 - df["Close"]).to_numpy(), spread_pct=1.0, volumes=df["Volume"].to_numpy())
    assert st.pullback_vol_ratio(mirrored, "bearish") == 0.5


def test_price_back_above_the_high_is_not_a_pullback():
    df = pullback_frame()
    closes = df["Close"].to_numpy().copy()
    closes[-1] = 125.0
    beyond = make_ohlcv(closes, spread_pct=1.0, volumes=df["Volume"].to_numpy())
    assert st.pullback_vol_ratio(beyond, "bullish") is None


def _absorption_frame():
    df = frame(UP).copy()
    last = df.index[-1]
    mid = float(df.loc[last, "Close"])
    df.loc[last, ["High", "Low", "Volume"]] = [mid + 0.2, mid - 0.2, 3_000_000.0]   # inside, 3x volume
    return df


@pytest.mark.parametrize("direction", ["bullish", "bearish"])
def test_high_volume_narrow_bar_is_absorption(direction):
    out = st.structure_features(_absorption_frame(), direction)
    assert out["absorption_bar"] is True
    assert out["absorption_count_10"] == 1


def test_ordinary_bars_are_not_absorption():
    out = st.structure_features(frame(UP), "bullish")
    assert (out["absorption_bar"], out["absorption_count_10"]) == (False, 0)


def test_trend_ratios_on_uniform_volume():
    out = st.structure_features(frame(UP), "bullish")
    assert out["vol_trend_10_50"] == 1.0
    assert 0 < out["range_trend_10_50"] < 2


def test_short_frame_returns_all_none():
    out = st.structure_features(frame(UP).iloc[:59], "bullish")
    assert set(out) == set(st.STRUCTURE_KEYS)
    assert all(value is None for value in out.values())
    assert st.structure_features(frame(UP).iloc[:60], "bullish")["structure_state"] == "up"


def test_zero_volume_gives_none_not_an_error():
    df = frame(UP).copy()
    df["Volume"] = 0.0
    out = st.structure_features(df, "bullish")
    assert out["vol_trend_10_50"] is None and out["pullback_vol_ratio"] is None
    assert out["absorption_bar"] is False


def test_flat_prices_give_no_structure_and_no_atr_keys():
    out = st.structure_features(make_ohlcv(np.full(80, 100.0), spread_pct=0.0), "bullish")
    assert out["structure_state"] is None and out["structure_aligned"] is None
    assert out["swing_high_atr"] is None and out["progress_atr_10"] is None
    assert out["range_trend_10_50"] is None
    assert all(out[key] is None for key in st.LEG_SHAPE_KEYS)


def test_nan_bars_do_not_raise():
    df = frame(UP).copy()
    df.iloc[40:42, df.columns.get_loc("High")] = np.nan
    df.iloc[50, df.columns.get_loc("Volume")] = np.nan
    assert st.structure_features(df, "bullish")["structure_state"] == "up"


def test_a_peak_younger_than_k_bars_is_not_used():
    df = frame(UP)                                   # peak 130 at bar 72, prior peak 125 at bar 56
    assert st.confirmed_pivots(df.iloc[:75]).iloc[-1]["last_sh_pos"] == 56   # t=74: 72 > t-k
    assert st.confirmed_pivots(df.iloc[:76]).iloc[-1]["last_sh_pos"] == 72   # t=75: confirmed
    close, atr14 = float(df["Close"].iloc[74]), float(atr(df.iloc[:75], 14).iloc[-1])
    expected = round((float(df["High"].iloc[56]) - close) / atr14, 6)
    assert st.structure_features(df.iloc[:75], "bullish")["swing_high_atr"] == expected


def test_pullback_shape_on_hand_derived_legs():
    df = pullback_frame()                            # SL0 bar 48, SH bar 58, t = 61
    assert st.pullback_legs(df, "bullish") == (48, 58, 61)
    out = st.structure_features(df, "bullish")
    # depth = (High[58] - min Low[59..61]) / (High[58] - Low[48]) = (120.6 - 113.43) / (120.6 - 99.5)
    assert out["pullback_depth_frac"] == round(7.17 / 21.1, 6)
    assert out["pullback_bars_ratio"] == 0.3         # 3 pullback bars / 10 impulse bars


def test_bearish_pullback_shape_mirror():
    df = pullback_frame()
    mirrored = make_ohlcv((250 - df["Close"]).to_numpy(), spread_pct=1.0, volumes=df["Volume"].to_numpy())
    high, low = mirrored["High"].to_numpy(), mirrored["Low"].to_numpy()
    out = st.structure_features(mirrored, "bearish")
    assert st.pullback_legs(mirrored, "bearish") == (48, 58, 61)
    assert out["pullback_depth_frac"] == round((high[59:62].max() - low[58]) / (high[48] - low[58]), 6)
    assert out["pullback_bars_ratio"] == 0.3


def test_impulse_speed_is_height_per_bar_in_atr():
    df = pullback_frame()
    atr14 = float(atr(df, 14).iloc[-1])
    assert st.structure_features(df, "bullish")["impulse_atr_per_bar"] == pytest.approx(21.1 / 10 / atr14, abs=1e-6)


def test_slowing_impulse_has_range_decay_below_one():
    assert st.structure_features(slowing_pullback_frame(), "bullish")["impulse_range_decay"] < 0.5
    assert st.structure_features(pullback_frame(), "bullish")["impulse_range_decay"] > 1.0


def test_short_impulse_has_no_range_decay_but_keeps_the_rest():
    out = st.structure_features(short_impulse_frame(), "bullish")
    assert st.pullback_legs(short_impulse_frame(), "bullish") == (56, 60, 63)
    assert out["impulse_range_decay"] is None
    assert out["pullback_bars_ratio"] == 0.75        # 3 / 4
    assert out["pullback_depth_frac"] is not None and out["impulse_atr_per_bar"] is not None


def test_no_pullback_leaves_every_leg_shape_key_none():
    df = pullback_frame()
    closes = df["Close"].to_numpy().copy()
    closes[-1] = 125.0                               # back above the swing high
    beyond = make_ohlcv(closes, spread_pct=1.0, volumes=df["Volume"].to_numpy())
    out = st.structure_features(beyond, "bullish")
    assert st.pullback_legs(beyond, "bullish") is None
    assert all(out[key] is None for key in st.LEG_SHAPE_KEYS)


def test_leg_shape_keys_ignore_volume():
    df = pullback_frame().copy()
    df["Volume"] = 0.0
    out = st.structure_features(df, "bullish")
    assert out["pullback_vol_ratio"] is None
    assert out["pullback_bars_ratio"] == 0.3


def _mirror(df):
    return make_ohlcv((250 - df["Close"]).to_numpy(), spread_pct=1.0, volumes=df["Volume"].to_numpy())


def test_bearish_impulse_speed_mirror():
    mirrored = _mirror(pullback_frame())
    high, low = mirrored["High"].to_numpy(), mirrored["Low"].to_numpy()
    atr14 = float(atr(mirrored, 14).iloc[-1])
    expected = (high[48] - low[58]) / 10 / atr14
    assert st.structure_features(mirrored, "bearish")["impulse_atr_per_bar"] == pytest.approx(expected, abs=1e-6)


def test_bearish_slowing_impulse_range_decay_mirror():
    assert st.structure_features(_mirror(slowing_pullback_frame()), "bearish")["impulse_range_decay"] < 0.5
    assert st.structure_features(_mirror(pullback_frame()), "bearish")["impulse_range_decay"] > 1.0


def test_bearish_short_impulse_mirror():
    mirrored = _mirror(short_impulse_frame())
    out = st.structure_features(mirrored, "bearish")
    assert st.pullback_legs(mirrored, "bearish") == (56, 60, 63)
    assert out["impulse_range_decay"] is None
    assert out["pullback_bars_ratio"] == 0.75
    assert out["pullback_depth_frac"] is not None and out["impulse_atr_per_bar"] is not None


def test_price_back_below_the_low_is_not_a_bearish_pullback():
    mirrored = _mirror(pullback_frame())
    closes = mirrored["Close"].to_numpy().copy()
    closes[-1] = 125.0
    beyond = make_ohlcv(closes, spread_pct=1.0, volumes=mirrored["Volume"].to_numpy())
    assert st.pullback_vol_ratio(beyond, "bearish") is None
    assert st.pullback_legs(beyond, "bearish") is None
    assert all(st.structure_features(beyond, "bearish")[key] is None for key in st.LEG_SHAPE_KEYS)


def test_swing_distances_bearish_mirror_frame():
    df = frame(UP, mirror=True)
    out = st.structure_features(df, "bearish")
    pivots = st.confirmed_pivots(df).iloc[-1]
    atr14 = float(atr(df, 14).iloc[-1])
    close = float(df["Close"].iloc[-1])
    assert out["swing_high_atr"] == pytest.approx((pivots["last_sh"] - close) / atr14, abs=1e-6)
    assert out["swing_low_atr"] == pytest.approx((close - pivots["last_sl"]) / atr14, abs=1e-6)
    assert out["swing_low_atr"] == st.structure_features(df, "bullish")["swing_low_atr"]


@pytest.mark.parametrize("direction", ["bullish", "bearish"])
def test_features_are_truncation_stable(direction):
    from tests.market.structure_fixtures import wavy_frame
    df = wavy_frame()
    for n in (120, 200, 260):
        assert st.structure_features(df.iloc[:n], direction) ==             st.structure_features(df.iloc[:n].copy(), direction)
        future_scrambled = df.iloc[:n + 30].copy()
        future_scrambled.iloc[n:] = future_scrambled.iloc[n:] * 3
        assert st.structure_features(future_scrambled.iloc[:n], direction) ==             st.structure_features(df.iloc[:n], direction)
