"""Structural layout assertions for the generated trade chart.

tests/conftest.py's assert_rendered counts distinct colours -- it answers
"did we draw something" and is blind to WHERE things landed, so every change
in the TradingView restyle (docs/superpowers/plans/2026-08-07-tradingview-
chart-restyle-v10.md) would pass it unchanged. These are the tests that can
actually see layout.
"""
import numpy as np
import pandas as pd
import pytest

# ~85% of suite runtime lives in nine files like this one; excluded from
# the fast tier (scripts/dev/testrun.py fast). See docs/claude/testing-cost.md.
pytestmark = pytest.mark.slow


def _df(periods=300, seed=7):
    """300 bars, not 120, on purpose. The volume-profile overlay widens its own
    lookback to VOLUME_PROFILE_PANEL_LOOKBACK_DAYS (180) and
    compute_volume_profile returns None unless len(df) >= lookback + 2 -- so
    with a 120-bar frame the profile silently never draws and
    test_volume_profile_draws_inside_the_price_pane would be testing nothing.
    """
    idx = pd.bdate_range("2025-01-01", periods=periods)
    close = pd.Series(100 + np.cumsum(np.random.default_rng(seed).normal(0, 1, periods)), index=idx)
    return pd.DataFrame({"Open": close.shift(1).fillna(close), "High": close + 1,
                         "Low": close - 1, "Close": close, "Volume": 1_000_000}, index=idx)


def _render(tmp_path, monkeypatch, **kw):
    """Render a chart and hand back (png_path, figure).

    generate_trade_chart closes its figure in a finally block, so the figure
    has to be grabbed at savefig time. Axes positions and limits stay readable
    after close, which is all these assertions need.
    """
    import matplotlib.figure
    from swingbot.core.charts.trade_chart import generate_trade_chart

    captured = []
    real_savefig = matplotlib.figure.Figure.savefig

    def _spy(self, *a, **k):
        captured.append(self)
        return real_savefig(self, *a, **k)

    monkeypatch.setattr(matplotlib.figure.Figure, "savefig", _spy)

    df = kw.pop("df", None)
    if df is None:
        df = _df()
    last = float(df["Close"].iloc[-1])
    path = generate_trade_chart(
        ticker="TEST", df=df, entry=last, stop_loss=last * 0.95,
        take_profit=last * 1.08, direction="bullish", strategy="RSI",
        horizon_label="2w", out_dir=str(tmp_path), **kw)
    assert path is not None, "generate_trade_chart returned None"
    assert captured, "savefig was never called"
    return path, captured[0]


@pytest.fixture
def chart(tmp_path, monkeypatch):
    return _render(tmp_path, monkeypatch)


def test_renders_at_all(chart):
    """Guards every assertion below against passing on a blank canvas."""
    from tests.conftest import assert_rendered
    path, _ = chart
    assert_rendered(path)


def test_bottom_pane_reaches_the_bottom_of_the_figure(chart):
    """No dead band under the lowest pane. Reads the figure's own axes rather
    than pixel-sniffing the PNG, so it is DPI-independent."""
    _, fig = chart
    lowest = min(ax.get_position().y0 for ax in fig.axes)
    assert lowest <= 0.12, (
        f"lowest pane starts at y0={lowest:.3f}; expected <= 0.12 "
        f"(anything higher is dead space at the bottom of the image)")


def test_candles_fill_most_of_the_price_pane(chart):
    """The x-axis used to be widened ~16 bars past the last candle to reserve a
    strategy-label column, leaving roughly 45% of the price pane empty.

    Bar count is derived from the plotted overlay lines (the Keltner Channel
    addplots span exactly the visible window) rather than hardcoded, since the
    visible window expands to fit a trendline and is not simply len(df)."""
    _, fig = chart
    ax = fig.axes[0]
    x0, x1 = ax.get_xlim()
    line_lens = [len(ln.get_xdata()) for ln in ax.lines if len(ln.get_xdata()) > 2]
    assert line_lens, "no overlay lines found to derive the visible bar count from"
    n_bars = max(line_lens)
    used = n_bars / (x1 - x0)
    assert used >= 0.80, (
        f"candles occupy only {used:.0%} of the price pane x-range "
        f"(xlim spans {x1 - x0:.1f} for {n_bars} bars)")


def test_no_duplicate_price_ladder(chart):
    """The Volume Profile panel used to own a second axis carrying its own
    dense per-bucket price ladder, so every chart printed the price scale
    twice. After the overlay move the price pane must carry exactly one.

    Scoped to axes occupying the PRICE pane's box: mplfinance gives the MACD
    and RSI panels their own left-hand secondary axes, and those are
    legitimate -- they label MACD and RSI values, not prices."""
    _, fig = chart
    price_pos = fig.axes[0].get_position()
    ladders = 0
    for ax in fig.axes:
        pos = ax.get_position()
        same_pane = (abs(pos.y0 - price_pos.y0) < 1e-6
                     and abs(pos.height - price_pos.height) < 1e-6)
        if not same_pane:
            continue
        if any(t.get_text().strip() for t in ax.get_yticklabels()):
            ladders += 1
    assert ladders == 1, (
        f"price pane carries {ladders} price ladders; expected exactly 1")


def test_volume_shares_the_price_pane(chart):
    """chart-init.js:36-40 draws volume as an overlay in the price pane with
    scaleMargins {top: 0.82}, not as a pane of its own."""
    _, fig = chart
    price_pos = fig.axes[0].get_position()
    twins = [ax for ax in fig.axes
             if ax is not fig.axes[0]
             and abs(ax.get_position().y0 - price_pos.y0) < 1e-6
             and abs(ax.get_position().height - price_pos.height) < 1e-6]
    assert twins, "no axes shares the price pane's box; volume is still a separate pane"


def test_indicator_titles_land_on_their_own_panes(chart):
    """The MACD/RSI annotation blocks index fig.axes by hardcoded position, and
    mplfinance returns two axes per panel. Moving volume into the price pane
    shifted every index by two, which silently drew MACD's title onto the RSI
    pane and skipped RSI's entirely -- no assertion noticed, only looking at
    the PNG did. Pin the mapping."""
    _, fig = chart
    macd_texts = " ".join(t.get_text() for t in fig.axes[2].texts)
    rsi_texts = " ".join(t.get_text() for t in fig.axes[4].texts)
    assert "MACD" in macd_texts, f"axes[2] is not the MACD pane: {macd_texts!r}"
    assert "RSI" in rsi_texts, f"axes[4] is not the RSI pane: {rsi_texts!r}"
    assert "RSI" not in macd_texts, "RSI annotations leaked onto the MACD pane"


def test_volume_profile_draws_inside_the_price_pane(chart):
    """TradingView's Volume Profile Visible Range overlays the price pane; it
    does not own a second axis. Detected by its dedicated gold colour."""
    import matplotlib.colors as mcolors
    from swingbot.core.charts.chart_style import VOLUME_PROFILE_COLOR

    _, fig = chart
    want = mcolors.to_rgb(VOLUME_PROFILE_COLOR)
    ax = fig.axes[0]
    found = 0
    for patch in ax.patches:
        try:
            if mcolors.to_rgb(patch.get_facecolor()[:3]) == want:
                found += 1
        except Exception:
            continue
    assert found > 0, "no volume-profile bars found on the price axes"
