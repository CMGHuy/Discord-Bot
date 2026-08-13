"""
Draws the ACTUAL confirming method (EMA/VWAP/Fib/Bollinger/Donchian/
Rolling-S-R/Floor-pivot/zigzag-pivot/FVG/Volume-Profile) behind a
scenario's target or stop level, rather than a generic stand-in line --
see trade_chart.generate_trade_chart(), which calls these once for the
"primary" confirming source (full opacity + label) and again for up to a
couple of "secondary" ones (dimmed, no label). Split out of trade_chart.py
since this dispatch-by-label logic is a large, self-contained unit that
doesn't touch the rest of that module's figure-assembly code.

This module is now purely the RENDERER. Where the level actually sits --
which source outranks which, which bars a Fibonacci fan was measured
between, where an unfilled FVG starts -- comes from
chart_geometry.overlay_geometry() as plain data, because the SPA's chart
endpoint has to draw the same overlay from the same numbers. Anything
that would be equally true of an SVG in a browser belongs there; only
matplotlib styling (linewidths, alphas, zorders, which artist type draws
which shape) belongs here.
"""
import pandas as pd
from matplotlib.patches import Rectangle

from .chart_style import CHART_BG, FVG_ZONE_ALPHA
from .chart_drawing import _place_strategy_label
from .chart_geometry import overlay_geometry, window_x


def _curve_ys(shape: dict) -> list:
    """Curve prices as matplotlib wants them: NaN for the bars the
    indicator isn't defined on yet. The geometry carries those as None
    because JSON has no NaN, and matplotlib's line breaks (rather than
    interpolating across the warm-up) depend on getting a real NaN
    back."""
    return [float("nan") if price is None else price for _t, price in shape["points"]]


def _draw_confirmed_strategy(ax, df: pd.DataFrame, recent_len: int, h: dict, source_label: str, color: str,
                              label_x: float = None, occupied: list = None, min_gap: float = 0.0) -> bool:
    """
    Draws the ACTUAL method behind `source_label` -- the real Fibonacci
    fan, the real unfilled FVG zone, the real VWAP/EMA/Bollinger curve,
    the real Donchian/rolling-S/R/floor-pivot line, or a marker at the
    real zigzag pivot -- instead of a generic stand-in. `h` is the
    scenario's own horizon dict (same one levels.py used), so periods/
    windows match exactly what actually produced this level. Diagonal
    trendlines are handled separately by the caller (they need the
    window-expansion logic generate_trade_chart already does).

    `label_x`/`occupied`/`min_gap`, if given, are forwarded to
    `_place_strategy_label` for every text label below instead of
    anchoring it directly at the last candle -- see that helper's
    docstring for why (keeps the label from covering the candles/other
    overlays it used to sit right on top of).

    Returns True if something was actually drawn, False if this label
    isn't a Trendline and also isn't recognized/couldn't be computed
    (e.g. not enough history) -- callers treat False the same as "fell
    through to the old behavior".
    """
    def _label(x_actual, y_actual, text, va="center"):
        _place_strategy_label(ax, x_actual, y_actual, label_x, color, text, va=va,
                               occupied=occupied, min_gap=min_gap)

    # `side` is only consulted for a Trendline source, and the caller
    # routes those to _draw_side_trendline() before ever reaching here --
    # so "target" is a don't-care, and a Trendline label that somehow did
    # arrive gets no trend_info and falls out as None (False), exactly as
    # it did when this function had no Trendline branch at all.
    geom = overlay_geometry(df, "target", [source_label], horizon=h, recent_len=recent_len)
    if geom is None:
        return False
    try:
        return _render(ax, df, recent_len, geom["shape"], source_label, color, _label)
    except Exception:
        # The blanket except that used to wrap BOTH the geometry and the
        # drawing. overlay_geometry() kept the geometry half of it, but
        # dropping it here would have been a real narrowing: a shape whose
        # price came back None (a Fibonacci fan on a frame with a NaN high,
        # say) hands matplotlib a None and raises, and an exception escaping
        # this function takes down the whole chart render -- inside the scan
        # loop, that is a missing alert rather than a missing overlay.
        return False


