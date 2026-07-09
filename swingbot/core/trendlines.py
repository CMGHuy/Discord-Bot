"""
Volume-confirmed diagonal trendline support/resistance.

Every other method in levels.py finds HORIZONTAL levels (EMAs, VWAP,
Fibonacci retracements, rolling highs/lows ...). Trendlines fill the
gap: a stock in a clean up- or down-channel has a RISING support line
connecting higher lows, not a flat prior-high -- a stale flat level
misses that entirely.

What makes a genuine S/R trendline (the user's definition):
  Support  -- a RISING (or flat) line through swing LOWS where buyers
              stepped in with real conviction: elevated volume at the
              bounce, price reversing upward from that level.
  Resistance -- a FALLING (or flat) line through swing HIGHS where
              sellers stepped in: elevated volume at the rejection,
              price turning back down from that level.

Previous approach (pure trendln library):
  • Only used a short lookback window (the horizon's fib_lookback, often
    30–120 bars). A trendline whose second anchor is 8 months old was
    simply invisible.
  • No volume filter whatsoever. Any geometric coincidence of two closes
    could produce a "trendline", even if neither bar had any buying or
    selling pressure at all.

This rewrite adds a custom primary scanner that fixes both:

  1. FULL HISTORY SCAN
     _volume_confirmed_pivots() scans the ENTIRE available history
     (not a capped window) to find every volume-confirmed swing pivot.
     One anchor can be far back in time -- that's intentional. A
     9-month-old structural low that the stock has respected four times
     since is far more meaningful than two random bars from the last
     3 weeks that happen to share a slope.

  2. VOLUME CONFIRMATION
     A pivot is only accepted as a trendline anchor if its bar's volume
     is at least VOL_MIN_RATIO × the local rolling-average volume at
     that bar. This enforces the S/R definition: real support is where
     buyers actually showed up (elevated volume at the bounce); real
     resistance is where sellers actually showed up (elevated volume at
     the rejection). Pure geometric fits that nobody was trading around
     are excluded.

  3. BEST-FIT LINE SELECTION
     For each valid pivot pair, a line is scored by:
       • Number of other volume-confirmed pivots within TOUCH_TOLERANCE_PCT
         of the line (more independent confirmations = stronger level)
       • Average volume ratio at touch points (stronger market interest)
       • Recency of the most recent touch (stale lines matter less)
     The highest-scoring valid line is returned for each side.

  4. DISPLAY-WINDOW COORDINATE SYSTEM
     Internally the scanner uses absolute bar indices (0 = oldest bar
     in df, len(df)-1 = today). Before returning geometry to trade_chart
     the slope/intercept are converted into the chart's own display-window
     coordinate system (0 = leftmost visible bar, window_bars-1 = today).
     This means the chart does NOT need to expand to show the full
     multi-year history just to render a trendline anchored there -- the
     visible segment is what matters, and matplotlib clips it naturally.

trendln (original library) is kept as a FALLBACK for tickers where the
volume filter is too aggressive (no volume data, or very thin markets)
and the custom scanner can't find 2 confirmed pivots per side.
"""
import logging

import numpy as np
import pandas as pd

from .indicators import zigzag_pivots

log = logging.getLogger("swing-bot.trendlines")

try:
    import trendln
    _TRENDLN_AVAILABLE = True
except ImportError:
    _TRENDLN_AVAILABLE = False
    log.info(
        "trendln not installed -- volume-confirmed custom scanner is the "
        "primary method; trendln fallback is disabled."
    )

# ── Tunable constants ──────────────────────────────────────────────────────────

# Minimum bars in df before any trendline attempt is even tried.
MIN_BARS_FOR_TRENDLINE = 30

# Zigzag threshold: % reversal needed for a bar to register as a swing
# high or low. Deliberately LOW so the pivot net is cast wide; the
# volume filter below does the real quality gating. (levels.py's own
# zigzag call uses the horizon's max_risk_pct, which can be much larger.)
PIVOT_THRESHOLD_PCT = 3.0

