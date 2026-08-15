"""
The GEOMETRY of a scenario's confirming-method overlay, as plain
JSON-serialisable data -- no matplotlib, no axes, no colors.

Every level the bot alerts on was confirmed by some actual method (an
EMA, a Fibonacci ratio, an unfilled fair value gap, a floor pivot, ...),
and the chart draws that method rather than a generic stand-in line.
That computation used to live inside chart_strategy_overlay.py's drawing
branches, which meant the PNG posted to Discord was the ONLY place the
geometry existed. The SPA's interactive chart needs the same numbers
(`GET /api/v1/market/chart/<trade_id>`), and a second implementation of
"where does the 61.8% retracement sit" is a guarantee that the browser
and the image will eventually disagree about it. So the geometry lives
here, once, and chart_strategy_overlay.py is now purely a renderer of
what this module returns.

Contract notes that matter to both consumers:

* Timestamps are int Unix epoch SECONDS (`int(pd.Timestamp(ts).value //
  10**9)`), never bar indices. Bar indices are meaningless to a browser
  that has its own idea of the visible window, and they silently rot
  whenever the chart's display window is expanded (which
  generate_trade_chart does routinely, e.g. to fit both Fibonacci
  anchors on screen). `window_x()` is the ONE place that converts a
  timestamp back into the 0-based x-coordinate the PNG draws in.
* Prices are plain `float`. A numpy scalar or a NaN in here is not a
  type error at import -- it is a 500 from json.dumps() at runtime, so
  undefined values (a rolling window's warm-up bars) are carried as
  `None` and the renderer turns them back into NaN.
* Returning `None` means "nothing drawable" -- no sources, no ranked
  source, or the method could not be computed on this frame (no zigzag
  pivot, no unfilled FVG of that direction, an unknown floor-pivot
  name). This preserves the blanket `except Exception: return False` the
  drawing code has always had: a chart that renders without an overlay
  is much better than a chart that fails to render.
"""
import math
from bisect import bisect_left

import pandas as pd

from .chart_style import DEFAULT_TRENDLINE_LOOKBACK_DAYS, METHOD_PRIORITY
from .chart_drawing import _fib_anchor_points, _floor_pivot_prices
from ..indicators import ema, fibonacci_levels, rolling_vwap, zigzag_pivots
from ..volatility import bollinger_bands
from ..fvg import find_fair_value_gaps_detailed
from ..strategy import compute_hvn_level


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

    Lives here rather than in chart_drawing.py because WHICH source wins
    is a decision about the data, not about matplotlib -- the API has to
    make exactly the same choice the PNG does, and one ranking function
    is the only way to keep that true.
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


# ---------------------------------------------------------------------------
# Time <-> bar-position plumbing
# ---------------------------------------------------------------------------

