# tests/test_analytics_charts.py
"""Chart-render smoke tests -- every renderer in analytics_charts.py is
(data, out_dir, ...) -> path_to_png. No display backend is needed
(chart_style.py already forces matplotlib's Agg backend); assertions
just confirm a real, non-trivial PNG landed on disk -- pixel-level
content isn't asserted (that's what a human "!stats"/"!calibration"
smoke-check in Task B38 is for)."""
import os

from swingbot.core.charts.analytics_charts import render_calibration, render_equity_curve, render_r_histogram, render_strategy_heatmap


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


def test_render_r_histogram_writes_a_real_png(tmp_path):
    r_list = [-1.0, -0.5, 0.3, 0.8, 1.2, 1.5, -1.0, 2.0, 0.5, -0.8]
    path = render_r_histogram(r_list, str(tmp_path))
    assert os.path.exists(path)
    assert os.path.getsize(path) > 10_000


def test_render_r_histogram_empty_list_still_renders(tmp_path):
    path = render_r_histogram([], str(tmp_path), filename="empty.png")
    assert os.path.exists(path)


def test_render_calibration_writes_a_real_png(tmp_path):
    deciles = [
        {"decile": "0-9", "n": 4, "win_rate": 25.0, "expectancy_r": -0.4},
        {"decile": "50-59", "n": 12, "win_rate": 66.7, "expectancy_r": 0.1},
        {"decile": "90-100", "n": 20, "win_rate": 90.0, "expectancy_r": 0.7},
    ]
    path = render_calibration(deciles, str(tmp_path))
    assert os.path.exists(path)
    assert os.path.getsize(path) > 10_000


def _fixture_rows():
    return [
        {"key": "EMA Crossover", "n": 15, "win_rate": 73.3, "expectancy_r": 0.4, "wins": 11, "losses": 4, "avg_r": 0.4, "profit_factor": 2.0, "total_pnl": 1500.0},
        {"key": "Fibonacci", "n": 20, "win_rate": 85.0, "expectancy_r": 0.6, "wins": 17, "losses": 3, "avg_r": 0.6, "profit_factor": 3.0, "total_pnl": 2400.0},
    ]


def test_render_strategy_heatmap_win_rate(tmp_path):
    path = render_strategy_heatmap(_fixture_rows(), str(tmp_path))
    assert os.path.exists(path)
    assert os.path.getsize(path) > 8_000


def test_render_strategy_heatmap_expectancy(tmp_path):
    path = render_strategy_heatmap(_fixture_rows(), str(tmp_path), value="expectancy_r", filename="heatmap_exp.png")
    assert os.path.exists(path)
