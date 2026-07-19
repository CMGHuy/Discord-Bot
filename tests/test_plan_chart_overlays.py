# tests/test_plan_chart_overlays.py
"""Chart-render tests for trade_chart.py's plan_v2= kwarg (risk/reward
bands, trigger arrow, status watermark, chandelier trail) and for
embeds.py's MFE/MAE markers on closed-trade charts. These are smoke
tests (file exists, non-trivial size, no exception) -- pixel content is
not asserted; Task B38's manual smoke pass is where a human actually
looks at one."""
import os
import types
from unittest.mock import patch

import matplotlib.pyplot as plt

from tests.conftest import make_ohlcv
from swingbot.core.charts.trade_chart import generate_trade_chart


def _fixture_plan(entry_type="market", status="ACTIVE", direction="bullish", tp2=118.0):
    return types.SimpleNamespace(
        plan_id="p1", ticker="NVDA", direction=direction, entry_type=entry_type,
        trigger_price=100.0, entry_price=None, stop_loss=95.0, tp1=110.0, tp2=tp2,
        trail_atr_mult=2.5, status=status, strategy="EMA Crossover", horizon_key="4w",
    )


def _fixture_df():
    closes = [100 + i * 0.3 for i in range(60)]
    return make_ohlcv(closes, spread_pct=1.5)


def test_generate_trade_chart_with_plan_renders(tmp_path):
    df = _fixture_df()
    path = generate_trade_chart(
        "NVDA", df, 100.0, 95.0, 110.0, "bullish", "EMA Crossover", "4 Weeks", str(tmp_path),
        filename="with_plan.png", target2=118.0, plan_v2=_fixture_plan(),
    )
    assert os.path.exists(path)
    assert os.path.getsize(path) > 10_000


def test_generate_trade_chart_without_plan_is_unaffected(tmp_path):
    df = _fixture_df()
    path = generate_trade_chart(
        "NVDA", df, 100.0, 95.0, 110.0, "bullish", "EMA Crossover", "4 Weeks", str(tmp_path),
        filename="no_plan.png", target2=118.0,
    )
    assert os.path.exists(path)


def test_pending_stop_entry_plan_renders_with_arrow(tmp_path):
    df = _fixture_df()
    plan = _fixture_plan(entry_type="stop_entry", status="PENDING")
    path = generate_trade_chart(
        "NVDA", df, 100.0, 95.0, 110.0, "bullish", "EMA Crossover", "4 Weeks", str(tmp_path),
        filename="pending_stop_entry.png", target2=118.0, plan_v2=plan,
    )
    assert os.path.exists(path)


def test_market_entry_plan_renders_without_error(tmp_path):
    df = _fixture_df()
    plan = _fixture_plan(entry_type="market", status="ACTIVE")
    path = generate_trade_chart(
        "NVDA", df, 100.0, 95.0, 110.0, "bullish", "EMA Crossover", "4 Weeks", str(tmp_path),
        filename="market_active.png", target2=118.0, plan_v2=plan,
    )
    assert os.path.exists(path)


def test_active_stop_entry_plan_suppresses_trigger_arrow(tmp_path):
    """Task B31 regression pin: a stop-entry plan that has gone ACTIVE has
    already fired its trigger, so the "BUY STOP"/"SELL STOP" arrow (which
    means "still waiting for trigger") must NOT be drawn -- only a PENDING
    stop-entry plan should show it (see
    test_pending_stop_entry_plan_renders_with_arrow above). Before Task
    B31's fix, the annotate call fired for ANY stop_entry plan regardless
    of status, so this exact combination (stop_entry + ACTIVE) would have
    still shown a stale "waiting for trigger" arrow.

    generate_trade_chart() always closes its figure internally
    (`finally: plt.close(fig)`) after saving, so the only way to inspect
    what was actually drawn is to intercept that close call, grab the
    still-populated Figure, inspect it, and close it ourselves.
    """
    df = _fixture_df()
    plan = _fixture_plan(entry_type="stop_entry", status="ACTIVE")
    captured_figs = []
    real_close = plt.close

    def _intercept_close(fig=None, *args, **kwargs):
        # savefig() has already run by the time `finally: plt.close(fig)`
        # executes, so the figure is fully drawn here -- just don't close
        # it yet, so the test can inspect it first.
        if fig is not None:
            captured_figs.append(fig)

    with patch("swingbot.core.charts.trade_chart.plt.close", side_effect=_intercept_close):
        path = generate_trade_chart(
            "NVDA", df, 100.0, 95.0, 110.0, "bullish", "EMA Crossover", "4 Weeks", str(tmp_path),
            filename="active_stop_entry.png", target2=118.0, plan_v2=plan,
        )

    assert os.path.exists(path)
    assert captured_figs, "generate_trade_chart did not call plt.close(fig) as expected"
    fig = captured_figs[0]
    try:
        all_texts = [t.get_text() for ax in fig.axes for t in ax.texts]
        assert not any(word in txt for txt in all_texts for word in ("BUY STOP", "SELL STOP")), (
            f"trigger arrow text found for an ACTIVE stop-entry plan (should be suppressed "
            f"once the trigger has fired): {all_texts}"
        )
    finally:
        real_close(fig)


