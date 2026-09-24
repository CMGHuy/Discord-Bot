"""v101 Phase A: Fibonacci mechanism diagnostic (TRAIN only)."""
import sys
from pathlib import Path
from types import SimpleNamespace as T

import numpy as np
import pytest

from tests.helpers import make_ohlcv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "backtest"))


def _mfd():
    import measure_fib_diagnostic as mfd
    return mfd


def test_fib_level_bull_measures_down_from_the_high():
    mfd = _mfd()
    assert mfd.fib_level(110.0, 100.0, 0.5, "bullish") == pytest.approx(105.0)
    assert mfd.fib_level(110.0, 100.0, 0.382, "bullish") == pytest.approx(106.18)


def test_fib_level_bear_measures_up_from_the_low():
    mfd = _mfd()
    assert mfd.fib_level(110.0, 100.0, 0.382, "bearish") == pytest.approx(103.82)


def test_tested_ratio_is_the_nearest_entry_ratio():
    mfd = _mfd()
    # bullish levels: 0.382 -> 106.18, 0.5 -> 105.0, 0.618 -> 103.82
    assert mfd.tested_ratio(104.0, 110.0, 100.0, "bullish") == 0.618
    assert mfd.tested_ratio(106.0, 110.0, 100.0, "bullish") == 0.382


def test_structural_stop_sits_one_buffer_beyond_the_swing_extreme():
    mfd = _mfd()
    buf = mfd.STRUCTURE_BUFFER_ATR * 2.0
    assert mfd.structural_stop(110.0, 100.0, 2.0, "bullish") == pytest.approx(100.0 - buf)
    assert mfd.structural_stop(110.0, 100.0, 2.0, "bearish") == pytest.approx(110.0 + buf)


def test_deeper_ratio_stop_uses_the_next_ratio_on_the_ladder():
    mfd = _mfd()
    buf = mfd.STRUCTURE_BUFFER_ATR * 2.0
    # close 104 tests 0.618 -> deeper is 0.786 -> level 110 - 7.86 = 102.14
    assert mfd.deeper_ratio_stop(104.0, 110.0, 100.0, 2.0, "bullish") == pytest.approx(102.14 - buf)
    # bearish close 106.2 tests 0.618 (100 + 6.18) -> deeper 0.786 -> 107.86
    assert mfd.deeper_ratio_stop(106.2, 110.0, 100.0, 2.0, "bearish") == pytest.approx(107.86 + buf)


def test_apply_cap_pulls_a_too_wide_stop_in_and_flags_it():
    mfd = _mfd()
    assert mfd.apply_cap(100.0, 90.0, "bullish", 5.0) == (pytest.approx(95.0), True)
    assert mfd.apply_cap(100.0, 97.0, "bullish", 5.0) == (pytest.approx(97.0), False)
    assert mfd.apply_cap(100.0, 110.0, "bearish", 5.0) == (pytest.approx(105.0), True)


def test_cap_distance_matches_the_builder_arithmetic():
    mfd = _mfd()
    pct = mfd.capped_planned_loss_pct(mfd.HORIZONS["4w"]["max_risk_pct"])
    assert mfd.cap_distance(200.0, "4w") == pytest.approx(200.0 * pct / 100)


def test_first_touch_checks_the_stop_before_the_target_on_the_same_bar():
    mfd = _mfd()
    high, low, close = np.array([100, 112.0]), np.array([100, 94.0]), np.array([100, 100.0])
    assert mfd.simulate_first_touch(high, low, close, 0, 100.0, 95.0, 110.0, "bullish", 5) == ("loss", -1.0)


def test_first_touch_win_pays_the_planned_r():
    mfd = _mfd()
    high, low, close = np.array([100, 101, 111.0]), np.array([100, 99, 100.0]), np.array([100, 100, 110.0])
    assert mfd.simulate_first_touch(high, low, close, 0, 100.0, 95.0, 110.0, "bullish", 5) == ("win", pytest.approx(2.0))


def test_first_touch_bearish_win():
    mfd = _mfd()
    high, low, close = np.array([100, 101, 100.0]), np.array([100, 99, 89.0]), np.array([100, 100, 90.0])
    assert mfd.simulate_first_touch(high, low, close, 0, 100.0, 105.0, 90.0, "bearish", 5) == ("win", pytest.approx(2.0))


def test_first_touch_timeout_marks_to_the_last_close_in_the_hold():
    mfd = _mfd()
    high, low, close = np.array([100, 101, 103, 150.0]), np.array([100, 99, 99, 99.0]), np.array([100, 100, 102, 150.0])
    assert mfd.simulate_first_touch(high, low, close, 0, 100.0, 95.0, 110.0, "bullish", 2) == ("timeout", pytest.approx(0.4))


def test_first_touch_is_open_when_no_forward_bar_exists():
    mfd = _mfd()
    a = np.array([100.0])
    assert mfd.simulate_first_touch(a, a, a, 0, 100.0, 95.0, 110.0, "bullish", 5) == ("open", None)


def test_reclaim_bar_is_the_first_close_beyond_the_signal_bar_extreme():
    mfd = _mfd()
    high = np.array([101, 100, 100, 100.0])
    low = np.array([99, 98, 98, 98.0])
    close = np.array([100, 99, 101.5, 102.0])
    assert mfd.reclaim_bar(high, low, close, 0, "bullish") == 2
    assert mfd.reclaim_bar(high, low, close, 0, "bearish") is None
    assert mfd.reclaim_bar(high, low, close, 0, "bullish", window=1) is None