# Volume confirmation: a pivot is only accepted as a trendline anchor if
# its bar's volume >= this multiple of the local rolling average.
# 1.05 = 5% above average -- lenient enough to avoid over-filtering thin
# markets, strict enough to reject "phantom" pivots nobody was trading.
VOL_MIN_RATIO = 1.05

# Rolling window (bars) for the local volume average.
VOL_ROLLING_WINDOW = 20

# A pivot "touches" a line if its actual price (High for resistance,
# Low for support) is within this % of the line's own value at that bar.
TOUCH_TOLERANCE_PCT = 2.0

# Hard slope cap: prevents lines so steep they'd be useless as swing S/R.
# 0.25% per bar ≈ ~60% annual slope on daily data -- already aggressive;
# anything steeper is more likely a blow-off move than a channel wall.
MAX_SLOPE_PCT_PER_BAR = 0.25

# trendln fallback constants (unchanged from original).
MIN_TRENDLINE_STRENGTH = 3
MAX_TRENDLINES_PER_SIDE = 2

# How many display bars to use for the chart coordinate system.  Mirrors
# DEFAULT_TRENDLINE_LOOKBACK_DAYS in trade_chart.py -- the fit itself
# uses ALL available history, but coordinates returned to the chart are
# expressed relative to this display window so the chart need not expand.
DEFAULT_DISPLAY_BARS = 90


# ── Volume-confirmed pivot scanner ────────────────────────────────────────────

