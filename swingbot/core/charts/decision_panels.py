"""Right-column panels of the decision chart. Each takes (ax, data) and
must handle data=None with a placeholder -- panels are optional, alerts
are not."""
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


def _weekly(ax, weekly_ctx):
    """Implemented in E58."""
    draw_placeholder(ax, "pending")


def _rs(ax, rs_ctx):
    """Implemented in E60."""
    draw_placeholder(ax, "pending")


def _info(ax, sizing_ctx, quality_ctx):
    """Implemented in E65/E66."""
    draw_placeholder(ax, "pending")
