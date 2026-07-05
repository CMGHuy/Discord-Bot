"""
Draws the ACTUAL confirming method (EMA/VWAP/Fib/Bollinger/Donchian/
Rolling-S-R/Floor-pivot/zigzag-pivot/FVG/Volume-Profile) behind a
scenario's target or stop level, rather than a generic stand-in line --
see trade_chart.generate_trade_chart(), which calls these once for the
"primary" confirming source (full opacity + label) and again for up to a
couple of "secondary" ones (dimmed, no label). Split out of trade_chart.py
since this dispatch-by-label logic is a large, self-contained unit that
doesn't touch the rest of that module's figure-assembly code.
"""
import pandas as pd
from matplotlib.patches import Rectangle

from .chart_style import CHART_BG, DEFAULT_TRENDLINE_LOOKBACK_DAYS, FVG_ZONE_ALPHA, _label_bbox
from .chart_drawing import _floor_pivot_prices, _place_strategy_label
from ..indicators import ema, fibonacci_levels, rolling_vwap, zigzag_pivots
from ..volatility import bollinger_bands
from ..fvg import find_fair_value_gaps_detailed
from ..strategy import compute_hvn_level


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

    try:
        if source_label.startswith("EMA"):
            period = int(source_label[3:])
            curve = ema(df["Close"], period).tail(recent_len).values
            ax.plot(range(recent_len), curve, color=color, linewidth=1.6, alpha=0.85, zorder=4)
            _label(recent_len - 1, curve[-1], source_label)
            return True

        if source_label == "VWAP":
            curve = rolling_vwap(df, h.get("vwap_window", 20)).tail(recent_len).values
            ax.plot(range(recent_len), curve, color=color, linewidth=1.6, alpha=0.85, zorder=4)
            _label(recent_len - 1, curve[-1], "VWAP")
            return True

        if source_label.startswith("Fib") or source_label in ("Swing high", "Swing low"):
            fib = fibonacci_levels(df, h.get("fib_lookback", DEFAULT_TRENDLINE_LOOKBACK_DAYS))
            drew_anything = False
            # The whole retracement fan as faint reference lines, with
            # whichever ratio (or swing high/low anchor) actually
            # confirmed this level drawn bolder -- shows the structure
            # the confirming ratio came from, not just that one number.
            for ratio, price in fib["levels"].items():
                label = f"Fib {ratio * 100:.1f}%"
                is_match = label == source_label
                ax.axhline(price, color=color, linewidth=1.6 if is_match else 0.8,
                           linestyle="--" if is_match else ":", alpha=0.9 if is_match else 0.35, zorder=3)
                if is_match:
                    _label(recent_len - 1, price, label)
                    drew_anything = True
            if source_label in ("Swing high", "Swing low"):
                price = fib["swing_high"] if source_label == "Swing high" else fib["swing_low"]
                ax.axhline(price, color=color, linewidth=1.6, linestyle="--", alpha=0.9, zorder=3)
                _label(recent_len - 1, price, source_label)
                drew_anything = True
            return drew_anything

        if source_label.startswith("Bollinger"):
            bb = bollinger_bands(df, window=20, num_std=2.0)
            curve = bb["upper" if "upper" in source_label else "lower"].tail(recent_len).values
            ax.plot(range(recent_len), curve, color=color, linewidth=1.6, alpha=0.85, linestyle="-.", zorder=4)
            _label(recent_len - 1, curve[-1], source_label)
            return True

        if source_label.startswith("Donchian"):
            col = "High" if "high" in source_label else "Low"
            fn = df[col].rolling(20).max() if "high" in source_label else df[col].rolling(20).min()
            curve = fn.shift(1).tail(recent_len).values
            ax.step(range(recent_len), curve, color=color, linewidth=1.5, alpha=0.8, where="post", zorder=4)
            _label(recent_len - 1, curve[-1], source_label)
            return True

        if source_label.startswith("Rolling"):
            sr_lookback = h.get("sr_lookback", 20)
            is_res = "resistance" in source_label
            col = "High" if is_res else "Low"
            fn = df[col].rolling(sr_lookback).max() if is_res else df[col].rolling(sr_lookback).min()
            value = float(fn.shift(1).iloc[-1])
            window_start_x = max(0, recent_len - sr_lookback)
            ax.plot([window_start_x, recent_len - 1], [value, value], color=color, linewidth=1.8,
                    linestyle="--", alpha=0.85, zorder=4)
            _label(recent_len - 1, value, source_label)
            return True

        if source_label.startswith("Floor"):
            value = _floor_pivot_prices(df).get(source_label)
            if value is None or pd.isna(value):
                return False
            ax.axhline(value, color=color, linewidth=1.6, linestyle="--", alpha=0.85, zorder=4)
            _label(recent_len - 1, value, source_label)
            return True

        if source_label.startswith("Pivot"):
            threshold = h.get("max_risk_pct", 5.0)
            kind = "high" if "high" in source_label else "low"
            pivots = [p for p in zigzag_pivots(df, threshold_pct=threshold) if p[2] == kind]
            if not pivots:
                return False
            bar_idx, price, _kind = pivots[-1]
            x = bar_idx - (len(df) - recent_len)
            if x < 0:
                # The confirming pivot is older than the chart's visible
                # window -- marking it at the left edge would misleadingly
                # place it next to a candle it has nothing to do with, so
                # skip the marker rather than draw something wrong.
                return False
            ax.scatter([x], [price], color=color, s=70, marker="D", zorder=7, edgecolors=CHART_BG, linewidths=1.0)
            _label(x, price, source_label, va="bottom" if kind == "high" else "top")
            return True

        if source_label.startswith("FVG"):
            gaps = find_fair_value_gaps_detailed(df)
            wanted_dir = "bullish" if "bullish" in source_label else "bearish"
            matches = [g for g in gaps if g["direction"] == wanted_dir]
            if not matches:
                return False
            gap = matches[-1]
            x0 = max(0, gap["bar_index"] - (len(df) - recent_len))
            x1 = recent_len - 1
            # A plain data-coordinate rectangle, not axhspan's axes-fraction
            # xmin/xmax -- those are pinned to the axes BOX, not the data,
            # so they'd drift out of place once the chart's xlim is later
            # widened to make room for the arrows/labels on the right.
            ax.add_patch(Rectangle(
                (x0, gap["bottom"]), max(x1 - x0, 0.4), gap["top"] - gap["bottom"],
                facecolor=color, edgecolor="none", alpha=FVG_ZONE_ALPHA, zorder=2,
            ))
            _label(x1, gap["mid"], source_label)
            return True

        if source_label.startswith("Volume Profile"):
            hvn = compute_hvn_level(df, h.get("sr_lookback", 20))
            if not hvn:
                return False
            hvn_price, vol_share_pct = hvn
            ax.axhline(hvn_price, color=color, linewidth=1.8, linestyle="--", alpha=0.85, zorder=4)
            _label(recent_len - 1, hvn_price, f"{source_label} ({vol_share_pct:.0f}%)")
            return True

    except Exception:
        return False

    return False