def test_partial_plan_renders_trail(tmp_path):
    """Task B32: once a plan is PARTIAL, the chandelier runner trail (a
    dotted ax.plot line plus an ax.text(..., " trail", ...) label) should be
    drawn. Intercept plt.close (same pattern as
    test_active_stop_entry_plan_suppresses_trigger_arrow above) to inspect
    the populated Figure before generate_trade_chart's own
    `finally: plt.close(fig)` discards it."""
    df = _fixture_df()
    plan = _fixture_plan(entry_type="market", status="PARTIAL")
    captured_figs = []
    real_close = plt.close

    def _intercept_close(fig=None, *args, **kwargs):
        if fig is not None:
            captured_figs.append(fig)

    with patch("swingbot.core.charts.trade_chart.plt.close", side_effect=_intercept_close):
        path = generate_trade_chart(
            "NVDA", df, 100.0, 95.0, 110.0, "bullish", "EMA Crossover", "4 Weeks", str(tmp_path),
            filename="partial_trail.png", target2=118.0, plan_v2=plan,
        )

    assert os.path.exists(path)
    assert os.path.getsize(path) > 10_000
    assert captured_figs, "generate_trade_chart did not call plt.close(fig) as expected"
    fig = captured_figs[0]
    try:
        all_texts = [t.get_text() for ax in fig.axes for t in ax.texts]
        assert any("trail" in txt for txt in all_texts), (
            f"chandelier trail label (' trail') not found for a PARTIAL plan: {all_texts}"
        )
    finally:
        real_close(fig)


def test_active_plan_has_no_trail_and_still_renders(tmp_path):
    """Companion to test_partial_plan_renders_trail: an ACTIVE (not PARTIAL)
    plan must never draw the chandelier trail, since the whole
    `if plan_v2.status == "PARTIAL":` block -- including the trail code --
    never executes for it."""
    df = _fixture_df()
    plan = _fixture_plan(entry_type="market", status="ACTIVE")
    captured_figs = []
    real_close = plt.close

    def _intercept_close(fig=None, *args, **kwargs):
        if fig is not None:
            captured_figs.append(fig)

    with patch("swingbot.core.charts.trade_chart.plt.close", side_effect=_intercept_close):
        path = generate_trade_chart(
            "NVDA", df, 100.0, 95.0, 110.0, "bullish", "EMA Crossover", "4 Weeks", str(tmp_path),
            filename="active_no_trail.png", target2=118.0, plan_v2=plan,
        )

    assert os.path.exists(path)
    assert captured_figs, "generate_trade_chart did not call plt.close(fig) as expected"
    fig = captured_figs[0]
    try:
        all_texts = [t.get_text() for ax in fig.axes for t in ax.texts]
        assert not any("trail" in txt for txt in all_texts), (
            f"chandelier trail label (' trail') found for an ACTIVE plan (should only "
            f"appear once PARTIAL): {all_texts}"
        )
    finally:
        real_close(fig)


import pandas as pd


def test_markers_render_without_error(tmp_path):
    """Task B33: MFE/MAE markers are drawn via ax.annotate() only for
    marker dates that fall inside the chart's currently-visible `recent`
    window (df.tail(effective_lookback_days) -- see generate_trade_chart's
    markers block, which silently `continue`s on a KeyError from
    recent.index.get_loc() otherwise). With this 60-bar fixture and no
    plan_v2/target_sources/stop_sources passed, effective_lookback_days
    resolves to the plain DEFAULT_LOOKBACK_DAYS=20 (confirmed by calling
    trendlines.strongest_trendline_pair(df, 90, 100.0) directly on this
    exact fixture: it returns None, since neither trendline side finds 2
    volume-confirmed pivots on this synthetic monotonic-close series -- so
    trendline_window_bars/fib_window_bars stay 0 and don't expand the
    window). That makes the visible window df.tail(20) == df.index[40:60],
    so indices 45/50 (unlike the original 30/10) actually land on-screen.

    Same plt.close-interception pattern as
    test_active_stop_entry_plan_suppresses_trigger_arrow /
    test_partial_plan_renders_trail above: capture the populated Figure
    before generate_trade_chart's own `finally: plt.close(fig)` discards
    it, and assert the MFE/MAE annotation text is actually present --
    not just that the file was written."""
    df = _fixture_df()
    mfe_date = df.index[50]
    mae_date = df.index[45]
    markers = {
        "mfe": (mfe_date, float(df["High"].iloc[50])), "mfe_r": 2.0,
        "mae": (mae_date, float(df["Low"].iloc[45])), "mae_r": -0.5,
    }
    captured_figs = []
    real_close = plt.close

    def _intercept_close(fig=None, *args, **kwargs):
        if fig is not None:
            captured_figs.append(fig)

    with patch("swingbot.core.charts.trade_chart.plt.close", side_effect=_intercept_close):
        path = generate_trade_chart(
            "NVDA", df, 100.0, 95.0, 110.0, "bullish", "EMA Crossover", "4 Weeks", str(tmp_path),
            filename="with_markers.png", target2=118.0, markers=markers,
        )

    assert os.path.exists(path)
    assert captured_figs, "generate_trade_chart did not call plt.close(fig) as expected"
    fig = captured_figs[0]
    try:
        all_texts = [t.get_text() for ax in fig.axes for t in ax.texts]
        assert any("MFE" in txt and "+2.0R" in txt for txt in all_texts), (
            f"MFE marker label ('MFE' + '+2.0R') not found -- marker was not actually "
            f"drawn: {all_texts}"
        )
        assert any("MAE" in txt and "-0.5R" in txt for txt in all_texts), (
            f"MAE marker label ('MAE' + '-0.5R') not found -- marker was not actually "
            f"drawn: {all_texts}"
        )
    finally:
        real_close(fig)


def test_no_markers_still_renders(tmp_path):
    df = _fixture_df()
    path = generate_trade_chart(
        "NVDA", df, 100.0, 95.0, 110.0, "bullish", "EMA Crossover", "4 Weeks", str(tmp_path),
        filename="no_markers.png", target2=118.0,
    )
    assert os.path.exists(path)
