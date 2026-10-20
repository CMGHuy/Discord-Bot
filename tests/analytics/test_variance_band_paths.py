"""v175 § 1: the week-block path sampler and the per-horizon band.

Blocks in the intactness tests carry tagged values: block ``b`` holds
``10*b + 1, 10*b + 2, ...``, so any value says which block it came from and
where it sat inside that block.
"""
from datetime import date, timedelta

import numpy as np
import pytest

from swingbot.core.analytics import variance_band as vb
from swingbot.core.analytics.variance_band import CloseDay

TAGGED = [np.array([1.0, 2.0, 3.0]), np.array([11.0, 12.0]),
          np.array([21.0, 22.0, 23.0, 24.0, 25.0]), np.array([31.0])]
FAST = {"paths": 2_000, "outer": 20, "outer_paths": 200}


def _day(d, r):
    return CloseDay(d, r, vb.day_kind(r))


def _assert_whole_weeks(path):
    """The path is whole TAGGED blocks in a row, only the last one cut short."""
    i, h = 0, len(path)
    while i < h:
        start = path[i]
        assert start % 10 == 1, f"position {i} is not a week start: {path}"
        block = TAGGED[int(start) // 10]
        take = min(len(block), h - i)
        assert list(path[i:i + take]) == list(block[:take]), path
        i += take


def test_week_blocks_group_by_iso_week_of_the_close_date_in_order():
    monday = date(2026, 1, 5)
    days = [_day(monday, -1.0), _day(monday + timedelta(days=2), 2.0),
            _day(monday + timedelta(days=6), 0.0),          # Sunday, same ISO week
            _day(monday + timedelta(days=7), -0.5),         # next Monday
            _day(monday + timedelta(days=21), 1.0)]         # two weeks later
    blocks = vb.week_blocks(days)
    assert [b.tolist() for b in blocks] == [[-1.0, 2.0, 0.0], [-0.5], [1.0]]
    assert all(b.dtype == float for b in blocks)


def test_week_blocks_of_no_days():
    assert vb.week_blocks([]) == []


@pytest.mark.parametrize("h", [1, 4, 7, 20, 50])
def test_paths_hold_h_days_of_whole_weeks_with_the_last_truncated(h):
    paths = vb.sample_paths(TAGGED, h, 500, np.random.default_rng(1))
    assert paths.shape == (500, h)
    for path in paths:
        _assert_whole_weeks(path)


def test_every_week_is_drawn():
    paths = vb.sample_paths(TAGGED, 10, 500, np.random.default_rng(2))
    assert {int(v) // 10 for v in paths[:, 0]} == {0, 1, 2, 3}


def test_one_day_weeks_still_fill_the_path():
    blocks = [np.array([-1.0]), np.array([2.0])]
    paths = vb.sample_paths(blocks, 50, 300, np.random.default_rng(3))
    assert paths.shape == (300, 50)
    assert set(np.unique(paths)) <= {-1.0, 2.0}


def test_a_seed_reproduces_the_paths():
    a = vb.sample_paths(TAGGED, 20, 200, np.random.default_rng(42))
    b = vb.sample_paths(TAGGED, 20, 200, np.random.default_rng(42))
    c = vb.sample_paths(TAGGED, 20, 200, np.random.default_rng(43))
    assert np.array_equal(a, b)
    assert not np.array_equal(a, c)


def test_longest_run_uses_the_close_day_rule():
    paths = np.array([
        [-1.0, -1.0, 0.0, -1.0, 1.0, -1.0],    # L L S L | W L: scratch passed over -> 3
        [1.0, 1.0, 1.0, 1.0, 1.0, 1.0],        # no loss day -> 0
        [-1.0, 0.05, -0.06, 0.06, -1.0, -1.0],  # L S L | W L L -> 2
        [-0.05, -0.05, -0.05, -0.05, -0.05, -0.05],  # all scratch -> 0
    ])
    assert vb.path_longest_runs(paths).tolist() == [3, 0, 2, 0]


def test_max_drawdown_from_the_running_peak_with_a_zero_baseline():
    paths = np.array([
        [1.0, -1.0, -1.0, 2.0, -3.0],          # cum 1 0 -1 1 -2, peak 1 -> 3
        [-1.0, -1.0, 0.0, 0.0, 0.0],           # never above 0: from the baseline -> 2
        [1.0, 1.0, 1.0, 1.0, 1.0],             # -> 0
    ])
    assert vb.path_max_drawdowns(paths).tolist() == pytest.approx([3.0, 2.0, 0.0])


def test_horizon_band_shape_and_types():
    blocks = [np.array([-1.0, 2.0, -1.0, 0.0, -1.0]), np.array([1.5, -1.0]),
              np.array([-1.0, -1.0, -1.0]), np.array([2.0, 2.0, -1.0, 1.0])]
    band = vb.horizon_band(blocks, 20, **FAST)
    assert set(band) == {"horizon", "run", "drawdown"}
    assert band["horizon"] == 20
    for key in ("run", "drawdown"):
        assert set(band[key]) == {"p80", "p95", "p95_lo", "p95_hi"}
        q = band[key]
        assert q["p80"] <= q["p95"]
        assert q["p95_lo"] <= q["p95_hi"]
    assert all(type(v) is int for v in band["run"].values())
    assert all(type(v) is float for v in band["drawdown"].values())
    assert all(round(v, 2) == v for v in band["drawdown"].values())


def test_horizon_band_is_reproducible_from_its_seed():
    blocks = [np.array([-1.0, 2.0, -1.0]), np.array([1.5, -1.0, -1.0, -1.0])]
    assert vb.horizon_band(blocks, 50, **FAST) == vb.horizon_band(blocks, 50, **FAST)


def test_an_all_win_book_gives_a_zero_band():
    blocks = [np.array([1.0, 2.0, 1.0]), np.array([0.5, 0.5])]
    band = vb.horizon_band(blocks, 20, **FAST)
    assert band["run"] == {"p80": 0, "p95": 0, "p95_lo": 0, "p95_hi": 0}
    assert band["drawdown"] == {"p80": 0.0, "p95": 0.0, "p95_lo": 0.0, "p95_hi": 0.0}


def test_an_all_loss_book_runs_the_whole_horizon():
    blocks = [np.array([-1.0] * 5), np.array([-1.0] * 3)]
    band = vb.horizon_band(blocks, 20, **FAST)
    assert band["run"] == {"p80": 20, "p95": 20, "p95_lo": 20, "p95_hi": 20}
    assert band["drawdown"] == {"p80": 20.0, "p95": 20.0, "p95_lo": 20.0, "p95_hi": 20.0}


def test_correlated_weeks_widen_the_run_band():
    # Same day mix (half losses): kept in all-loss weeks versus spread
    # across alternating weeks. Week blocks keep the clusters, so the
    # clustered book's p95 run is longer.
    clustered = [np.array([-1.0] * 5), np.array([1.0] * 5)] * 10
    spread = [np.array([-1.0, 1.0, -1.0, 1.0, -1.0]),
              np.array([1.0, -1.0, 1.0, -1.0, 1.0])] * 10
    wide = vb.horizon_band(clustered, 50, **FAST)["run"]["p95"]
    narrow = vb.horizon_band(spread, 50, **FAST)["run"]["p95"]
    assert wide > narrow
