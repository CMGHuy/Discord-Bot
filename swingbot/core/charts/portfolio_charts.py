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


def render_corr_matrix(open_trades: list, dfs: dict, out_dir: str) -> str:
    from swingbot.core.edge.correlation import DEFAULT_THRESHOLD, returns_corr
    tickers = [t["ticker"] for t in open_trades if t["ticker"] in dfs]
    n = len(tickers)
    fig, ax = plt.subplots(figsize=(1.2 * max(n, 4), 1.0 * max(n, 4)),
                           facecolor=CHART_BG, dpi=110)
    ax.set_facecolor(CHART_BG)
    if n < 2:
        ax.text(0.5, 0.5, "need 2+ open positions", ha="center", va="center",
                color=MUTED_TEXT_COLOR, transform=ax.transAxes)
        ax.set_xticks([]); ax.set_yticks([])
        return _save(fig, out_dir, "corr_matrix.png")
    m = np.eye(n)
    for i in range(n):
        for j in range(i + 1, n):
            c = returns_corr(dfs[tickers[i]], dfs[tickers[j]]) or 0.0
            m[i, j] = m[j, i] = c
    im = ax.imshow(m, cmap="RdYlGn_r", vmin=-1, vmax=1)
    for i in range(n):
        for j in range(n):
            ax.text(j, i, f"{m[i, j]:.2f}", ha="center", va="center",
                    fontsize=7, color=TEXT_COLOR)
            if i != j and m[i, j] > DEFAULT_THRESHOLD:
                ax.add_patch(plt.Rectangle((j - 0.5, i - 0.5), 1, 1, fill=False,
                                           edgecolor=DOWN_COLOR, lw=2))
    ax.set_xticks(range(n), tickers, rotation=45, color=TEXT_COLOR, fontsize=8)
    ax.set_yticks(range(n), tickers, color=TEXT_COLOR, fontsize=8)
    ax.set_title("90d returns correlation — outlined > 0.75", color=TEXT_COLOR,
                 fontsize=10, loc="left")
    fig.colorbar(im, ax=ax, shrink=0.8)
    return _save(fig, out_dir, "corr_matrix.png")


def render_mc_fan(sim_result: dict, start_balance: float, out_dir: str,
                  percentile_paths: dict | None = None) -> str:
    fig, ax = plt.subplots(figsize=(10, 5.5), facecolor=CHART_BG, dpi=110)
    ax.set_facecolor(CHART_BG)
    if percentile_paths:
        n = len(percentile_paths["p50"])
        xs = range(n)
        bal = lambda path: [start_balance * m for m in path]
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


def render_growth_path(equity_curve: list, out_dir: str, target: float = 10.0,
                       horizons_years: tuple = (3, 5, 8)) -> str:
    import datetime as dt
    fig, ax = plt.subplots(figsize=(10, 5.5), facecolor=CHART_BG, dpi=110)
    ax.set_facecolor(CHART_BG)
    dates = [dt.date.fromisoformat(str(d)[:10]) for d, _ in equity_curve]
    values = [v for _, v in equity_curve]
    start = values[0]
    ax.plot(dates, values, color=UP_COLOR, lw=1.6, label="actual")
    for years in horizons_years:
        daily = target ** (1 / (years * 365.25))
        ref_dates = [dates[0] + dt.timedelta(days=i)
                     for i in range(0, years * 366, 14)]
        ax.plot(ref_dates, [start * daily ** (d - dates[0]).days for d in ref_dates],
                lw=0.9, ls="--", alpha=0.6, color=MUTED_TEXT_COLOR)
        ax.annotate(f"10x in {years}y", xy=(ref_dates[-1], start * target),
                    fontsize=7, color=MUTED_TEXT_COLOR)
    ax.plot([dates[-1]], [values[-1]], "o", color=TEXT_COLOR)
    ax.annotate(f"{values[-1] / start:.2f}x", xy=(dates[-1], values[-1]),
                color=TEXT_COLOR, fontsize=9, va="bottom")
    ax.set_yscale("log")
    ax.grid(color=GRID_COLOR, lw=0.4)
    ax.tick_params(colors=MUTED_TEXT_COLOR)
    ax.set_title("growth path vs required rates", color=TEXT_COLOR, fontsize=10, loc="left")
    ax.legend(loc="upper left", fontsize=8)
    return _save(fig, out_dir, "growth_path.png")