def _draw_confirmed_strategy_secondary(ax, df: pd.DataFrame, recent_len: int, h: dict,
                                       source_label: str, color: str) -> bool:
    """
    Like _draw_confirmed_strategy() but draws at reduced opacity with no
    label -- used for secondary confirming strategies so the chart stays
    readable while still showing that multiple methods independently
    agree on this level.
    """
    try:
        if source_label.startswith("EMA"):
            period = int(source_label[3:])
            curve = ema(df["Close"], period).tail(recent_len).values
            ax.plot(range(recent_len), curve, color=color, linewidth=1.0,
                    alpha=0.38, zorder=3, linestyle="--")
            return True

        if source_label == "VWAP":
            curve = rolling_vwap(df, h.get("vwap_window", 20)).tail(recent_len).values
            ax.plot(range(recent_len), curve, color=color, linewidth=1.0,
                    alpha=0.38, zorder=3, linestyle="--")
            return True

        if source_label.startswith("Fib"):
            fib = fibonacci_levels(df, h.get("fib_lookback", DEFAULT_TRENDLINE_LOOKBACK_DAYS))
            for ratio, price in fib["levels"].items():
                label = f"Fib {ratio * 100:.1f}%"
                if label == source_label:
                    ax.axhline(price, color=color, linewidth=0.8, linestyle=":",
                               alpha=0.4, zorder=2)
                    return True

        if source_label.startswith("Bollinger"):
            bb = bollinger_bands(df, window=20, num_std=2.0)
            curve = bb["upper" if "upper" in source_label else "lower"].tail(recent_len).values
            ax.plot(range(recent_len), curve, color=color, linewidth=0.9,
                    alpha=0.38, zorder=3, linestyle="-.")
            return True

        if source_label.startswith("Volume Profile"):
            hvn = compute_hvn_level(df, h.get("sr_lookback", 20))
            if hvn:
                ax.axhline(hvn[0], color=color, linewidth=1.0, linestyle=":", alpha=0.4, zorder=2)
                return True

    except Exception:
        pass
    return False
