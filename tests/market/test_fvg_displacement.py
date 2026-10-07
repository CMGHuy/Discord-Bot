"""v128: the causal displacement predicate and the FVG mode filter."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from swingbot.core.market import fvg
from swingbot.core.market.indicators import atr
from tests.market.fvg_frames import (BEAR_THIRD, BULL_THIRD, MID_CLOSE_BULL, STRONG_BEAR, STRONG_BULL,
                                     UP_CLOSE_BIG, WEAK_BULL, bar_frame, gap_frame, witness_frame)

WITNESS = Path(__file__).resolve().parents[1] / "fixtures" / "v128" / "fvg_all_witness.json"


def _only_gap(frame):
    gaps = fvg.find_fair_value_gaps_detailed(frame)
    assert len(gaps) == 1, gaps
    return gaps[0]


def test_strong_bullish_body_closing_in_the_top_third_is_displacement():
    frame = gap_frame(STRONG_BULL, BULL_THIRD)
    assert fvg.is_displacement_gap(frame, _only_gap(frame), 1.5) is True


def test_body_below_k_atr_is_not_displacement():
    frame = gap_frame(WEAK_BULL, BULL_THIRD)
    assert fvg.is_displacement_gap(frame, _only_gap(frame), 1.5) is False


def test_k_is_the_body_threshold():
    frame = gap_frame(STRONG_BULL, BULL_THIRD)
    gap = _only_gap(frame)
    assert fvg.is_displacement_gap(frame, gap, 1.0) is True
    assert fvg.is_displacement_gap(frame, gap, 2.0) is False       # 2.0 x 2.1714 = 4.34 > body 4.0


def test_close_outside_the_extreme_third_is_not_displacement():
    frame = gap_frame(MID_CLOSE_BULL, BULL_THIRD)
    assert fvg.is_displacement_gap(frame, _only_gap(frame), 1.5) is False


def test_bearish_mirror():
    frame = gap_frame(STRONG_BEAR, BEAR_THIRD)
    gap = _only_gap(frame)
    assert gap["direction"] == "bearish"
    assert fvg.is_displacement_gap(frame, gap, 1.5) is True


def test_bearish_gap_needs_the_close_in_the_bottom_third():
    frame = gap_frame(UP_CLOSE_BIG, BEAR_THIRD)
    gap = _only_gap(frame)
    assert gap["direction"] == "bearish"
    assert fvg.is_displacement_gap(frame, gap, 1.5) is False


@pytest.mark.parametrize("atr_value", [np.nan, 0.0, -1.0, np.inf])
def test_non_finite_or_non_positive_atr_is_not_displacement(atr_value):
    frame = gap_frame(STRONG_BULL, BULL_THIRD)
    series = pd.Series(atr_value, index=frame.index)
    assert fvg.is_displacement_gap(frame, _only_gap(frame), 1.5, atr_series=series) is False


def test_too_little_history_for_atr14_is_not_displacement():
    frame = gap_frame(STRONG_BULL, BULL_THIRD, flat_bars=3)      # ATR14 is still NaN at the middle candle
    assert fvg.is_displacement_gap(frame, _only_gap(frame), 1.5) is False


def test_appending_future_bars_never_changes_the_verdict():
    frame = gap_frame(STRONG_BULL, BULL_THIRD)
    gap = _only_gap(frame)
    violent = [(104.5, 130.0, 102.0, 128.0), (128.0, 129.0, 60.0, 61.0)] * 5
    extended = bar_frame(list(frame[["Open", "High", "Low", "Close"]].itertuples(index=False, name=None)) + violent)
    for k in (1.0, 1.5, 2.0):
        assert fvg.is_displacement_gap(extended, gap, k) == fvg.is_displacement_gap(frame, gap, k)
    assert fvg.is_displacement_gap(extended, gap, 1.5, atr_series=atr(extended, 14)) is True


def test_mode_all_matches_the_pre_change_witness():
    expected = [tuple(row) for row in json.loads(WITNESS.read_text(encoding="utf-8"))]
    assert fvg.find_fair_value_gaps(witness_frame()) == expected
    assert fvg.find_fair_value_gaps(witness_frame(), mode="all", k=2.0) == expected


def test_mode_off_returns_nothing():
    assert fvg.find_fair_value_gaps(witness_frame(), mode="off") == []


@pytest.mark.parametrize("k", [1.0, 1.5, 2.0])
def test_displacement_is_a_subset_of_all(k):
    everything = fvg.find_fair_value_gaps(witness_frame())
    kept = fvg.find_fair_value_gaps(witness_frame(), mode="displacement", k=k)
    assert all(item in everything for item in kept)


def test_displacement_filters_on_the_hand_built_frames():
    strong = fvg.find_fair_value_gaps(gap_frame(STRONG_BULL, BULL_THIRD), mode="displacement", k=1.5)
    weak = fvg.find_fair_value_gaps(gap_frame(WEAK_BULL, BULL_THIRD), mode="displacement", k=1.5)
    assert (strong, weak) == ([(101.25, "FVG (bullish)")], [])


def test_filter_gaps_keeps_the_same_dict_objects():
    frame = gap_frame(STRONG_BULL, BULL_THIRD)
    gaps = fvg.find_fair_value_gaps_detailed(frame)
    assert fvg.filter_gaps(frame, gaps, "displacement", 1.5)[0] is gaps[0]
    assert fvg.filter_gaps(frame, gaps, "all")[0] is gaps[0]


def test_unknown_mode_raises():
    with pytest.raises(ValueError, match="unknown FVG mode"):
        fvg.find_fair_value_gaps(witness_frame(), mode="sideways")


def test_detailed_output_is_unchanged_so_charts_keep_every_gap():
    assert len(fvg.find_fair_value_gaps_detailed(gap_frame(WEAK_BULL, BULL_THIRD))) == 1
