"""
Small, self-contained drawing/geometry helpers shared by trade_chart.py's
generate_trade_chart() -- label placement, the two-part branch arrows,
diagonal trendline rendering, and picking which confirming source is
"primary" for a scenario. Split out of trade_chart.py because these are
generic building blocks with no dependency on the rest of that module's
much larger chart-assembly logic.
"""
import pandas as pd

from .chart_style import MIN_LABEL_GAP_FRAC, METHOD_PRIORITY, _label_bbox
from ..indicators import zigzag_pivots


def _spread_labels(items: list, ylim: tuple) -> list:
    """
    items: list of (price, color, text), any order.
    Returns the same items sorted by price, each with an added adjusted
    label y-position that keeps at least MIN_LABEL_GAP_FRAC of the
    visible range between any two labels, without changing the real
    price each line is drawn at.
    """
    if not items:
        return []
    items = sorted(items, key=lambda it: it[0])
    span = max(ylim[1] - ylim[0], 1e-9)
    min_gap = span * MIN_LABEL_GAP_FRAC

    ys = [price for price, _, _ in items]
    for i in range(1, len(ys)):
        if ys[i] - ys[i - 1] < min_gap:
            ys[i] = ys[i - 1] + min_gap

    # If pushing everything up overshot the top of the visible range,
    # shift the whole stack back down -- relative spacing is preserved,
    # so nothing re-collides.
    overflow = ys[-1] - ylim[1]
    if overflow > 0:
        ys = [y - overflow for y in ys]

    return [(items[i][0], ys[i], items[i][1], items[i][2]) for i in range(len(items))]


def _place_strategy_label(ax, x_actual, y_actual, label_x, color, text, va="center",
                           occupied: list = None, min_gap: float = 0.0):
    """
    Draws one confirming-strategy/trendline label -- either directly at
    the real data point (old behavior, when `label_x` is None: used by
    call sites that don't have a dedicated off-candle margin to put it
    in), or, when `label_x` is given, out in a dedicated label column
    away from the candles: a thin dotted leader line from the real point
    back to `(label_x, label_y)`, with the text placed there instead.

    Anchoring every one of these labels at the last candle's x-position
    (the old behavior, unconditionally) is what caused them to sit
    "quite near the candle chart" and sometimes cover the very
    indicator/candle they're annotating -- moving them out to the same
    kind of margin column the entry/stop/target price labels already
    use (see trade_chart.generate_trade_chart's `label_x`) fixes that
    while the leader line keeps it unambiguous which real point each
    label refers to.

    `occupied`, if given, is a running list of y-positions already used
    in this same label column (mutated in place) -- greedily nudges
    `label_y` down by `min_gap` past whichever already-placed label it
    would otherwise land within `min_gap` of, so multiple strategy
    labels sharing one column (e.g. a target overlay AND a stop overlay)
    don't stack on top of each other either. Ignored when `label_x` is
    None (nothing is being moved, so nothing to space out).
    """
    label_y = y_actual
    if label_x is not None and occupied is not None and min_gap > 0:
        bumped = True
        guard = 0
        while bumped and guard < 8:
            bumped = False
            for used_y in occupied:
                if abs(label_y - used_y) < min_gap:
                    label_y = used_y + min_gap
                    bumped = True
            guard += 1
        occupied.append(label_y)

    if label_x is not None:
        if abs(label_x - x_actual) > 1e-9 or abs(label_y - y_actual) > 1e-9:
            ax.plot([x_actual, label_x], [y_actual, label_y], color=color, linewidth=0.9, alpha=0.5,
                    linestyle=":", zorder=5, solid_capstyle="round")
        ax.text(label_x, label_y, f" {text}", color=color, fontsize=8, fontweight="bold",
                va="center", ha="left", zorder=6, bbox=_label_bbox(color))
    else:
        ax.text(x_actual, y_actual, f" {text}", color=color, fontsize=8, fontweight="bold",
                va=va, ha="left", zorder=6, bbox=_label_bbox(color))


def _draw_arrow_leg(ax, x, y_from, y_to, color, label):
    """Draws one smooth curved arrow from y_from to y_to at column x,
    with a rotated label at the midpoint.

    The arc3 connectionstyle gives a gentle rightward bow so multiple
    overlapping legs remain visually distinguishable and the path reads
    as a flowing price movement rather than a rigid ruler line.
    """
    going_up = y_to > y_from
    # Curve slightly toward the right so upward and downward moves look distinct
    rad = 0.25 if going_up else -0.25
    ax.annotate(
        "", xy=(x, y_to), xytext=(x, y_from),
        arrowprops=dict(
            arrowstyle="-|>",
            color=color,
            lw=2.4,
            alpha=0.90,
            shrinkA=3,
            shrinkB=3,
            connectionstyle=f"arc3,rad={rad}",
        ),
        zorder=6,
    )
    mid_y = (y_from + y_to) / 2
    ax.text(
        x + 0.3, mid_y, f" {label}", color=color, fontsize=8, fontweight="bold",
        va="center", ha="left", rotation=90, zorder=6,
    )


def _draw_two_part_branch(ax, x_entry, x_leg2, entry, target1, outcome_price, path_color, outcome_color, outcome_label):
    """
    Draws one full branch of the scenario as two connected arrow legs,
    both starting from the entry point:
      - Part 1 (x_entry): entry -> target 1 -- the move to the next
        support/resistance level. Drawn in the neutral path color since
        this leg is common to every branch.
      - Part 2 (x_leg2): target 1 -> outcome_price -- what happens once
        price gets there (continues to target 2, or reverses to the
        stop), drawn in that branch's own color with its label.
    A short horizontal connector at target 1's height ties the two legs
    together visually so the branch reads as one continuous path from
    entry through the key level to the outcome, not two floating arrows.
    """
    _draw_arrow_leg(ax, x_entry, entry, target1, path_color, "to level")
    ax.plot([x_entry, x_leg2], [target1, target1], color=path_color, linewidth=1.4, alpha=0.6, zorder=5)
    _draw_arrow_leg(ax, x_leg2, target1, outcome_price, outcome_color, outcome_label)


