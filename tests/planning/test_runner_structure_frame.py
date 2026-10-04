import math

import pandas as pd
import pytest

from swingbot.core.planning.exit_sim import PIVOT_K, runner_structure_frame
from tests.planning.structure_fixtures import WARMUP, sawtooth, stall_frame

POSITIONS = ("sh_i", "sh_prev_i", "sl_i", "sl_prev_i")


def test_v121_contract_is_merged():
    from swingbot.core.market import structure
    assert callable(structure.confirmed_pivots)


def test_frame_is_truncation_stable():
    df = stall_frame()
    full = runner_structure_frame(df)
    for cut in range(5, len(df) + 1):
        pd.testing.assert_series_equal(runner_structure_frame(df.iloc[:cut]).iloc[-1],
                                       full.iloc[cut - 1], check_names=False)


def test_no_pivot_is_known_before_k_bars():
    frame = runner_structure_frame(stall_frame())
    for j in range(len(frame)):
        for col in POSITIONS:
            value = frame[col].iloc[j]
            assert math.isnan(value) or value <= j - PIVOT_K


def test_trend_ratios_equal_v121_scalars_at_every_bar():
    from swingbot.core.market import structure
    df = stall_frame()
    frame = runner_structure_frame(df)
    for t in range(structure.MIN_BARS - 1, len(df)):
        scalar = structure.structure_features(df.iloc[:t + 1], "bullish")
        for key in ("range_trend_10_50", "vol_trend_10_50"):
            assert frame[key].iloc[t] == pytest.approx(scalar[key], abs=1e-6), (key, t)


def test_sawtooth_prints_a_higher_low_each_cycle():
    df = sawtooth(3)
    frame = runner_structure_frame(df)
    first_sl = WARMUP + 6                     # bottom of cycle 1
    assert frame["sl_i"].iloc[first_sl + PIVOT_K] == first_sl
    assert frame["sl_px"].iloc[first_sl + PIVOT_K] == df["Low"].iloc[first_sl]
    assert math.isnan(frame["sl_i"].iloc[first_sl + PIVOT_K - 1]) or \
        frame["sl_i"].iloc[first_sl + PIVOT_K - 1] < first_sl