def _render(ax, df: pd.DataFrame, recent_len: int, shape: dict, source_label: str,
            color: str, _label) -> bool:
    """The drawing half of `_draw_confirmed_strategy`, split out only so
    the caller's try/except wraps every branch without indenting all of
    them one level deeper."""
    kind = shape["kind"]

    if kind == "curve":
        ys = _curve_ys(shape)
        if source_label.startswith("Donchian"):
            # A Donchian channel only changes when a new extreme prints;
            # a stepped line says that, an interpolated one implies the
            # level drifted between bars.
            ax.step(range(recent_len), ys, color=color, linewidth=1.5, alpha=0.8, where="post", zorder=4)
        elif source_label.startswith("Bollinger"):
            ax.plot(range(recent_len), ys, color=color, linewidth=1.6, alpha=0.85, linestyle="-.", zorder=4)
        else:
            ax.plot(range(recent_len), ys, color=color, linewidth=1.6, alpha=0.85, zorder=4)
        _label(recent_len - 1, ys[-1], shape["label"])
        return True

    if kind == "fib_fan":
        drew_anything = False
        # The whole retracement fan as faint reference lines, with
        # whichever ratio (or swing high/low anchor) actually
        # confirmed this level drawn bolder -- shows the structure
        # the confirming ratio came from, not just that one number.
        for _ratio, price, is_match in shape["ratios"]:
            ax.axhline(price, color=color, linewidth=1.6 if is_match else 0.8,
                       linestyle="--" if is_match else ":", alpha=0.9 if is_match else 0.35, zorder=3)
            if is_match:
                _label(recent_len - 1, price, shape["matched"])
                drew_anything = True
        if shape["matched"] in ("Swing high", "Swing low"):
            # The anchor itself confirmed the level, not one of the
            # ratios -- it gets the bold line the matching ratio would
            # otherwise have had, on top of its diamond below.
            ax.axhline(shape["matched_price"], color=color, linewidth=1.6, linestyle="--", alpha=0.9, zorder=3)
            _label(recent_len - 1, shape["matched_price"], shape["matched"])
            drew_anything = True

        # Mark the actual 0% and 100% anchor points -- the real swing
        # high/low bars the whole fan was measured between, not just
        # their prices as flat reference lines off at the right edge.
        # generate_trade_chart() expands the chart's display window
        # (fib_window_bars) to make sure both anchors fall inside
        # `recent`/`recent_len` before this is called, so the diamond
        # should always land on-chart rather than needing a skip guard
        # the way the older, non-expanding Pivot marker below does.
        for point, marker_label, va in ((shape["origin"], "0%", "bottom"),
                                        (shape["anchor"], "100%", "top")):
            x = window_x(df, recent_len, point[0])
            if x < 0:
                continue  # defensive -- shouldn't happen given the window expansion above
            ax.scatter([x], [point[1]], color=color, s=70, marker="D", zorder=7,
                       edgecolors=CHART_BG, linewidths=1.0)
            _place_strategy_label(ax, x, point[1], None, color, marker_label, va=va)
            drew_anything = True

        # False here means the fan drew nothing at all -- a "Fib" label
        # matching no ratio AND both anchors off-window. Everything else
        # counts as drawn.
        return drew_anything

    if kind == "horizontal":
        price = shape["price"]
        if shape["full_width"]:
            # Floor pivots and the volume-profile HVN are properties of
            # the whole period, not of a bounded stretch of it, so they
            # run edge to edge.
            ax.axhline(price, color=color,
                       linewidth=1.8 if source_label.startswith("Volume Profile") else 1.6,
                       linestyle="--", alpha=0.85, zorder=4)
        else:
            # A rolling S/R level only holds over the bars it was
            # measured across -- an explicit two-point segment, clamped
            # at the left edge when its own lookback reaches further
            # back than the chart shows.
            x0 = max(0, window_x(df, recent_len, shape["t_from"]))
            x1 = window_x(df, recent_len, shape["t_to"])
            ax.plot([x0, x1], [price, price], color=color, linewidth=1.8,
                    linestyle="--", alpha=0.85, zorder=4)
        _label(recent_len - 1, price, shape["label"])
        return True

    if kind == "marker":
        x = window_x(df, recent_len, shape["t"])
        if x < 0:
            # The confirming pivot is older than the chart's visible
            # window -- marking it at the left edge would misleadingly
            # place it next to a candle it has nothing to do with, so
            # skip the marker rather than draw something wrong.
            return False
        ax.scatter([x], [shape["price"]], color=color, s=70, marker="D", zorder=7,
                   edgecolors=CHART_BG, linewidths=1.0)
        _label(x, shape["price"], shape["label"],
               va="bottom" if shape["pivot_kind"] == "high" else "top")
        return True

    if kind == "fvg_zone":
        x0 = max(0, window_x(df, recent_len, shape["t_from"]))
        x1 = window_x(df, recent_len, shape["t_to"])
        # A plain data-coordinate rectangle, not axhspan's axes-fraction
        # xmin/xmax -- those are pinned to the axes BOX, not the data,
        # so they'd drift out of place once the chart's xlim is later
        # widened to make room for the arrows/labels on the right.
        # max(..., 0.4) keeps a gap that only formed on the last bar or
        # two from collapsing to an invisible zero-width sliver.
        ax.add_patch(Rectangle(
            (x0, shape["price_low"]), max(x1 - x0, 0.4), shape["price_high"] - shape["price_low"],
            facecolor=color, edgecolor="none", alpha=FVG_ZONE_ALPHA, zorder=2,
        ))
        _label(x1, shape["mid"], shape["label"])
        return True

    return False


