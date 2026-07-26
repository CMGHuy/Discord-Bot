import os

import matplotlib
matplotlib.use("Agg")

import numpy as np
import pytest

from tests.conftest import make_trend_df


class FakePlan:
    direction = "bullish"
    entry_price = None
    trigger_price = 108.0
    stop_loss = 104.0
    tp1 = 111.0
    tp2 = 114.0
    strategy = "Support/Resistance"
    horizon_key = "4w"


@pytest.fixture
def daily_df():
    return make_trend_df(300, +0.15)


def test_skeleton_renders_with_empty_context(tmp_path, daily_df):
    from swingbot.core.charts.decision_chart import render_decision_chart
    path = render_decision_chart("TEST", daily_df, FakePlan(), {}, str(tmp_path))
    assert os.path.exists(path)
    assert os.path.getsize(path) > 10_000       # a real figure, not a stub
    assert path.endswith(".png")


def test_weekly_panel_renders(tmp_path, daily_df):
    from swingbot.core.edge.factors import weekly_frame
    from swingbot.core.charts.decision_chart import render_decision_chart
    ctx = {"weekly": {"df": weekly_frame(daily_df), "pivots": [105.0, 112.0]}}
    path = render_decision_chart("TEST", daily_df, FakePlan(), ctx, str(tmp_path))
    assert os.path.getsize(path) > 10_000
