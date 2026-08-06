"""Right-column panels of the decision chart. Each takes (ax, data) and
must handle data=None with a placeholder -- panels are optional, alerts
are not."""
import mplfinance as mpf

from swingbot.core.charts.chart_style import (CHART_BG, CHIP_EDGE, DOWN_COLOR,
                                              GRID_COLOR, MUTED_TEXT_COLOR,
                                              PRO_STYLE, STOP_COLOR, TEXT_COLOR,
                                              UP_COLOR)
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


def _rs(ax, ctx):
    s = ctx["rel_series"].tail(130)
    if s.empty:
        draw_placeholder(ax, "no RS history")
        return
    x = range(len(s))
    ax.plot(x, s.values, color=UP_COLOR, lw=1.0)
    ax.axhline(0.0, color=MUTED_TEXT_COLOR, lw=0.7)
    ax.fill_between(x, s.values, 0, where=(s.values < 0),
                    color=DOWN_COLOR, alpha=0.25)
    pct = ctx.get("percentile")
    if pct is not None:
        ax.set_title(f"RS vs SPY — {pct:.0f}th pct", color=MUTED_TEXT_COLOR,
                     fontsize=8, loc="left")
    ax.set_xticks([]); ax.set_facecolor(CHART_BG)


def _info(ax, sizing_ctx, quality_ctx):
    ax.set_facecolor(CHART_BG)
    ax.set_xticks([]); ax.set_yticks([])
    y = 0.97
    if sizing_ctx:
        rows = [
            ("risk", f"{sizing_ctx['risk_pct']:.2f}%  (min: {sizing_ctx['risk_source']})"),
            ("shares", f"{sizing_ctx['shares']}"),
            ("heat", f"{sizing_ctx['heat_before']:.1f}% → {sizing_ctx['heat_after']:.1f}%"
                     f" / {sizing_ctx['cap']:.1f}%"),
        ]
        if sizing_ctx.get("cluster_note"):
            rows.append(("cluster", sizing_ctx["cluster_note"]))
        over = sizing_ctx["heat_after"] > sizing_ctx["cap"]
        for label, value in rows:
            color = STOP_COLOR if (label == "heat" and over) else TEXT_COLOR
            ax.text(0.04, y, f"{label:<8}", transform=ax.transAxes, fontsize=8,
                    color=MUTED_TEXT_COLOR, family="monospace", va="top")
            ax.text(0.30, y, value, transform=ax.transAxes, fontsize=8,
                    color=color, family="monospace", va="top")
            y -= 0.11
    if quality_ctx:
        y = _quality_rows(ax, quality_ctx, y)      # E66


def _quality_rows(ax, q, y):
    ax.text(0.04, y, f"quality {q['score']}/100   follow "
            f"{q.get('follow_score') if q.get('follow_score') is not None else '—'}",
            transform=ax.transAxes, fontsize=8, color=TEXT_COLOR,
            family="monospace", va="top")
    y -= 0.11
    for label, pts, mx in q.get("components", []):
        filled = int(round(6 * pts / mx)) if mx else 0
        bar = "▮" * filled + "▯" * (6 - filled)
        ax.text(0.04, y, f"{label:<8}{bar} {pts}/{mx}", transform=ax.transAxes,
                fontsize=7, color=MUTED_TEXT_COLOR, family="monospace", va="top")
        y -= 0.09
    ax.text(0.04, y, f"{q.get('badge', 'WEAK')} · {q.get('badge_stats', '')}",
            transform=ax.transAxes, fontsize=7, color=TEXT_COLOR,
            family="monospace", va="top")
    y -= 0.10
    # E51 gave this panel a trailing "🤖 <advisor verdict>" row, fed by
    # llm-advisor-v5. That plan was deleted unimplemented on 2026-08-06 and
    # nothing else ever produced the key, so the row could not render -- removed
    # with its producer rather than left as a slot for something not coming.
    return y