def _draw_trendline(ax, recent_len: int, window_bars: int, slope: float, intercept: float, color: str, label: str,
                     touch_points: list = None, label_x: float = None, occupied: list = None, min_gap: float = 0.0):
    """
    Draws one diagonal trendline segment from where its fit window
    starts to today, mapped into the chart's own 0-based x-coordinates.
    `recent_len` (how many bars the chart is actually showing) can be
    larger than `window_bars` (how many bars the trendline's own fit
    used) -- e.g. the 4-week minimum, or a second trendline, needed more
    room than this one did -- so this offsets for that difference
    rather than assuming the two windows are the same size.

    `touch_points`, if given (see `_trendline_touch_points`), are the
    actual swing highs/lows the line was fit through -- drawn as small
    diamond markers along the line, in the line's own window-relative
    x-coordinates. A bare diagonal line doesn't make clear how well- or
    poorly-supported it really is; the touch points do.

    `label_x`/`occupied`/`min_gap` are forwarded straight to
    `_place_strategy_label` -- when `label_x` is given, the label is
    moved off the line's own right endpoint (which sits right at the
    last candle, easy to cover with other overlays) out to that shared
    margin column instead, with a leader line back to the real endpoint.
    """
    offset = recent_len - window_bars  # always >= 0 by construction -- see generate_trade_chart()
    x0, x1 = offset, recent_len - 1
    y0 = slope * 0 + intercept
    y1 = slope * (window_bars - 1) + intercept
    ax.plot([x0, x1], [y0, y1], color=color, linewidth=1.7, linestyle="-.", alpha=0.85, zorder=4)
    if touch_points:
        xs = [offset + x for x, _price in touch_points]
        ys = [price for _x, price in touch_points]
        ax.scatter(xs, ys, color=color, s=55, marker="D", zorder=6, edgecolors="white", linewidths=0.8)
    _place_strategy_label(ax, x1, y1, label_x, color, label, occupied=occupied, min_gap=min_gap)


def _trendline_touch_points(df: pd.DataFrame, window_bars: int, slope: float, intercept: float, kind: str,
                             threshold_pct: float, tolerance_pct: float = 2.5) -> list:
    """
    Finds the actual swing highs/lows (see indicators.zigzag_pivots --
    the same pivot detector levels.py's own confluence system uses)
    that sit within `tolerance_pct` of the trendline's own value at
    their bar -- i.e. the real points the line is claiming to connect,
    not just its two endpoints. `kind` is "low" for a support line or
    "high" for a resistance line. Returns (x, price) pairs in the
    trendline's own window-relative x-coordinates (0 = window start),
    ready to pass straight into `_draw_trendline`'s `touch_points`.

    Uses the actual High (resistance) or Low (support) at each pivot bar
    rather than the zigzag's internal close-based price, because genuine
    S/R is where buying/selling pressure physically stopped the move --
    the wick extremes -- not where it happened to close.
    """
    try:
        pivots = zigzag_pivots(df, threshold_pct=threshold_pct)
    except Exception:
        return []
    window_start = len(df) - window_bars
    price_col = "Low" if kind == "low" else "High"
    touches = []
    for bar_idx, _close_price, pkind in pivots:
        if pkind != kind or bar_idx < window_start:
            continue
        x = bar_idx - window_start
        line_price = slope * x + intercept
        # Use High/Low at the bar for the touch comparison -- the new
        # trendline fitter also fits through High/Low, so this keeps
        # the detection consistent with how the line was actually built.
        actual_price = float(df[price_col].iloc[bar_idx]) if bar_idx < len(df) else _close_price
        if line_price and abs(actual_price - line_price) / line_price * 100 <= tolerance_pct:
            touches.append((x, actual_price))
    return touches


def _pick_primary_source(sources: list) -> str | None:
    """
    Picks the single most visually informative confirming method from a
    scenario's target_sources/stop_sources to actually draw on the
    chart (see METHOD_PRIORITY) -- drawing every clustered source at
    once would be unreadable, and flat generic sources add little over
    the horizontal target/stop line already shown. Bonus, non-level
    sources confidence.py may have appended (a candlestick pattern
    name, "Bollinger Squeeze Breakout") aren't real price levels and
    are never picked. Returns None if nothing drawable is present, so
    the caller can fall back to the old plain-trendline behavior.
    """
    if not sources:
        return None

    def _rank(label):
        for i, key in enumerate(METHOD_PRIORITY):
            if label.startswith(key):
                return i
        return None

    ranked = [(r, s) for s in sources for r in [_rank(s)] if r is not None]
    if not ranked:
        return None
    ranked.sort(key=lambda t: t[0])
    return ranked[0][1]


def _floor_pivot_prices(df: pd.DataFrame) -> dict:
    """Classic floor trader pivots off the most recently completed bar -- same formula as levels.py."""
    prev = df.iloc[-2] if len(df) > 1 else df.iloc[-1]
    pp = (prev["High"] + prev["Low"] + prev["Close"]) / 3
    span = prev["High"] - prev["Low"]
    return {"Floor Pivot": pp, "Floor R1": pp + span, "Floor S1": pp - span,
            "Floor R2": pp + span * 1.5, "Floor S2": pp - span * 1.5}
