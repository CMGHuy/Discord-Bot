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


def render_r_histogram(r_list: list, out_dir: str, filename: str = "r_histogram.png") -> str:
    """Fixed bin edges -3R..+5R at 0.25R width regardless of the actual
    data range -- a stable x-axis across every render means two !stats
    screenshots taken weeks apart are visually comparable, rather than
    each auto-scaling to whatever that particular sample happened to
    span."""
    bins = np.arange(-3.0, 5.0 + 0.25, 0.25)
    fig, ax = _new_dark_axes()

    if r_list:
        wins = [r for r in r_list if r >= 0]
        losses = [r for r in r_list if r < 0]
        ax.hist(losses, bins=bins, color=DOWN_COLOR, alpha=0.85, label=f"Losses (n={len(losses)})")
        ax.hist(wins, bins=bins, color=UP_COLOR, alpha=0.85, label=f"Wins/scratch (n={len(wins)})")
        mean_r = float(np.mean(r_list))
        ax.axvline(mean_r, color=TARGET_COLOR, linewidth=1.8, linestyle="--")
        ax.text(mean_r, ax.get_ylim()[1] * 0.95, f" Expectancy {mean_r:+.2f}R",
               color=TARGET_COLOR, fontsize=9, fontweight="bold", va="top")
    else:
        ax.text(0.5, 0.5, "No R-multiples yet", transform=ax.transAxes, ha="center", va="center",
               color=MUTED_TEXT_COLOR, fontsize=11)

    ax.set_xlabel("R multiple")
    ax.set_ylabel("Trade count")
    ax.set_title("R-Multiple Distribution", color=TEXT_COLOR, fontsize=12, fontweight="bold")
    if r_list:
        ax.legend(loc="upper right", fontsize=8, framealpha=0.9, facecolor=CHIP_BG, edgecolor=SPINE_COLOR, labelcolor=TEXT_COLOR)
    return _save(fig, out_dir, filename)


CALIBRATION_TARGET_WR = 80.0


def render_calibration(deciles: list, out_dir: str, filename: str = "calibration.png") -> str:
    fig, ax = _new_dark_axes()
    if deciles:
        labels = [d["decile"] for d in deciles]
        wrs = [d["win_rate"] for d in deciles]
        colors = [UP_COLOR if wr >= CALIBRATION_TARGET_WR else DOWN_COLOR for wr in wrs]
        bars = ax.bar(labels, wrs, color=colors, alpha=0.9)
        for bar, d in zip(bars, deciles):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1.5, f"n={d['n']}",
                   ha="center", fontsize=7, color=MUTED_TEXT_COLOR)
        ax.axhline(CALIBRATION_TARGET_WR, color=TEXT_COLOR, linewidth=1.2, linestyle="--")
        ax.text(len(labels) - 0.5, CALIBRATION_TARGET_WR + 1.5, f"{CALIBRATION_TARGET_WR:.0f}% target",
               color=TEXT_COLOR, fontsize=8, ha="right")
        ax.set_ylim(0, 105)
    else:
        ax.text(0.5, 0.5, "No quality-scored closed trades yet", transform=ax.transAxes,
               ha="center", va="center", color=MUTED_TEXT_COLOR, fontsize=11)

    ax.set_xlabel("Quality score decile")
    ax.set_ylabel("Realized win rate %")
    ax.set_title("Quality-Score Calibration", color=TEXT_COLOR, fontsize=12, fontweight="bold")
    return _save(fig, out_dir, filename)


def render_strategy_heatmap(rows: list, out_dir: str, *, value: str = "win_rate",
                            filename: str = "strategy_heatmap.png") -> str:
    """Single-column heatmap (one row per strategy, one color-mapped
    column for whichever `value` was asked for) -- diverging red->green,
    centered at 80 for win_rate (the OOS validation bar) or 0 for
    expectancy_r (breakeven)."""
    fig, ax = _new_dark_axes(figsize=(6, max(2.5, 0.5 * len(rows) + 1)))
    if not rows:
        ax.text(0.5, 0.5, "No strategy stats yet", transform=ax.transAxes, ha="center", va="center",
               color=MUTED_TEXT_COLOR, fontsize=11)
        ax.set_title("Strategy Heatmap", color=TEXT_COLOR)
        return _save(fig, out_dir, filename)

    center = 80.0 if value == "win_rate" else 0.0
    values = np.array([[r[value]] for r in rows], dtype=float)
    span = max(abs(values.max() - center), abs(values.min() - center), 1e-6)
    norm = (values - center) / span  # -1..+1, 0 at center

    cmap = plt.get_cmap("RdYlGn")
    ax.imshow(norm, cmap=cmap, vmin=-1, vmax=1, aspect="auto")
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([r["key"] for r in rows], color=TEXT_COLOR, fontsize=9)
    ax.set_xticks([0])
    ax.set_xticklabels([value.replace("_", " ")], color=TEXT_COLOR, fontsize=9)

    for i, r in enumerate(rows):
        val = r[value]
        label = f"{val:.1f}%" if value == "win_rate" else f"{val:+.2f}"
        ax.text(0, i, f"{label}\n(n={r['n']})", ha="center", va="center", fontsize=8,
               color="black" if abs(norm[i, 0]) < 0.6 else "white", fontweight="bold")

    ax.set_title(f"Strategy Heatmap — {value.replace('_', ' ')}", color=TEXT_COLOR, fontsize=12, fontweight="bold")
    return _save(fig, out_dir, filename)
