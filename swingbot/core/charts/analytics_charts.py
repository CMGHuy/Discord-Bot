# swingbot/core/charts/analytics_charts.py
"""
Stat/analytics charts (equity curve, R-multiple histogram, calibration
decile bars, strategy heatmap) -- distinct from trade_chart.py's
per-trade candlestick charts, but sharing the exact same dark visual
system (chart_style.py's constants) so a !stats screenshot and a scan
alert's chart never look like they came from two different tools.
Every function here follows the same (data, out_dir, **style) -> path
shape and is designed to run inside asyncio.to_thread from command
handlers (see Task B36's async-render audit).
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np

from .chart_style import (
    CHART_BG, CHIP_BG, DOWN_COLOR, GRID_COLOR, MUTED_TEXT_COLOR,
    SPINE_COLOR, TARGET_COLOR, TEXT_COLOR, UP_COLOR,
)

_FIGSIZE = (10, 5)
_DPI = 150


def _new_dark_axes(figsize=_FIGSIZE):
    fig, ax = plt.subplots(figsize=figsize, facecolor=CHART_BG)
    ax.set_facecolor(CHART_BG)
    ax.grid(True, color=GRID_COLOR, linestyle="--", linewidth=0.6, alpha=0.7)
    for spine in ax.spines.values():
        spine.set_color(SPINE_COLOR)
    ax.tick_params(colors=MUTED_TEXT_COLOR, labelsize=8)
    ax.xaxis.label.set_color(TEXT_COLOR)
    ax.yaxis.label.set_color(TEXT_COLOR)
    return fig, ax


def _save(fig, out_dir: str, filename: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, filename)
    try:
        fig.savefig(path, dpi=_DPI, bbox_inches="tight", facecolor=CHART_BG)
    finally:
        plt.close(fig)
    return path


def render_equity_curve(curve: dict, out_dir: str, *, spy_overlay: list = None,
                        filename: str = "equity_curve.png") -> str:
    """curve is Plan A's equity_curve() return shape:
    {"points": [{"date","balance","pnl"}, ...], "skipped_n": int}.
    Drawdown is shaded beneath the equity line itself (peak-to-current
    gap, filled in DOWN_COLOR at low alpha) rather than drawn on a
    separate panel -- for a single balance series, overlaying it directly
    is more legible than a second synced axis."""
    points = curve["points"]
    dates = [np.datetime64(p["date"]) for p in points]
    balances = [p["balance"] for p in points]

    fig, ax = _new_dark_axes()
    ax.plot(dates, balances, color=TARGET_COLOR, linewidth=1.8, marker="o", markersize=3, label="Equity")

    peak = balances[0]
    peaks = []
    for b in balances:
        peak = max(peak, b)
        peaks.append(peak)
    ax.fill_between(dates, balances, peaks, color=DOWN_COLOR, alpha=0.15, step=None, label="Drawdown")

    if spy_overlay:
        spy_dates = [np.datetime64(p["date"]) for p in spy_overlay]
        spy_bal = [p["balance"] for p in spy_overlay]
        # Normalized to the same starting balance as the equity curve so
        # the two lines are visually comparable regardless of SPY's own
        # price scale.
        scale = balances[0] / spy_bal[0] if spy_bal[0] else 1.0
        ax.plot(spy_dates, [b * scale for b in spy_bal], color=MUTED_TEXT_COLOR,
                linestyle="--", linewidth=1.2, alpha=0.8, label="SPY (normalized)")

    ax.set_title("Equity Curve", color=TEXT_COLOR, fontsize=12, fontweight="bold")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    fig.autofmt_xdate()
    legend = ax.legend(loc="upper left", fontsize=8, framealpha=0.9, facecolor=CHIP_BG, edgecolor=SPINE_COLOR, labelcolor=TEXT_COLOR)
    return _save(fig, out_dir, filename)
