# tests/market/test_major_structure_features.py
import numpy as np
import pytest

from swingbot.core.market import structure as st
from swingbot.core.market.indicators import atr
from tests.conftest import make_ohlcv
from tests.fixtures.ohlcv_parity import load_ohlcv
from tests.market.structure_fixtures import UP, frame, wavy_frame
from tests.market.structure_tier_fixtures import DOWN, tier_frame


def _cut(mirror, last_bar):
    return tier_frame(DOWN, mirror=mirror).iloc[:last_bar + 1]


@pytest.mark.parametrize("mirror,state", [(False, "down"), (True, "up")])
def test_major_state_and_alignment_follow_the_trade_direction(mirror, state):
    df = _cut(mirror, 93)
    with_trend, counter = ("bullish", "bearish") if mirror else ("bearish", "bullish")
    assert st.major_structure_features(df, with_trend)["structure_state_major"] == state
    assert st.major_structure_features(df, with_trend)["structure_aligned_major"] is True
    assert st.major_structure_features(df, counter)["structure_aligned_major"] is False


@pytest.mark.parametrize("mirror,with_side,against_side", [(False, "bullish", "bearish"), (True, "bearish", "bullish")])
def test_choch_is_labelled_with_or_against_the_trade(mirror, with_side, against_side):
    df = _cut(mirror, 96)                                  # CHoCH fired at bar 94
    out = st.major_structure_features(df, with_side)
    assert (out["struct_event_last"], out["struct_event_bars_ago"]) == ("choch_with", 2)
    assert type(out["struct_event_bars_ago"]) is int
    assert st.major_structure_features(df, against_side)["struct_event_last"] == "choch_against"


@pytest.mark.parametrize("mirror,with_side,against_side", [(False, "bearish", "bullish"), (True, "bullish", "bearish")])
def test_bos_is_labelled_with_or_against_the_trade(mirror, with_side, against_side):
    df = _cut(mirror, 70)                                  # BOS fired on the final bar
    out = st.major_structure_features(df, with_side)
    assert (out["struct_event_last"], out["struct_event_bars_ago"]) == ("bos_with", 0)
    assert st.major_structure_features(df, against_side)["struct_event_last"] == "bos_against"


def test_major_distances_are_side_named_not_direction_signed():
    df = _cut(False, 93)
    majors = st.major_pivots(df).iloc[-1]
    close, atr14 = float(df["Close"].iloc[-1]), float(atr(df, 14).iloc[-1])
    out = st.major_structure_features(df, "bullish")
    assert out["major_sh_atr"] == pytest.approx((majors["last_msh"] - close) / atr14, abs=1e-6)
    assert out["major_sl_atr"] == pytest.approx((close - majors["last_msl"]) / atr14, abs=1e-6)
    assert out["major_sh_atr"] == st.major_structure_features(df, "bearish")["major_sh_atr"]


def test_reaction_of_the_last_swing_low_in_atr_at_the_pivot():
    df = _cut(False, 96)                                   # last confirmed k=3 low is bar 88, rally still running
    high, low = df["High"].to_numpy(), df["Low"].to_numpy()
    expected = round((high[88:].max() - low[88]) / float(atr(df, 14).iloc[88]), 6)
    out = st.major_structure_features(df, "bullish")
    assert st.confirmed_pivots(df).iloc[-1]["last_sl_pos"] == 88
    assert out["last_sl_reaction_atr"] == expected
    assert out["last_sh_reaction_atr"] is None             # the last swing high (bar 80) has been taken out


def test_reaction_mirror_for_the_last_swing_high():
    df = _cut(True, 96)
    high, low = df["High"].to_numpy(), df["Low"].to_numpy()
    expected = round((high[88] - low[88:].min()) / float(atr(df, 14).iloc[88]), 6)
    out = st.major_structure_features(df, "bearish")
    assert out["last_sh_reaction_atr"] == expected
    assert out["last_sl_reaction_atr"] is None


def test_no_major_high_leaves_state_and_event_none_but_keeps_the_low_side():
    out = st.major_structure_features(frame(UP), "bullish")
    assert out["structure_state_major"] is None and out["structure_aligned_major"] is None
    assert out["major_sh_atr"] is None and out["major_sl_atr"] > 0
    assert out["struct_event_last"] is None and out["struct_event_bars_ago"] is None


def test_short_frame_returns_all_none():
    df = tier_frame(DOWN)
    out = st.major_structure_features(df.iloc[:59], "bullish")
    assert tuple(out) == st.MAJOR_KEYS
    assert all(value is None for value in out.values())
    assert st.major_structure_features(df.iloc[:60], "bullish")["major_sl_atr"] is not None
    assert all(value is None for value in st.major_structure_features(None, "bullish").values())


def test_flat_prices_give_all_none():
    out = st.major_structure_features(make_ohlcv(np.full(80, 100.0), spread_pct=0.0), "bullish")
    assert all(value is None for value in out.values())


def test_nan_bars_do_not_raise():
    df = tier_frame(DOWN).copy()
    df.iloc[40:42, df.columns.get_loc("High")] = np.nan
    df.iloc[50, df.columns.get_loc("Close")] = np.nan
    assert set(st.major_structure_features(df, "bullish")) == set(st.MAJOR_KEYS)


@pytest.mark.parametrize("df", [wavy_frame(), tier_frame(DOWN), load_ohlcv("TSLA").iloc[:400]],
                         ids=["wavy", "down", "tsla"])
@pytest.mark.parametrize("direction", ["bullish", "bearish"])
def test_features_equal_the_full_frame_rows_at_every_cut(df, direction):
    """The dict at cut t must be derivable from row t of the full-frame tables."""
    majors, events = st.major_pivots(df), st.structure_events(df)
    for t in range(59, len(df), 5):
        out = st.major_structure_features(df.iloc[:t + 1], direction)
        assert out["structure_state_major"] == st._major_state(majors.iloc[t]), t
        kind, side, pos = events.iloc[t]
        expected = None if kind is None else f"{kind}_{'with' if side == direction else 'against'}"
        assert out["struct_event_last"] == expected, t
        assert out["struct_event_bars_ago"] == (None if kind is None else t - int(pos)), t