def bar_epochs(df: pd.DataFrame) -> list:
    """Every bar's timestamp as int Unix epoch seconds, positionally
    aligned with `df`. Built from `pd.Timestamp(ts).value` so tz-aware
    and tz-naive frames produce the same UTC instant."""
    return [int(pd.Timestamp(ts).value // 10 ** 9) for ts in df.index]


def window_x(df: pd.DataFrame, recent_len: int, t: int) -> int:
    """
    Converts an absolute timestamp from a shape back into the 0-based
    x-coordinate the chart draws in, where x=0 is the oldest of the
    `recent_len` visible bars.

    The single home for `bar_index - (len(df) - recent_len)`. That
    arithmetic used to be repeated inline in three of the overlay
    branches with slightly different clamping in each; the offset is
    easy to get subtly wrong and its failure mode (an overlay drawn one
    window-width away from the candle it describes) is invisible until
    someone reads the chart carefully. Can legitimately return a
    NEGATIVE x for a bar older than the visible window -- callers decide
    whether to clamp it (the FVG rectangle) or skip drawing entirely
    (the zigzag pivot marker).
    """
    # Bar timestamps are strictly increasing, so the bisect is exact for
    # any `t` this module itself produced.
    return bisect_left(bar_epochs(df), t) - (len(df) - recent_len)


def _price(value) -> float | None:
    """A plain finite float, or None for anything JSON cannot carry
    (NaN from a rolling window's warm-up bars, numpy masked values)."""
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


# ---------------------------------------------------------------------------
# The shapes
# ---------------------------------------------------------------------------

def _curve_shape(df: pd.DataFrame, recent_len: int, series: pd.Series, label: str) -> dict:
    """
    An indicator line as `recent_len` [t, price] points.

    The series is computed over the FULL frame and only then sliced to
    the visible tail -- an EMA over just the 20 visible bars is a
    different number from an EMA over all history, and the chart must
    show the one the scan actually used. Warm-up bars with no value
    (Donchian shifts a 20-bar rolling window) carry None, not NaN.
    """
    values = series.tail(recent_len).values
    stamps = bar_epochs(df)[-recent_len:]
    return {
        "kind": "curve",
        "label": label,
        "points": [[t, _price(v)] for t, v in zip(stamps, values)],
    }


def _fib_fan_shape(df: pd.DataFrame, source: str, fib_lookback: int) -> dict:
    """
    The whole retracement fan plus which member of it confirmed the
    level -- the chart draws every ratio as a faint reference line with
    the matching one bolder, because a lone horizontal line at 61.8%
    tells the reader nothing about the swing it was measured from.

    `origin`/`anchor` are the real (bar, price) 0%/100% anchors from
    `_fib_anchor_points`; `fibonacci_levels` itself only returns the two
    swing PRICES, not which bar each came from.

    A "Swing high"/"Swing low" source is the same fan with the ANCHOR
    matched instead of a ratio -- so `matched` can name a ratio label,
    an anchor label, or (for a Fib label that matches no ratio at all)
    be None while the fan is still drawn.
    """
    fib = fibonacci_levels(df, fib_lookback)
    anchors = _fib_anchor_points(df, fib_lookback)
    epochs = bar_epochs(df)

    matched = None
    matched_price = None
    ratios = []
    for ratio, price in fib["levels"].items():
        label = f"Fib {ratio * 100:.1f}%"
        is_match = label == source
        if is_match:
            matched = label
            matched_price = _price(price)
        ratios.append([float(ratio), _price(price), is_match])

    if source in ("Swing high", "Swing low"):
        matched = source
        matched_price = _price(fib["swing_high"] if source == "Swing high" else fib["swing_low"])

    return {
        "kind": "fib_fan",
        "origin": [epochs[anchors["high_bar_abs"]], _price(anchors["swing_high"])],
        "anchor": [epochs[anchors["low_bar_abs"]], _price(anchors["swing_low"])],
        "ratios": ratios,
        "matched": matched,
        "matched_price": matched_price,
    }


def _trendline_shape(df: pd.DataFrame, side: str, trend_info: dict,
                     trendline_window_bars: int, is_bull: bool,
                     trend_fit: dict = None) -> dict | None:
    """
    The diagonal support/resistance line, CONVERTED from the fit the
    caller already did rather than re-fit here.

    generate_trade_chart() fits the pair once (it needs the entry price
    and the full frame, and it happens before the display window is even
    decided, since the window is then expanded to fit the line's own
    touches). Re-fitting here would be a second source of truth for the
    same line and would drift the moment either side's parameters
    changed -- so a caller that did not fit a line gets None back rather
    than a fabricated one.

    Which side of the fit belongs to which scenario side mirrors
    levels.py's build_scenarios(): a bullish setup targets resistance
    and stops at support, a bearish one the other way round.

    `trend_fit` is the trade's PERSISTED fit (charts/trendline_fit.py). It
    supersedes `trend_info` when present, and for the fit's own side it is
    read as absolute epochs rather than converted: this function's caller in
    the API serves whatever bar range the browser asked for, and converting
    window-relative coordinates against a different frame slides the line
    off its own pivots. The stored points cannot slide, which is what makes
    the SPA's line and the PNG's line the same line.

    The other side has no stored points -- a fit is taken for the side the
    trade rests on -- so it comes from the pair the fit stored verbatim, on
    the conversion path below.
    """
    if trend_fit and trend_fit.get("pair"):
        trend_info = trend_fit["pair"]
        trendline_window_bars = trendline_window_bars or int(
            trend_fit.get("window_bars") or 0)
    if not trend_info:
        return None
    if is_bull:
        side_key = "resistance" if side == "target" else "support"
    else:
        side_key = "support" if side == "target" else "resistance"
    info = trend_info.get(side_key)
    if not info:
        return None

    if trend_fit and trend_fit.get("side") == side_key and trend_fit.get("points"):
        return _stored_trendline_shape(trend_fit, info)

    window_bars = int(trendline_window_bars or trend_info.get("window_bars") or 0)
    if window_bars <= 0 or window_bars > len(df):
        return None

    slope = float(info["slope"])
    intercept = float(info["intercept"])
    epochs = bar_epochs(df)
    start_abs = len(df) - window_bars
    # Same endpoints _draw_trendline() plots: y0 at the first bar of the
    # fit window, y1 at the last, so the API line and the PNG line are
    # the same line.
    p1 = [epochs[start_abs], _price(intercept)]
    p2 = [epochs[-1], _price(slope * (window_bars - 1) + intercept)]

    # Touches arrive from trendlines.strongest_trendline_pair() as
    # (x, price) in the fit window's OWN coordinates, not absolute bar
    # indices -- offset them back onto real bars.
    pivots = []
    for x, price in (info.get("touches") or []):
        pos = start_abs + int(x)
        if 0 <= pos < len(df):
            pivots.append([epochs[pos], _price(price)])

    return {
        "kind": "trendline",
        "p1": p1,
        "p2": p2,
        "pivots": pivots,
        "label": f"Trendline ({info['strength']}x)",
    }


def _stored_trendline_shape(fit: dict, info: dict) -> dict:
    """The persisted fit, as a drawable shape. Every number is copied, not
    derived -- there is exactly one place a trendline is computed and it is
    `charts/trendline_fit.py`.

    `pivots` are NOT the endpoints. `p1`/`p2` are where the drawn segment
    starts and stops, two extrapolated positions at the window edges that no
    candle need ever have visited; the pivots are the bars that actually
    touched the line and earned it the `Nx` in its label. Drawing the ends as
    the diamonds would put two markers under a label reading "(6x)" -- the
    bug trade_chart.py:752-760 records being fixed once already.

    Missing pivots are normal, not an error: fits stored before that key
    existed, and trendlines.py's trendln fallback, both carry no touches. A
    line with no diamonds is the right degradation.
    """
    points = [[int(p["t"]), _price(p["price"])] for p in fit["points"]]
    return {
        "kind": "trendline",
        "p1": points[0],
        "p2": points[-1],
        "pivots": [[int(p["t"]), _price(p["price"])] for p in fit.get("pivots") or []],
        "label": f"Trendline ({int(info.get('strength', fit.get('strength', 0)))}x)",
    }


def _shape_for(df: pd.DataFrame, source: str, h: dict, recent_len: int, side: str,
               trend_info: dict | None, trendline_window_bars: int, is_bull: bool,
               trend_fit: dict | None = None) -> dict | None:
    """Dispatches one confirming-source label to its shape. Branch order
    and every period/window default match what levels.py used to produce
    the level in the first place -- `h` is the scenario's own horizon
    dict, so the drawn method is the method that actually confirmed."""
    n = len(df)
    epochs = bar_epochs(df)
    visible_from = epochs[max(0, n - recent_len)]

    if source.startswith("EMA"):
        period = int(source[3:])
        return _curve_shape(df, recent_len, ema(df["Close"], period), source)

    if source == "VWAP":
        return _curve_shape(df, recent_len, rolling_vwap(df, h.get("vwap_window", 20)), "VWAP")

    if source.startswith("Fib") or source in ("Swing high", "Swing low"):
        return _fib_fan_shape(df, source, h.get("fib_lookback", DEFAULT_TRENDLINE_LOOKBACK_DAYS))

    if source.startswith("Bollinger"):
        bb = bollinger_bands(df, window=20, num_std=2.0)
        return _curve_shape(df, recent_len, bb["upper" if "upper" in source else "lower"], source)

    if source.startswith("Donchian"):
        col = "High" if "high" in source else "Low"
        roll = df[col].rolling(20)
        series = (roll.max() if "high" in source else roll.min()).shift(1)
        return _curve_shape(df, recent_len, series, source)

    if source.startswith("Rolling"):
        # A rolling S/R level is only meaningful over the bars it was
        # measured across, so it is a bounded segment, not an axhline --
        # `full_width` False is what tells the renderer that.
        sr_lookback = h.get("sr_lookback", 20)
        is_res = "resistance" in source
        col = "High" if is_res else "Low"
        roll = df[col].rolling(sr_lookback)
        value = _price((roll.max() if is_res else roll.min()).shift(1).iloc[-1])
        if value is None:
            return None
        return {
            "kind": "horizontal", "price": value,
            "t_from": epochs[max(0, n - sr_lookback)], "t_to": epochs[-1],
            "label": source, "full_width": False,
        }

    if source.startswith("Floor"):
        value = _price(_floor_pivot_prices(df).get(source))
        if value is None:
            return None
        return {
            "kind": "horizontal", "price": value,
            "t_from": visible_from, "t_to": epochs[-1],
            "label": source, "full_width": True,
        }

    if source.startswith("Pivot"):
        # A zigzag pivot is a single point in time, not a level that
        # extends anywhere -- hence its own `marker` kind rather than a
        # zero-length `horizontal`, which would lose the fact that the
        # chart draws it as a lone diamond.
        threshold = h.get("max_risk_pct", 5.0)
        pivot_kind = "high" if "high" in source else "low"
        pivots = [p for p in zigzag_pivots(df, threshold_pct=threshold) if p[2] == pivot_kind]
        if not pivots:
            return None
        bar_idx, price, _kind = pivots[-1]
        price = _price(price)
        if price is None or not 0 <= int(bar_idx) < n:
            return None
        return {
            "kind": "marker", "t": epochs[int(bar_idx)], "price": price,
            "label": source, "pivot_kind": pivot_kind,
        }

    if source.startswith("FVG"):
        gaps = find_fair_value_gaps_detailed(df)
        wanted_dir = "bullish" if "bullish" in source else "bearish"
        matches = [g for g in gaps if g["direction"] == wanted_dir]
        if not matches:
            return None
        gap = matches[-1]
        # The zone runs from the third candle of the 3-bar pattern that
        # opened it (that's what `bar_index` is) to the right edge -- an
        # unfilled gap is still unfilled today, which is the whole point
        # of drawing it.
        return {
            "kind": "fvg_zone",
            "t_from": epochs[gap["bar_index"]], "t_to": epochs[-1],
            "price_low": _price(gap["bottom"]), "price_high": _price(gap["top"]),
            "mid": _price(gap["mid"]), "label": source,
        }

    if source.startswith("Volume Profile"):
        hvn = compute_hvn_level(df, h.get("sr_lookback", 20))
        if not hvn:
            return None
        hvn_price, vol_share_pct = hvn
        price = _price(hvn_price)
        if price is None:
            return None
        # The volume share is part of the label, not a separate field:
        # it is what the chart prints, and splitting it would let the
        # PNG and the API round it differently.
        return {
            "kind": "horizontal", "price": price,
            "t_from": visible_from, "t_to": epochs[-1],
            "label": f"{source} ({vol_share_pct:.0f}%)", "full_width": True,
        }

    if source.startswith("Trendline"):
        return _trendline_shape(df, side, trend_info, trendline_window_bars, is_bull,
                                trend_fit)

    return None


def overlay_geometry(df: pd.DataFrame, side: str, sources: list, *, horizon: dict = None,
                     recent_len: int = None, trend_info: dict = None,
                     trendline_window_bars: int = 0, is_bull: bool = True,
                     trend_fit: dict = None) -> dict | None:
    """
    The geometry of the ONE confirming method that gets drawn for this
    scenario side, as plain data.

    `side` is "target" or "stop"; `sources` is the scenario's
    target_sources/stop_sources. `horizon` is the scenario's own horizon
    dict (the same one levels.py used), so periods and windows match
    exactly what produced the level. `recent_len` is how many bars the
    chart shows -- it bounds the `curve` point count and the full-width
    horizontals, and nothing else (every other shape carries the real
    bars it was measured between, in or out of the window).

    `trend_info`/`trendline_window_bars`/`is_bull`/`trend_fit` are only
    consulted for a Trendline source; see `_trendline_shape`. `trend_fit` is
    the trade's stored fit and wins over a live `trend_info` when both are
    passed -- it is the line the trade was planned on and the PNG drew.

    Returns None when nothing is drawable. Callers must handle that --
    it is the normal outcome for a scenario confirmed only by
    candlestick patterns, and for any method the frame is too short to
    compute.
    """
    source = _pick_primary_source(sources or [])
    if source is None:
        return None

    n = len(df)
    if not n:
        return None
    if not recent_len or recent_len > n:
        recent_len = n

    try:
        shape = _shape_for(df, source, horizon or {}, recent_len, side,
                           trend_info, trendline_window_bars, is_bull, trend_fit)
    except Exception:
        # Deliberately blanket, matching the drawing code this was
        # extracted from: an unparseable label, a frame too short for an
        # indicator, a missing column. None means "draw nothing", which
        # every caller already handles; an exception would take the
        # whole chart (or the whole API response) down with it.
        return None

    if shape is None:
        return None
    return {"side": side, "source": source, "shape": shape}
