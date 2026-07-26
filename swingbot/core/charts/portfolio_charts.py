# swingbot/core/charts/portfolio_charts.py
"""Portfolio survival visuals: heat treemap (E68), correlation heatmap
(E69), Monte Carlo fan (E70), growth path (E71), regime timeline (E72),
fold evidence (E73)."""
from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from swingbot.core.charts.chart_style import (CHART_BG, DISCLAIMER_TEXT,
                                              DOWN_COLOR, GRID_COLOR,
                                              MUTED_TEXT_COLOR, TEXT_COLOR,
                                              UP_COLOR)


def _save(fig, out_dir: str, name: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, name)
    fig.text(0.99, 0.01, DISCLAIMER_TEXT, color=MUTED_TEXT_COLOR, fontsize=6, ha="right")
    fig.savefig(path, facecolor=CHART_BG, bbox_inches="tight")
    plt.close(fig)
    return path


def render_heat_map(open_trades: list, caps: dict, out_dir: str) -> str:
    fig, ax = plt.subplots(figsize=(9, 5), facecolor=CHART_BG, dpi=110)
    ax.set_facecolor(CHART_BG)
    total_cap = caps.get("total", 6.0)
    if not open_trades:
        ax.text(0.5, 0.5, "no open positions", ha="center", va="center",
                color=MUTED_TEXT_COLOR, transform=ax.transAxes)
        ax.set_xticks([]); ax.set_yticks([])
        return _save(fig, out_dir, "heat_treemap.png")

    sectors: dict = {}
    for t in open_trades:
        sectors.setdefault(t.get("sector") or "?", []).append(t)
    x = 0.0
    for sec, ts in sorted(sectors.items(), key=lambda kv: -sum(t["risk_pct"] for t in kv[1])):
        width = sum(t["risk_pct"] for t in ts) / total_cap
        y = 0.0
        for t in sorted(ts, key=lambda t: -t["risk_pct"]):
            h = t["risk_pct"] / sum(p["risk_pct"] for p in ts)
            color = UP_COLOR if t.get("current_r", 0) >= 0 else DOWN_COLOR
            ax.add_patch(plt.Rectangle((x, y), width * 0.97, h * 0.97,
                                       color=color, alpha=0.55))
            ax.text(x + width / 2, y + h / 2,
                    f"{t['ticker']}\n{t['risk_pct']:.1f}% {t.get('current_r', 0):+.1f}R",
                    ha="center", va="center", fontsize=8, color=TEXT_COLOR)
            y += h
        ax.text(x + width / 2, 1.03, sec, ha="center", fontsize=8,
                color=MUTED_TEXT_COLOR)
        x += width
    # headroom to the cap
    if x < 1.0:
        ax.add_patch(plt.Rectangle((x, 0), 1.0 - x, 1.0, color=GRID_COLOR, alpha=0.4))
        ax.text(x + (1 - x) / 2, 0.5, f"free heat\n{(1 - x) * total_cap:.1f}%",
                ha="center", va="center", fontsize=8, color=MUTED_TEXT_COLOR)
    ax.set_xlim(0, 1); ax.set_ylim(0, 1.08)
    ax.set_xticks([]); ax.set_yticks([])
    ax.set_title(f"portfolio heat — cap {total_cap:.1f}%", color=TEXT_COLOR,
                 fontsize=11, loc="left")
    return _save(fig, out_dir, "heat_treemap.png")
