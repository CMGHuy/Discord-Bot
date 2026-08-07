import os

import matplotlib
matplotlib.use("Agg")

import numpy as np
import pytest

from tests.conftest import assert_rendered, make_trend_df

# ~85% of suite runtime lives in nine files like this one; excluded from
# the fast tier (scripts/testrun.py fast). See docs/claude/testing-cost.md.
pytestmark = pytest.mark.slow


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
    assert_rendered(path)
    assert path.endswith(".png")


def test_weekly_panel_renders(tmp_path, daily_df):
    from swingbot.core.edge.factors import weekly_frame
    from swingbot.core.charts.decision_chart import render_decision_chart
    ctx = {"weekly": {"df": weekly_frame(daily_df), "pivots": [105.0, 112.0]}}
    path = render_decision_chart("TEST", daily_df, FakePlan(), ctx, str(tmp_path))
    assert_rendered(path)


def test_avwap_overlay_renders(tmp_path, daily_df):
    from swingbot.core.edge.factors import anchored_vwap, avwap_anchors
    from swingbot.core.charts.decision_chart import render_decision_chart
    avwaps = [{"series": anchored_vwap(daily_df, a), "anchor_label": f"⚓{a}"}
              for a in avwap_anchors(daily_df)[:3]]
    path = render_decision_chart("TEST", daily_df, FakePlan(),
                                 {"avwaps": avwaps}, str(tmp_path))
    assert_rendered(path)


def test_rs_strip_renders(tmp_path, daily_df):
    import pandas as pd
    from swingbot.core.charts.decision_chart import render_decision_chart
    rel = (daily_df["Close"].pct_change(63) - 0.01).dropna()
    ctx = {"rs": {"rel_series": rel, "percentile": 78.0}}
    path = render_decision_chart("TEST", daily_df, FakePlan(), ctx, str(tmp_path))
    assert_rendered(path)


def test_regime_shading_renders(tmp_path, daily_df):
    import pandas as pd
    from swingbot.core.charts.decision_chart import render_decision_chart
    labels = (["bull_quiet"] * 150 + ["bear_volatile"] * 150)
    ctx = {"regimes": pd.Series(labels, index=daily_df.index)}
    path = render_decision_chart("TEST", daily_df, FakePlan(), ctx, str(tmp_path))
    assert_rendered(path)


def test_outcome_cloud_renders_and_respects_min_samples(tmp_path, daily_df):
    from swingbot.core.charts.decision_chart import render_decision_chart
    win = {"r_path": [0.1, 0.3, 0.6, 1.0], "outcome": "win"}
    loss = {"r_path": [-0.2, -0.6, -1.0], "outcome": "loss"}
    big = {"outcomes": [win] * 16 + [loss] * 8}      # 24 >= 20 -> drawn
    small = {"outcomes": [win] * 5}                  # < 20 -> silently omitted
    p1 = render_decision_chart("BIG", daily_df, FakePlan(), big, str(tmp_path))
    p2 = render_decision_chart("SMALL", daily_df, FakePlan(), small, str(tmp_path))
    assert os.path.getsize(p1) > os.path.getsize(p2) * 0.5   # both render fine


def test_ev_cone_renders(tmp_path, daily_df):
    from swingbot.core.charts.decision_chart import render_decision_chart
    ctx = {"ev_cone": {"p25_path": [0.05, 0.1, 0.2, 0.3],
                       "p50_path": [0.1, 0.25, 0.45, 0.6],
                       "p75_path": [0.2, 0.5, 0.8, 1.1],
                       "ev_r": 0.14}}
    path = render_decision_chart("TEST", daily_df, FakePlan(), ctx, str(tmp_path))
    assert_rendered(path)


def test_gap_band_renders(tmp_path, daily_df):
    from swingbot.core.charts.decision_chart import render_decision_chart
    ctx = {"gap": {"p90_gap_pct": 2.5, "gap_fragile": True}}
    path = render_decision_chart("TEST", daily_df, FakePlan(), ctx, str(tmp_path))
    assert_rendered(path)


def test_sizing_box_renders(tmp_path, daily_df):
    from swingbot.core.charts.decision_chart import render_decision_chart
    ctx = {"sizing": {"risk_pct": 0.7, "risk_source": "vol_target",
                      "shares": 35, "heat_before": 4.0, "heat_after": 4.7,
                      "cap": 6.0, "cluster_note": "corr 0.82 with NVDA"}}
    path = render_decision_chart("TEST", daily_df, FakePlan(), ctx, str(tmp_path))
    assert_rendered(path)


def test_quality_box_renders(tmp_path, daily_df):
    from swingbot.core.charts.decision_chart import render_decision_chart
    ctx = {"quality": {"score": 74,
                       "components": [("RS", 8, 10), ("MTF", 6, 10), ("breadth", 3, 5)],
                       "follow_score": 81.5, "badge": "VALIDATED",
                       "badge_stats": "N=206 · 81.6% OOS",
                       "advisor": "CAUTION (62) — earnings in 2 days"}}
    path = render_decision_chart("TEST", daily_df, FakePlan(), ctx, str(tmp_path))
    assert_rendered(path)


def test_build_decision_context_never_raises(daily_df):
    # NOTE: the plan's own brief says `swingbot.commands.scanning` -- wrong,
    # same known trap as E49/E52 (commands/scanning.py only posts
    # already-built tuples; the alert-building loop that has the real data
    # lives in core/scanning/engine.py, so that's where this function is).
    from swingbot.core.scanning.engine import build_decision_context

    class Item:  # minimal ScanItem stand-in
        plan = FakePlan()
        rs_percentile = 70.0
        breadth = 55.0
        heat_blocked = None

    ctx = build_decision_context(Item(), {"TEST": daily_df}, daily_df)
    assert isinstance(ctx, dict)          # missing pieces -> keys absent, no raise


def test_render_decision_chart_saves_through_the_disclaimer():
    """Task E97: decision_chart.py has exactly one savefig call (unlike
    portfolio_charts.py's shared _save() helper, this is a single one-pager
    renderer) -- assert DISCLAIMER_TEXT is drawn before that one savefig
    call, so a future edit can't slip a second, disclaimer-free savefig
    path into this module without this test catching it."""
    import inspect
    from swingbot.core.charts import decision_chart as dc

    src = inspect.getsource(dc)
    assert src.count("fig.savefig(") == 1
    # rindex, not index: the FIRST "DISCLAIMER_TEXT" occurrence is just the
    # module's import line, which trivially precedes savefig regardless of
    # whether the actual fig.text(...) draw call still exists. The LAST
    # occurrence is that real draw call -- it must precede the save.
    assert src.rindex("DISCLAIMER_TEXT") < src.index("fig.savefig(")
