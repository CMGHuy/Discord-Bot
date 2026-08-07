"""
The chart's top-left legend block and its level name/price annotations --
the two systems that replace mplfinance's centered title, its auto-generated
boxed legend, and the old combined "{name} {price}" pills.

Split out of trade_chart.py (already 62 KB) rather than added to it: these
are self-contained text-drawing helpers with no dependency on that module's
figure-assembly state, and they are the parts most likely to be tuned.

Both mirror swingbot/admin/static/chart-init.js, the interactive
lightweight-charts view these PNGs are meant to read like.
"""
from .chart_style import CHART_BG, MUTED_TEXT_COLOR, TEXT_COLOR

LEGEND_X = 0.008
LEGEND_TOP = 0.985
LEGEND_LINE_STEP = 0.042


def _fmt_volume(v) -> str:
    """21_400_000 -> '21.4M'. Discord renders these small; a raw integer is
    unreadable at that size and adds nothing over a rounded magnitude."""
    v = float(v or 0)
    for cutoff, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(v) >= cutoff:
            return f"{v / cutoff:.1f}{suffix}"
    return f"{v:.0f}"


def draw_legend_block(ax, *, ticker, horizon_label, direction_label, ohlc, overlays) -> None:
    """TradingView's top-left legend, in up to three lines:

        KLAC  2-month swing  SHORT
        O 235.55  H 240.12  L 231.08  C 235.55   Vol 21.4M
        EMA35   Fib 38.2%   KC (EMA20 +/-1.5xATR)

    Line 3 is what makes removing mplfinance's boxed legend safe: it names
    every overlay actually drawn. It is omitted entirely when nothing is
    overlaid, rather than rendering an empty row.
    """
    lines = [
        (f"{ticker}   {horizon_label}   {direction_label}", TEXT_COLOR, 11.0, "bold"),
        (f"O {ohlc['open']:,.2f}   H {ohlc['high']:,.2f}   "
         f"L {ohlc['low']:,.2f}   C {ohlc['close']:,.2f}   "
         f"Vol {_fmt_volume(ohlc.get('volume'))}", MUTED_TEXT_COLOR, 8.5, "normal"),
    ]
    if overlays:
        lines.append(("   ".join(overlays), MUTED_TEXT_COLOR, 8.0, "normal"))

    for i, (text, color, size, weight) in enumerate(lines):
        ax.text(LEGEND_X, LEGEND_TOP - i * LEGEND_LINE_STEP, text,
                transform=ax.transAxes, ha="left", va="top",
                fontsize=size, fontweight=weight, color=color, zorder=7,
                bbox=dict(boxstyle="square,pad=0.25", fc=CHART_BG, ec="none", alpha=0.72))


def draw_level(ax, price, name, color, *, y_offset: int = 0, tag_fontsize: float = 9.0) -> None:
    """A plan level rendered the way lightweight-charts' createPriceLine does
    (chart-init.js:8-12): the short name at the LEFT end of the line, the price
    alone on a coloured tag riding the right price axis.

    tag_fontsize defaults ABOVE TradingView's own size on purpose -- these PNGs
    are read in Discord on a phone, where the image is downscaled.

    y_offset is screen-space offset points, not data units, so the collision
    nudge moves only where the tag renders and never the anchor price (and so
    never the level line itself).
    """
    ax.annotate(
        f" {name} ", xy=(0.0, price), xycoords=("axes fraction", "data"),
        xytext=(3, 0), textcoords="offset points", va="center", ha="left",
        fontsize=tag_fontsize - 1.5, fontweight="bold", color=color, zorder=6,
        bbox=dict(boxstyle="square,pad=0.18", fc=CHART_BG, ec="none", alpha=0.7),
        annotation_clip=False,
    )
    ax.annotate(
        f" {price:,.2f} ", xy=(1.0, price), xycoords=("axes fraction", "data"),
        xytext=(2, y_offset), textcoords="offset points", va="center", ha="left",
        fontsize=tag_fontsize, fontweight="bold", color=CHART_BG, zorder=6,
        bbox=dict(boxstyle="round,pad=0.25", fc=color, ec="none"),
        annotation_clip=False,
    )
