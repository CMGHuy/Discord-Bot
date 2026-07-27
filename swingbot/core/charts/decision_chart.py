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
    PRO_STYLE, STOP_COLOR, TARGET_COLOR, TEXT_COLOR, UP_COLOR,
)

PANEL_LOOKBACK_BARS = 130
OUTCOME_MIN_SAMPLES = 20

REGIME_SHADE = {"bull_quiet": (UP_COLOR, 0.05), "bull_volatile": (UP_COLOR, 0.12),
                "bear_quiet": (STOP_COLOR, 0.05), "bear_volatile": (STOP_COLOR, 0.12)}


def draw_placeholder(ax, text: str) -> None:
    ax.set_facecolor(CHART_BG)
    ax.text(0.5, 0.5, text, transform=ax.transAxes, ha="center", va="center",
            color=MUTED_TEXT_COLOR, fontsize=9)
    ax.set_xticks([]); ax.set_yticks([])


def _draw_main_panel(ax, daily_df: pd.DataFrame, plan, avwaps=None, regimes=None,
                     outcomes=None, ev_cone=None, gap=None) -> None:
    part = daily_df.tail(PANEL_LOOKBACK_BARS)
    if regimes is not None:
        r = regimes.reindex(part.index).ffill()
        run_start = 0
        vals = r.values
        for i in range(1, len(vals) + 1):
            if i == len(vals) or vals[i] != vals[run_start]:
                color, alpha = REGIME_SHADE.get(vals[run_start], (GRID_COLOR, 0.0))
                ax.axvspan(run_start - 0.5, i - 0.5, color=color, alpha=alpha, zorder=0)
                run_start = i
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
    if outcomes and len(outcomes) >= OUTCOME_MIN_SAMPLES:
        entry_px = plan.trigger_price or plan.entry_price
        rps = abs(entry_px - plan.stop_loss)
        x0 = len(part) - 1
        sign = 1 if plan.direction == "bullish" else -1
        for o in outcomes:
            ys = [entry_px + sign * r * rps for r in [0.0] + list(o["r_path"])]
            color = TARGET_COLOR if o["outcome"] == "win" else STOP_COLOR
            ax.plot(range(x0, x0 + len(ys)), ys, color=color, alpha=0.10, lw=0.8,
                    zorder=1)
        ax.annotate(f"outcome cloud: {len(outcomes)} past setups",
                    xy=(0.02, 0.02), xycoords="axes fraction",
                    fontsize=7, color=MUTED_TEXT_COLOR)
        ax.set_xlim(0, len(part) + 15)
    if ev_cone:
        entry_px = plan.trigger_price or plan.entry_price
        rps = abs(entry_px - plan.stop_loss)
        sign = 1 if plan.direction == "bullish" else -1
        x0 = len(part) - 1
        def to_px(path):
            return [entry_px + sign * r * rps for r in [0.0] + list(path)]
        lo, mid, hi = (to_px(ev_cone["p25_path"]), to_px(ev_cone["p50_path"]),
                       to_px(ev_cone["p75_path"]))
        xs = list(range(x0, x0 + len(mid)))
        ax.fill_between(xs, lo, hi, color=TARGET_COLOR, alpha=0.12, zorder=1)
        ax.plot(xs, mid, color=TARGET_COLOR, lw=1.0, ls="--", alpha=0.8)
        ax.annotate(f"EV {ev_cone['ev_r']:+.2f}R", xy=(xs[-1], mid[-1]),
                    fontsize=8, color=TARGET_COLOR, ha="left")
    if gap and plan.stop_loss:
        entry_px = plan.trigger_price or plan.entry_price
        band = entry_px * gap["p90_gap_pct"] / 100.0
        ax.axhspan(plan.stop_loss - band, plan.stop_loss + band,
                   color=STOP_COLOR, alpha=0.08, hatch="//", zorder=0)
        label = "P90 overnight gap band"
        if gap.get("gap_fragile"):
            label = "⚠ stop inside gap noise — " + label
        ax.annotate(label, xy=(0.02, plan.stop_loss + band),
                    xycoords=("axes fraction", "data"),
                    fontsize=7, color=STOP_COLOR, va="bottom")
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

    _draw_main_panel(ax_main, daily_df, plan, context.get("avwaps"), context.get("regimes"),
                     context.get("outcomes"), context.get("ev_cone"), context.get("gap"))
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
