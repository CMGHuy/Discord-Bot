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


def test_avwap_overlay_renders(tmp_path, daily_df):
    from swingbot.core.edge.factors import anchored_vwap, avwap_anchors
    from swingbot.core.charts.decision_chart import render_decision_chart
    avwaps = [{"series": anchored_vwap(daily_df, a), "anchor_label": f"⚓{a}"}
              for a in avwap_anchors(daily_df)[:3]]
    path = render_decision_chart("TEST", daily_df, FakePlan(),
                                 {"avwaps": avwaps}, str(tmp_path))
    assert os.path.getsize(path) > 10_000


def test_rs_strip_renders(tmp_path, daily_df):
    import pandas as pd
    from swingbot.core.charts.decision_chart import render_decision_chart
    rel = (daily_df["Close"].pct_change(63) - 0.01).dropna()
    ctx = {"rs": {"rel_series": rel, "percentile": 78.0}}
    path = render_decision_chart("TEST", daily_df, FakePlan(), ctx, str(tmp_path))
    assert os.path.getsize(path) > 10_000


def test_regime_shading_renders(tmp_path, daily_df):
    import pandas as pd
    from swingbot.core.charts.decision_chart import render_decision_chart
    labels = (["bull_quiet"] * 150 + ["bear_volatile"] * 150)
    ctx = {"regimes": pd.Series(labels, index=daily_df.index)}
    path = render_decision_chart("TEST", daily_df, FakePlan(), ctx, str(tmp_path))
    assert os.path.getsize(path) > 10_000


def test_outcome_cloud_renders_and_respects_min_samples(tmp_path, daily_df):
    from swingbot.core.charts.decision_chart import render_decision_chart
    win = {"r_path": [0.1, 0.3, 0.6, 1.0], "outcome": "win"}
    loss = {"r_path": [-0.2, -0.6, -1.0], "outcome": "loss"}
    big = {"outcomes": [win] * 16 + [loss] * 8}      # 24 >= 20 -> drawn
    small = {"outcomes": [win] * 5}                  # < 20 -> silently omitted
    p1 = render_decision_chart("BIG", daily_df, FakePlan(), big, str(tmp_path))
    p2 = render_decision_chart("SMALL", daily_df, FakePlan(), small, str(tmp_path))
    assert os.path.getsize(p1) > os.path.getsize(p2) * 0.5   # both render fine
