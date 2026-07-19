# tests/test_analytics_charts.py
"""Chart-render smoke tests -- every renderer in analytics_charts.py is
(data, out_dir, ...) -> path_to_png. No display backend is needed
(chart_style.py already forces matplotlib's Agg backend); assertions
just confirm a real, non-trivial PNG landed on disk -- pixel-level
content isn't asserted (that's what a human "!stats"/"!calibration"
smoke-check in Task B38 is for)."""
import os

from swingbot.core.charts.analytics_charts import render_equity_curve


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
    assert os.path.getsize(path) > 10_000


def test_render_equity_curve_with_spy_overlay(tmp_path):
    spy = [
        {"date": "2026-01-02", "balance": 1000.0},
        {"date": "2026-01-08", "balance": 1030.0},
    ]
    path = render_equity_curve(_fixture_curve(), str(tmp_path), spy_overlay=spy)
    assert os.path.exists(path)