def _draw_confirmed_strategy_secondary(ax, df: pd.DataFrame, recent_len: int, h: dict,
                                       source_label: str, color: str) -> bool:
    """
    Like _draw_confirmed_strategy() but draws at reduced opacity with no
    label -- used for secondary confirming strategies so the chart stays
    readable while still showing that multiple methods independently
    agree on this level.

    Deliberately handles FIVE kinds of source only: EMA, VWAP, a single
    matched Fib ratio, Bollinger and Volume Profile. Everything else --
    Donchian, Rolling, Floor, Pivot, FVG, and the Swing high/low anchors
    -- returns False and draws nothing, because as a dimmed unlabeled
    line they'd be indistinguishable from the horizontal target/stop
    lines already on the chart (or, for the FVG zone and the pivot
    diamond, are far too heavy to be a background hint). The whitelist
    is the feature, not an oversight; widening it changes every chart.
    """
    if not (source_label.startswith("EMA") or source_label == "VWAP"
            or source_label.startswith("Fib") or source_label.startswith("Bollinger")
            or source_label.startswith("Volume Profile")):
        return False

    geom = overlay_geometry(df, "target", [source_label], horizon=h, recent_len=recent_len)
    if geom is None:
        return False
    try:
        return _render_secondary(ax, recent_len, geom["shape"], source_label, color)
    except Exception:
        # Same reasoning as _draw_confirmed_strategy's -- and more so
        # here, since a secondary source is a background hint nobody
        # would miss, while the exception would cost the whole chart.
        return False


def _render_secondary(ax, recent_len: int, shape: dict, source_label: str, color: str) -> bool:
    """The drawing half of `_draw_confirmed_strategy_secondary`."""
    if shape["kind"] == "curve":
        if source_label.startswith("Bollinger"):
            ax.plot(range(recent_len), _curve_ys(shape), color=color, linewidth=0.9,
                    alpha=0.38, zorder=3, linestyle="-.")
        else:
            ax.plot(range(recent_len), _curve_ys(shape), color=color, linewidth=1.0,
                    alpha=0.38, zorder=3, linestyle="--")
        return True

    if shape["kind"] == "fib_fan":
        # Just the one confirming ratio, never the whole fan and never
        # the anchor diamonds -- a second full fan on the same chart is
        # unreadable. A Fib label matching no ratio draws nothing.
        if shape["matched"] != source_label:
            return False
        ax.axhline(shape["matched_price"], color=color, linewidth=0.8, linestyle=":",
                   alpha=0.4, zorder=2)
        return True

    if shape["kind"] == "horizontal":  # Volume Profile only, given the whitelist above
        ax.axhline(shape["price"], color=color, linewidth=1.0, linestyle=":", alpha=0.4, zorder=2)
        return True

    return False
