# tests/test_analytics_charts.py
"""Chart-render smoke tests -- every renderer in analytics_charts.py is
(data, out_dir, ...) -> path_to_png. No display backend is needed
(chart_style.py already forces matplotlib's Agg backend); assertions
just confirm a real, non-trivial PNG landed on disk -- pixel-level
content isn't asserted (that's what a human "!stats"/"!calibration"
smoke-check in Task B38 is for)."""
import os

from swingbot.core.charts.analytics_charts import render_calibration, render_equity_curve
import pytest
from tests.conftest import assert_rendered

# ~85% of suite runtime lives in nine files like this one; excluded from
# the fast tier (scripts/dev/testrun.py fast). See docs/claude/testing-cost.md.
pytestmark = pytest.mark.slow


def _fixture_curve():
    return {
        "points": [
            {"date": "2026-01-02", "balance": 1000.0, "pnl": 0.0},
            {"date": "2026-01-05", "balance": 1050.0, "pnl": 50.0},
            {"date": "2026-01-06", "balance": 980.0, "pnl": -70.0},
            {"date": "2026-01-08", "balance": 1120.0, "pnl": 140.0},
        ],
        "skipped_n": 0,
    }


def test_render_equity_curve_writes_a_real_png(tmp_path):
    path = render_equity_curve(_fixture_curve(), str(tmp_path))
    assert os.path.exists(path)
    assert_rendered(path)


def test_render_equity_curve_with_spy_overlay(tmp_path):
    spy = [
        {"date": "2026-01-02", "balance": 1000.0},
        {"date": "2026-01-08", "balance": 1030.0},
    ]
    path = render_equity_curve(_fixture_curve(), str(tmp_path), spy_overlay=spy)
    assert os.path.exists(path)


def test_render_calibration_writes_a_real_png(tmp_path):
    deciles = [
        {"decile": "0-9", "n": 4, "win_rate": 25.0, "expectancy_r": -0.4},
        {"decile": "50-59", "n": 12, "win_rate": 66.7, "expectancy_r": 0.1},
        {"decile": "90-100", "n": 20, "win_rate": 90.0, "expectancy_r": 0.7},
    ]
    path = render_calibration(deciles, str(tmp_path))
    assert os.path.exists(path)
    assert_rendered(path)


def test_save_stamps_disclaimer(tmp_path):
    """render_equity_curve/render_calibration/etc. are posted to Discord via
    commands/stats.py -- same disclaimer requirement as every other chart
    type. _save() was the one save path in this module missing it."""
    import matplotlib.pyplot as plt
    from swingbot.core.charts.analytics_charts import _save
    from swingbot.core.charts.chart_style import DISCLAIMER_TEXT

    fig, ax = plt.subplots()
    _save(fig, str(tmp_path), "test.png")
    assert any(t.get_text() == DISCLAIMER_TEXT for t in fig.texts)
