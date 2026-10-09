"""v140 forward drift and rank correlation: reported beside the verdict, never read by it."""
import numpy as np
import pandas as pd
import pytest

from swingbot.core.backtesting.screen import forward
from tests.backtesting.screen.helpers import frame


def test_horizons_are_the_spec_set():
    assert forward.HORIZONS == (5, 10, 20, 60)


def test_forward_atr_hand_computed():
    df = frame([100.0, 102.0, 104.0, 103.0])
    atr = pd.Series(2.0, index=df.index)
    out = forward.forward_atr(df, atr, 2)
    assert out[:2].tolist() == [2.0, 0.5]
    assert np.isnan(out[2:]).all()


def test_forward_atr_past_the_frame_is_all_nan():
    df = frame([100.0, 101.0])
    assert np.isnan(forward.forward_atr(df, pd.Series(1.0, index=df.index), 5)).all()


def test_excess_drift_is_event_minus_null_mean_and_skips_empty_pairs():
    fwd = np.array([1.0, 0.0, 2.0, np.nan, 4.0])
    out = forward.excess_drift(fwd, [0, 4], (np.array([1, 2]), np.array([3])))
    assert out == [pytest.approx(0.0)]


def test_spearman_known_answers():
    assert forward.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert forward.spearman([1, 2, 3, 4], [40, 30, 20, 10]) == pytest.approx(-1.0)
    assert forward.spearman([0, 0, 1, 1], [1, 2, 3, 4]) == pytest.approx(0.894427, abs=1e-6)


def test_spearman_is_none_when_undefined():
    assert forward.spearman([1, 1, 1, 1], [1, 2, 3, 4]) is None
    assert forward.spearman([1, 2], [1, 2]) is None


def test_yearly_rank_corr_drops_nan_and_splits_by_year():
    years = np.array([2010] * 4 + [2011] * 4)
    indicator = np.array([0, 0, 1, 1, 1, 1, 0, 0])
    fwd = np.array([1.0, 2.0, 3.0, 4.0, 4.0, 3.0, 2.0, np.nan])
    out = forward.yearly_rank_corr(years, indicator, fwd)
    assert set(out) == {2010, 2011}
    assert out[2010] == pytest.approx(0.894427, abs=1e-6)
    assert out[2011] == pytest.approx(0.866025, abs=1e-6)