def _volume_confirmed_pivots(df: pd.DataFrame, kind: str) -> list:
    """
    Returns [(bar_index, price, vol_ratio), ...] for all swing pivots of
    `kind` ("high" or "low") where the bar's volume passes the
    VOL_MIN_RATIO threshold against the local rolling average.

    ``price`` is the actual High (for "high" pivots) or Low (for "low"
    pivots) at that bar -- not the closing price the zigzag algorithm
    tracked internally -- because genuine S/R is where buying/selling
    pressure physically stopped the move (the wick extremes), not where
    it happened to close.

    bar_index is the absolute 0-based position into df (0 = oldest bar).
    When volume data is absent or mostly zero the volume filter is
    bypassed so the scanner can still run on index symbols (^GSPC, etc.)
    that carry no volume.
    """
    if len(df) < MIN_BARS_FOR_TRENDLINE:
        return []

    # Check whether usable volume data exists.
    has_volume = False
    vol_avg: pd.Series | None = None
    if "Volume" in df.columns:
        vol = df["Volume"].replace(0, np.nan)
        if vol.count() > len(df) * 0.3:          # at least 30 % non-zero bars
            has_volume = True
            vol_avg = vol.rolling(
                VOL_ROLLING_WINDOW,
                min_periods=max(3, VOL_ROLLING_WINDOW // 4),
            ).mean()

    try:
        all_pivots = zigzag_pivots(df, threshold_pct=PIVOT_THRESHOLD_PCT)
    except Exception:
        return []

    confirmed: list = []
    for bar_idx, _close_price, pkind in all_pivots:
        if pkind != kind or bar_idx >= len(df):
            continue

        # Use High/Low of the pivot bar for line fitting accuracy.
        if kind == "high":
            price = float(df["High"].iloc[bar_idx])
        else:
            price = float(df["Low"].iloc[bar_idx])

        if not has_volume or vol_avg is None:
            # No volume data: accept the pivot without volume gating.
            confirmed.append((bar_idx, price, 1.0))
            continue

        bar_vol = df["Volume"].iloc[bar_idx]
        avg_vol = vol_avg.iloc[bar_idx]
        if pd.isna(bar_vol) or pd.isna(avg_vol) or avg_vol <= 0:
            # Missing local average (can happen at the very start of the
            # series): accept without filtering rather than silently drop.
            confirmed.append((bar_idx, price, 1.0))
        else:
            ratio = float(bar_vol / avg_vol)
            if ratio >= VOL_MIN_RATIO:
                confirmed.append((bar_idx, price, ratio))

    return confirmed


# ── Line scoring ──────────────────────────────────────────────────────────────

def _eval_line(slope: float, intercept: float, bar_idx: int) -> float:
    """Price of the line at absolute bar_idx (0 = oldest bar in df)."""
    return slope * bar_idx + intercept


def _score_candidate(slope: float, intercept: float, pivots: list,
                     n_bars: int, current_price: float, side: str) -> dict | None:
    """
    Validates and scores a candidate trendline (slope/intercept in
    absolute bar-index coordinates).

    Hard gates (return None):
      • Wrong side of current price (support above price / resistance below)
      • Slope too steep (> MAX_SLOPE_PCT_PER_BAR)

    Score (higher = stronger):
      touch_count × avg_vol_ratio × recency_weight
      where recency_weight gives a 40–100 % bonus based on how recently
      the last touch occurred (older lines matter less).
    """
    line_at_now = _eval_line(slope, intercept, n_bars - 1)

    # Side check: 1 % tolerance lets a line that's right at current price
    # still count (it could be the current S/R being tested).
    if side == "support" and line_at_now > current_price * 1.01:
        return None
    if side == "resistance" and line_at_now < current_price * 0.99:
        return None

    # Slope cap.
    if current_price > 0:
        slope_pct = abs(slope / current_price * 100)
        if slope_pct > MAX_SLOPE_PCT_PER_BAR:
            return None

    # Count every pivot (including non-anchor ones) that touches the line.
    touches: list = []
    for bar_idx, price, vol_ratio in pivots:
        line_here = _eval_line(slope, intercept, bar_idx)
        if line_here > 0 and abs(price - line_here) / line_here * 100 <= TOUCH_TOLERANCE_PCT:
            touches.append((bar_idx, price, vol_ratio))

    if len(touches) < 2:
        return None

    avg_vol = sum(v for _, _, v in touches) / len(touches)
    last_touch_bar = max(b for b, _, _ in touches)
    recency = last_touch_bar / max(n_bars - 1, 1)          # 0 … 1
    score = len(touches) * avg_vol * (0.4 + 0.6 * recency)

    return {
        "slope": slope,
        "intercept": intercept,
        "touches": touches,
        "strength": len(touches),
        "score": score,
        "line_at_now": line_at_now,
    }


def _find_best_trendline(df: pd.DataFrame, current_price: float, side: str) -> dict | None:
    """
    Finds the strongest volume-confirmed S/R trendline for `side`
    ("support" or "resistance") by scanning the FULL df history.

    Algorithm:
      1. Collect volume-confirmed swing lows (support) or highs (resistance).
      2. For every pair (i, j) fit the line through their bar_index/price.
      3. Score the line by how many other confirmed pivots also touch it.
      4. Return the highest-scoring valid line, or None.
    """
    kind = "low" if side == "support" else "high"
    pivots = _volume_confirmed_pivots(df, kind)

    if len(pivots) < 2:
        return None

    n_bars = len(df)
    best: dict | None = None

    for i in range(len(pivots)):
        x0, y0, _ = pivots[i]
        for j in range(i + 1, len(pivots)):
            x1, y1, _ = pivots[j]
            if x1 == x0 or y0 <= 0 or y1 <= 0:
                continue
            slope = (y1 - y0) / (x1 - x0)
            intercept = y0 - slope * x0
            result = _score_candidate(slope, intercept, pivots, n_bars, current_price, side)
            if result and (best is None or result["score"] > best["score"]):
                best = result

    return best


# ── Coordinate conversion ─────────────────────────────────────────────────────

def _to_display_coords(line: dict, n_bars_total: int, display_bars: int) -> dict:
    """
    Converts slope/intercept from absolute bar-index coordinates
    (0 = oldest bar in df, n_bars_total-1 = today) into display-window
    coordinates (0 = leftmost visible bar, display_bars-1 = today).

    Slope is unchanged (rate of change per bar, independent of origin).
    Intercept shifts because "x=0" now means a different point in time.

    Also converts `line["touches"]` (the (bar_idx, price, vol_ratio)
    tuples _score_candidate found -- these are what actually earned the
    line its "Nx touch" strength) into the same display-window-relative
    (x, price) coordinates, dropping vol_ratio -- the chart only needs
    where to draw the diamond marker, not the volume that qualified it.
    """
    chart_start_abs = n_bars_total - display_bars
    new_intercept = line["slope"] * chart_start_abs + line["intercept"]
    new_touches = [(bar_idx - chart_start_abs, price) for bar_idx, price, _vol in line.get("touches", [])]
    return {**line, "intercept": new_intercept, "touches": new_touches}


# ── Public API (same signatures as original) ──────────────────────────────────

def trendline_levels(df: pd.DataFrame, lookback: int, current_price: float) -> list:
    """
    Fits volume-confirmed support/resistance trendlines through the FULL
    df history and returns (price, source_label) candidates in the exact
    shape every other levels.py method produces -- 0 to 2 entries.

    ``lookback`` is kept in the signature for API compatibility; the
    actual scan always uses the full df so anchor points can be far apart.
    Falls back to trendln if the custom scanner finds nothing on either side.
    Never raises.
    """
    if len(df) < MIN_BARS_FOR_TRENDLINE or current_price <= 0:
        return []

    candidates: list = []
    for side in ("support", "resistance"):
        try:
            result = _find_best_trendline(df, current_price, side)
            if result:
                candidates.append((
                    float(result["line_at_now"]),
                    f"Trendline ({result['strength']}x touch)",
                ))
        except Exception:
            pass

    # Fallback: trendln when custom scanner finds nothing.
    if not candidates and _TRENDLN_AVAILABLE:
        candidates.extend(_trendln_fallback_levels(df, lookback, current_price))

    return [(p, s) for p, s in candidates if p and p > 0 and not pd.isna(p)]


def strongest_trendline_pair(df: pd.DataFrame, lookback: int,
                              current_price: float) -> dict | None:
    """
    Returns the strongest support and resistance trendline geometry for
    drawing -- slope, intercept, strength, and window_bars -- in display-
    window coordinates (bar 0 = chart's leftmost visible bar).

    Uses the full df for fitting but converts to a display window of
    ``max(lookback, MIN_BARS_FOR_TRENDLINE)`` bars so the chart doesn't
    need to expand to show the full history.  The visible segment is
    extrapolated from wherever in time the anchors actually are.

    Return shape (same as original):
      {"support": {...}|None, "resistance": {...}|None, "window_bars": int}
    where each side: {"slope": float, "intercept": float, "strength": int}
    in display-window bar coordinates.  Returns None if nothing drawable
    was found on either side.
    """
    if len(df) < MIN_BARS_FOR_TRENDLINE or current_price <= 0:
        return None

    display_bars = max(lookback, MIN_BARS_FOR_TRENDLINE, 1)
    display_bars = min(display_bars, len(df))
    n_bars = len(df)

    support_raw: dict | None = None
    resistance_raw: dict | None = None
    try:
        support_raw = _find_best_trendline(df, current_price, "support")
    except Exception:
        pass
    try:
        resistance_raw = _find_best_trendline(df, current_price, "resistance")
    except Exception:
        pass

    # Fall back to trendln when the custom scanner found nothing on both sides.
    if support_raw is None and resistance_raw is None:
        return _strongest_trendline_pair_trendln(df, lookback, current_price)

    # Expand display_bars, if needed, to cover every pivot that actually
    # touches the line -- _find_best_trendline() scores a line by touches
    # found across the FULL df history (that's the whole point: a
    # 9-month-old touch is a real confirmation), but if the display
    # window stayed at its lookback-based default, a touch older than
    # that window would silently fall outside the chart's own x-axis and
    # never get drawn -- the chart would then show e.g. "Trendline (6x)"
    # with only 2-3 diamonds visible, which is exactly the mismatch this
    # closes. Mirrors trade_chart.generate_trade_chart()'s own
    # lookback-expansion logic for the same reason.
    touch_bar_indices = [
        bar_idx
        for raw in (support_raw, resistance_raw)
        if raw is not None
        for bar_idx, _price, _vol in raw["touches"]
    ]
    if touch_bar_indices:
        earliest_touch = min(touch_bar_indices)
        coverage_needed = n_bars - earliest_touch
        display_bars = max(display_bars, min(coverage_needed, n_bars))

    out: dict = {"window_bars": display_bars}

    for key, raw in (("support", support_raw), ("resistance", resistance_raw)):
        if raw is None:
            out[key] = None
        else:
            disp = _to_display_coords(raw, n_bars, display_bars)
            out[key] = {
                "slope": disp["slope"],
                "intercept": disp["intercept"],
                "strength": disp["strength"],
                "touches": disp["touches"],
            }

    return out


# ── trendln fallback ──────────────────────────────────────────────────────────

def _trendln_fallback_levels(df: pd.DataFrame, lookback: int,
                              current_price: float) -> list:
    """Original trendln level-detection, used only when the custom scanner
    finds no volume-confirmed pivots on either side."""
    if not _TRENDLN_AVAILABLE:
        return []
    try:
        window_bars = max(lookback, MIN_BARS_FOR_TRENDLINE)
        window = df.tail(window_bars)
        if len(window) < MIN_BARS_FOR_TRENDLINE:
            return []
        lows = window["Low"].reset_index(drop=True)
        highs = window["High"].reset_index(drop=True)
        if lows.isna().any() or highs.isna().any():
            return []
        last_idx = len(window) - 1
        calc = trendln.calc_support_resistance(
            (lows, highs),
            extmethod=trendln.METHOD_NAIVECONSEC,
            method=trendln.METHOD_NSQUREDLOGN,
        )
        support_lvls, resistance_lvls, _ = trendln.get_levels(
            calc, last_idx, current_price, n=MAX_TRENDLINES_PER_SIDE,
        )
        out: list = []
        for level, strength, _, _ in support_lvls + resistance_lvls:
            if strength >= MIN_TRENDLINE_STRENGTH and level == level and level > 0:
                out.append((float(level), f"Trendline ({strength}x touch)"))
        return out
    except Exception:
        return []


def _strongest_trendline_pair_trendln(df: pd.DataFrame, lookback: int,
                                       current_price: float) -> dict | None:
    """trendln geometry fallback -- same return shape as strongest_trendline_pair."""
    if not _TRENDLN_AVAILABLE:
        return None
    try:
        window_bars = max(lookback, MIN_BARS_FOR_TRENDLINE)
        window = df.tail(window_bars)
        if len(window) < MIN_BARS_FOR_TRENDLINE:
            return None
        window_bars = len(window)
        lows = window["Low"].reset_index(drop=True)
        highs = window["High"].reset_index(drop=True)
        if lows.isna().any() or highs.isna().any():
            return None
        last_idx = window_bars - 1
        calc = trendln.calc_support_resistance(
            (lows, highs),
            extmethod=trendln.METHOD_NAIVECONSEC,
            method=trendln.METHOD_NSQUREDLOGN,
        )
        support_lvls, resistance_lvls, _ = trendln.get_levels(
            calc, last_idx, current_price, n=1,
        )

        def _best(lvls):
            if not lvls:
                return None
            level, strength, slope, intercept = lvls[0]
            if strength < MIN_TRENDLINE_STRENGTH or level != level:
                return None
            return {
                "slope": float(slope),
                "intercept": float(intercept),
                "strength": int(strength),
                # trendln's own get_levels() doesn't expose individual touch
                # coordinates the way the custom scanner's _score_candidate
                # does -- no diamonds to draw in this fallback path, but the
                # key is still present so callers can uniformly do
                # info.get("touches", []) without a fallback-path special case.
                "touches": [],
            }

        support = _best(support_lvls)
        resistance = _best(resistance_lvls)
        if support is None and resistance is None:
            return None
        return {"support": support, "resistance": resistance, "window_bars": window_bars}
    except Exception:
        return None
