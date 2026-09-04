"""The dead-cat-bounce detector -- v68's one piece of pattern geometry.

Every frame here is synthetic and built from tests/conftest.py's shared
builders, so a failure names a shape rather than a ticker.
"""
import numpy as np
import pandas as pd
import pytest

from tests.conftest import make_ohlcv
from swingbot.core.market.chart_patterns import (
    DEFAULT_DCB_PARAMS, dead_cat_bounce,
)


def _dcb_frame(decline_pct=30.0, retrace=0.25, bounce_bars=4, pre_bars=30):
    """A textbook dead cat bounce: flat, then a hard drop, then a weak bounce."""
    peak = 100.0
    trough = peak * (1 - decline_pct / 100)
    now = trough + (peak - trough) * retrace
    closes = (
        [peak] * pre_bars
        + list(np.linspace(peak, trough, 8))[1:]
        + list(np.linspace(trough, now, bounce_bars + 1))[1:]
    )
    return make_ohlcv(closes)


def test_a_textbook_dead_cat_bounce_is_detected():
    assert dead_cat_bounce(_dcb_frame())["detected"] is True


def test_a_v_shaped_recovery_past_half_is_not_a_dead_cat():
    # The whole point of RETRACE_MAX: a bounce that reclaims most of the
    # decline is a recovery, and vetoing it would block the good case.
    assert dead_cat_bounce(_dcb_frame(retrace=0.80))["detected"] is False


def test_a_shallow_decline_is_not_a_dead_cat():
    assert dead_cat_bounce(_dcb_frame(decline_pct=5.0))["detected"] is False


def test_a_still_falling_frame_is_not_a_dead_cat():
    # Deliberate scope limit (spec): no bounce yet means no dead cat bounce,
    # even though this is exactly the falling knife a broader veto would catch.
    closes = [100.0] * 30 + list(np.linspace(100.0, 60.0, 12))[1:]
    assert dead_cat_bounce(make_ohlcv(closes))["detected"] is False


def test_a_frame_shorter_than_the_window_blocks_nothing():
    # An uncomputable gate never vetoes -- entry_filters.py's own convention.
    assert dead_cat_bounce(make_ohlcv([100.0] * 5))["detected"] is False


def test_a_trough_at_the_window_start_blocks_nothing():
    """The decline began before the window, so its magnitude is not
    measurable from the data in hand and must not be guessed at."""
    lookback = DEFAULT_DCB_PARAMS["lookback"]
    closes = [60.0] + list(np.linspace(60.0, 70.0, lookback))
    assert dead_cat_bounce(make_ohlcv(closes))["detected"] is False


def test_a_flat_frame_does_not_divide_by_zero():
    assert dead_cat_bounce(make_ohlcv([100.0] * 60))["detected"] is False


def test_the_evidence_survives_a_detection():
    got = dead_cat_bounce(_dcb_frame(decline_pct=30.0, retrace=0.25))
    assert got["decline_pct"] == pytest.approx(30.0, abs=1.5)
    assert got["retrace"] == pytest.approx(0.25, abs=0.10)


def test_the_gap_arm_rejects_a_gapless_decline():
    frame = _dcb_frame()          # linspace decline -- no single-bar gap
    params = {**DEFAULT_DCB_PARAMS, "gap_required": True}
    assert dead_cat_bounce(frame, params)["detected"] is False


def test_the_gap_arm_accepts_a_real_breakaway_gap():
    closes = [100.0] * 30 + [70.0, 69.0, 68.0, 71.0, 73.0]
    frame = make_ohlcv(closes)              # make_ohlcv sets Open = prior close
    frame.loc[frame.index[30], "Open"] = 71.0   # a genuine gap down from 100
    params = {**DEFAULT_DCB_PARAMS, "gap_required": True}
    assert dead_cat_bounce(frame, params)["detected"] is True


def test_the_volume_arm_rejects_a_high_conviction_bounce():
    frame = _dcb_frame(bounce_bars=4)
    volumes = [1_000_000.0] * len(frame)
    volumes[-4:] = [5_000_000.0] * 4        # the bounce is the loudest thing here
    frame["Volume"] = volumes
    params = {**DEFAULT_DCB_PARAMS, "volume_ratio": 0.8}
    assert dead_cat_bounce(frame, params)["detected"] is False


def test_the_volume_arm_accepts_a_quiet_bounce():
    frame = _dcb_frame(bounce_bars=4)
    volumes = [1_000_000.0] * len(frame)
    volumes[-12:-4] = [4_000_000.0] * 8     # heavy selling
    volumes[-4:] = [500_000.0] * 4          # nobody buying
    frame["Volume"] = volumes
    params = {**DEFAULT_DCB_PARAMS, "volume_ratio": 0.8}
    assert dead_cat_bounce(frame, params)["detected"] is True


@pytest.mark.parametrize("threshold,expected", [(15.0, True), (25.0, False)])
def test_the_decline_threshold_is_the_grid_dimension(threshold, expected):
    frame = _dcb_frame(decline_pct=20.0)
    params = {**DEFAULT_DCB_PARAMS, "decline_pct": threshold}
    assert dead_cat_bounce(frame, params)["detected"] is expected


def test_the_four_fixed_parameters_are_the_spec_values():
    # These are set from reasoning, not from the grid. A change here is a new
    # pre-registration, so it should be a visible test failure.
    assert DEFAULT_DCB_PARAMS["lookback"] == 20
    assert DEFAULT_DCB_PARAMS["retrace_max"] == 0.50
    assert DEFAULT_DCB_PARAMS["bounce_min_bars"] == 2
    assert DEFAULT_DCB_PARAMS["gap_pct"] == 5.0
