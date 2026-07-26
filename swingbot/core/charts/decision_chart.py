"""The decision one-pager: everything needed to take or skip a trade on
one image -- daily plan, weekly context, relative strength, regime,
historical outcome distribution, sizing math. Composed of independent
panel functions; every panel degrades to a placeholder when its context
key is missing, because a chart must never cost us an alert."""
from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mplfinance as mpf
import pandas as pd

from swingbot.core.charts.chart_style import (
    AVWAP_COLOR, CHART_BG, DISCLAIMER_TEXT, ENTRY_COLOR, GRID_COLOR, MUTED_TEXT_COLOR,
    PRO_STYLE, STOP_COLOR, TARGET_COLOR, TEXT_COLOR,
)

PANEL_LOOKBACK_BARS = 130


def draw_placeholder(ax, text: str) -> None:
    ax.set_facecolor(CHART_BG)
    ax.text(0.5, 0.5, text, transform=ax.transAxes, ha="center", va="center",
            color=MUTED_TEXT_COLOR, fontsize=9)
    ax.set_xticks([]); ax.set_yticks([])


def _draw_main_panel(ax, daily_df: pd.DataFrame, plan, avwaps=None) -> None:
    part = daily_df.tail(PANEL_LOOKBACK_BARS)
    mpf.plot(part, type="candle", ax=ax, style=PRO_STYLE, warn_too_much_data=10_000)
    levels = [(plan.trigger_price or plan.entry_price, ENTRY_COLOR, "entry"),
              (plan.stop_loss, STOP_COLOR, "stop"),
              (plan.tp1, TARGET_COLOR, "TP1")]
    if getattr(plan, "tp2", None):
        levels.append((plan.tp2, TARGET_COLOR, "TP2"))
    for price, color, label in levels:
        if price:
            ax.axhline(price, color=color, lw=1.1, ls="--", alpha=0.9)
            ax.annotate(f"{label} {price:.2f}", xy=(1.0, price),
                        xycoords=("axes fraction", "data"),
                        fontsize=8, color=color, ha="right", va="bottom")
    part_index = part.index
    for av in (avwaps or []):
        s = av["series"].reindex(part_index).dropna()
        if s.empty:
            continue
        x0 = part_index.get_indexer([s.index[0]])[0]
        xs = range(x0, x0 + len(s))
        ax.plot(list(xs), s.values, color=AVWAP_COLOR, lw=1.2, alpha=0.85)
        ax.annotate("⚓", xy=(x0, s.values[0]), color=AVWAP_COLOR, fontsize=9)
        ax.annotate(f"AVWAP {s.values[-1]:.2f}", xy=(1.0, s.values[-1]),
                    xycoords=("axes fraction", "data"), fontsize=7,
                    color=AVWAP_COLOR, ha="right")
    ax.set_facecolor(CHART_BG)


def render_decision_chart(symbol: str, daily_df: pd.DataFrame, plan,
                          context: dict, out_dir: str) -> str:
    fig = plt.figure(figsize=(16, 9), facecolor=CHART_BG, dpi=110)
    gs = fig.add_gridspec(3, 4, hspace=0.25, wspace=0.18,
                          width_ratios=[1, 1, 1, 0.85])
    ax_main = fig.add_subplot(gs[:, :3])
    ax_weekly = fig.add_subplot(gs[0, 3])
    ax_rs = fig.add_subplot(gs[1, 3])
    ax_info = fig.add_subplot(gs[2, 3])

    _draw_main_panel(ax_main, daily_df, plan, context.get("avwaps"))
    # Later tasks replace these placeholders panel by panel:
    from swingbot.core.charts import decision_panels as panels  # this module, split below
    panels.draw_weekly(ax_weekly, context.get("weekly"))
    panels.draw_rs_strip(ax_rs, context.get("rs"))
    panels.draw_info(ax_info, context.get("sizing"), context.get("quality"))

    fig.suptitle(f"{symbol} — {plan.strategy} ({plan.horizon_key}) {plan.direction}",
                 color=TEXT_COLOR, fontsize=13, x=0.02, ha="left")
    fig.text(0.99, 0.005, DISCLAIMER_TEXT, color=MUTED_TEXT_COLOR,
             fontsize=7, ha="right")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{symbol}_decision.png")
    fig.savefig(path, facecolor=CHART_BG, bbox_inches="tight")
    plt.close(fig)
    return path
