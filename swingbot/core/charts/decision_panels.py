"""Right-column panels of the decision chart. Each takes (ax, data) and
must handle data=None with a placeholder -- panels are optional, alerts
are not."""
import mplfinance as mpf

from swingbot.core.charts.chart_style import (CHART_BG, CHIP_EDGE, GRID_COLOR,
                                              MUTED_TEXT_COLOR, PRO_STYLE, TEXT_COLOR)
from swingbot.core.charts.decision_chart import draw_placeholder


def draw_weekly(ax, weekly_ctx):
    draw_placeholder(ax, "weekly context (E58)") if weekly_ctx is None else _weekly(ax, weekly_ctx)


def draw_rs_strip(ax, rs_ctx):
    draw_placeholder(ax, "relative strength (E60)") if rs_ctx is None else _rs(ax, rs_ctx)


def draw_info(ax, sizing_ctx, quality_ctx):
    if sizing_ctx is None and quality_ctx is None:
        draw_placeholder(ax, "sizing & quality (E65/E66)")
        return
    _info(ax, sizing_ctx, quality_ctx)


def _weekly(ax, ctx):
    df = ctx["df"].tail(40)
    if len(df) < 5:
        draw_placeholder(ax, "not enough weekly history")
        return
    mpf.plot(df, type="candle", ax=ax, style=PRO_STYLE, warn_too_much_data=10_000)
    for span, alpha in ((10, 0.9), (40, 0.6)):
        ema = ctx["df"]["Close"].ewm(span=span, adjust=False).mean().tail(40)
        ax.plot(range(len(ema)), ema.values, lw=1.0, alpha=alpha, color=TEXT_COLOR)
    for p in ctx.get("pivots", []):
        ax.axhline(p, color=CHIP_EDGE, lw=0.8, ls=":")
    # highlight the live (incomplete) week
    ax.axvspan(len(df) - 1.5, len(df) - 0.5, color=GRID_COLOR, alpha=0.5)
    ax.set_title("weekly", color=MUTED_TEXT_COLOR, fontsize=8, loc="left")
    ax.set_facecolor(CHART_BG)


def _rs(ax, rs_ctx):
    """Implemented in E60."""
    draw_placeholder(ax, "pending")


def _info(ax, sizing_ctx, quality_ctx):
    """Implemented in E65/E66."""
    draw_placeholder(ax, "pending")
