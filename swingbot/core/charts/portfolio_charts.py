# swingbot/core/charts/portfolio_charts.py
"""Portfolio survival visuals: the Monte Carlo fan (E70), posted by
`!portfolio`. Its siblings from the same plan -- heat treemap (E68),
correlation heatmap (E69), growth path (E71) and fold evidence (E73) --
never gained a caller and were deleted as dead code on 2026-09-11."""
from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from swingbot.core.charts.chart_style import (CHART_BG, DISCLAIMER_TEXT,
                                              GRID_COLOR, MUTED_TEXT_COLOR,
                                              TEXT_COLOR, UP_COLOR)


def _save(fig, out_dir: str, name: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, name)
    fig.text(0.99, 0.01, DISCLAIMER_TEXT, color=MUTED_TEXT_COLOR, fontsize=6, ha="right")
    try:
        fig.savefig(path, facecolor=CHART_BG, bbox_inches="tight")
    finally:
        plt.close(fig)
    return path


def render_mc_fan(sim_result: dict, start_balance: float, out_dir: str,
                  percentile_paths: dict | None = None) -> str:
    fig, ax = plt.subplots(figsize=(10, 5.5), facecolor=CHART_BG, dpi=110)
    ax.set_facecolor(CHART_BG)
    if percentile_paths:
        n = len(percentile_paths["p50"])
        xs = range(n)

        def bal(path):
            return [start_balance * m for m in path]

        ax.fill_between(xs, bal(percentile_paths["p25"]), bal(percentile_paths["p75"]),
                        color=UP_COLOR, alpha=0.18, label="P25–P75")
        for q, ls in (("p05", ":"), ("p95", ":")):
            ax.plot(xs, bal(percentile_paths[q]), color=MUTED_TEXT_COLOR, lw=0.8, ls=ls)
        ax.plot(xs, bal(percentile_paths["p50"]), color=UP_COLOR, lw=1.4, label="median")
        ax.set_yscale("log")
    ax.axhline(start_balance * 10, color=TEXT_COLOR, lw=1.0, ls="--")
    ax.annotate("10x", xy=(0.99, start_balance * 10), xycoords=("axes fraction", "data"),
                color=TEXT_COLOR, fontsize=9, ha="right", va="bottom")
    ax.set_title(f"Monte Carlo — p(10x) {sim_result['p_10x']:.0%}, "
                 f"P95 max drawdown {sim_result['max_dd_p95']:.0%}, "
                 f"p(halve) {sim_result['p_ruin']:.1%}",
                 color=TEXT_COLOR, fontsize=10, loc="left")
    ax.tick_params(colors=MUTED_TEXT_COLOR)
    ax.grid(color=GRID_COLOR, lw=0.4)
    ax.legend(loc="upper left", fontsize=8)
    return _save(fig, out_dir, "mc_fan.png")
