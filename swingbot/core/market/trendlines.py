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

  1. DEEP HISTORY SCAN
     _volume_confirmed_pivots() scans well beyond any single horizon's
     own lookback (MAX_PIVOT_SCAN_BARS -- 1500 bars, ~6 years of daily
     data) to find every volume-confirmed swing pivot. One anchor can be
     far back in time -- that's intentional. A 9-month-old structural low
     that the stock has respected four times since is far more meaningful
     than two random bars from the last 3 weeks that happen to share a
     slope. It is NOT the entire available history: production's cache
     holds decades for some tickers (45 years for AAPL), and the pairwise
     scan below is O(pivots^3) -- uncapped, that measured 6-9 SECONDS per
     call on real tickers. See MAX_PIVOT_SCAN_BARS's own comment.

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
from dataclasses import dataclass

import numpy as np
import pandas as pd

from swingbot.core.market.indicators import zigzag_pivots

log = logging.getLogger(__name__)

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

# Hard cap on how much history the pairwise trendline scan considers.
# _find_best_trendline is O(P^3) in the pivot count P (all-pairs line fit,
# each scored by an O(P) touch-count pass), and production's actual
# market_data/daily/ cache holds each ticker's FULL history since listing --
# 11,500+ daily bars / 45 years for AAPL, not the 2y DEFAULT_HISTORY_PERIOD.
# Measured live against that real cache: a single support+resistance pass
# took 9.4s for AAPL, 6.9s for AMD -- called once per horizon (10, see
# HORIZONS), that alone was enough to pin a CPU core for minutes per ticker
# and was the dominant cost of the whole scan (v56 CPU incident). Nothing
# this bot trades holds a horizon longer than 9 months, so an anchor beyond
# a few years old buys no real information; 1500 bars (~6 years of daily
# data) stays far beyond that -- comfortably covering this module's own
# "9-month-old anchor" example above -- while capping worst-case cost to
# hundredths of a second even on the oldest tickers (measured: AAPL/AMD
# both drop to ~0.02s at this cap, same trendlines found).
MAX_PIVOT_SCAN_BARS = 1500

# v245 prefix/tail split (index Decision 4): the prefix is the trimmed window
# minus its last row(s); its last pivots are left to the tail. Hit rate only:
# _verified_prefix checks every call that the window's pivots start with it.
TRENDLINE_PREFIX_TAIL_BARS = 1
UNSTABLE_PREFIX_PIVOTS = 2


@dataclass(frozen=True)
class TrendlinePrefix:
    """``confirmed``: (bar_idx, price, vol_ratio) pivots, trimmed-window coordinates.
    ``pairs[i][j - i - 1]`` (i < j): None (skipped pair) or (slope, intercept, touches over confirmed)."""
    side: str
    m: int
    confirmed: tuple
    pairs: tuple


def trimmed_frame(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """(last MAX_PIVOT_SCAN_BARS rows, their start offset in df)."""
    trim_start = max(len(df) - MAX_PIVOT_SCAN_BARS, 0)
    return (df.tail(MAX_PIVOT_SCAN_BARS) if trim_start else df), trim_start


def prefix_length(trimmed: pd.DataFrame) -> int:
    """Rows of the trimmed window the cached prefix covers."""
    return max(len(trimmed) - TRENDLINE_PREFIX_TAIL_BARS, 0)


# ── Volume-confirmed pivot scanner ────────────────────────────────────────────

def _volume_average(df: pd.DataFrame) -> pd.Series | None:
    """The rolling volume mean the pivot filter compares against, or None
    when volume is absent or mostly zero (index symbols: filter bypassed)."""
    if "Volume" not in df.columns:
        return None
    vol = df["Volume"].replace(0, np.nan)
    if vol.count() <= len(df) * 0.3:             # need at least 30 % non-zero bars
        return None
    return vol.rolling(
        VOL_ROLLING_WINDOW,
        min_periods=max(3, VOL_ROLLING_WINDOW // 4),
    ).mean()


def _zigzag_or_empty(df: pd.DataFrame) -> list:
    """zigzag_pivots at the scanner's threshold; a failure means no pivots."""
    try:
        return zigzag_pivots(df, threshold_pct=PIVOT_THRESHOLD_PCT)
    except Exception:
        return []


def _pivot_ratio(df: pd.DataFrame, vol_avg: pd.Series | None, bar_idx: int) -> float | None:
    """The pivot's volume ratio, 1.0 when it cannot be judged, None when it fails."""
    if vol_avg is None:
        return 1.0                               # no volume data: accept ungated
    bar_vol = df["Volume"].iloc[bar_idx]
    avg_vol = vol_avg.iloc[bar_idx]
    if pd.isna(bar_vol) or pd.isna(avg_vol) or avg_vol <= 0:
        # Missing local average (can happen at the very start of the
        # series): accept without filtering rather than silently drop.
        return 1.0
    ratio = float(bar_vol / avg_vol)
    return ratio if ratio >= VOL_MIN_RATIO else None


def _volume_confirmed_pivots(df: pd.DataFrame, kind: str, all_pivots: list | None = None) -> list:
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

    ``all_pivots``: ``zigzag_pivots(df, threshold_pct=PIVOT_THRESHOLD_PCT)``
    of this same ``df`` when the caller already has it (both trendline sides
    share one, v245); None computes it here. The result is the same.
    """
    if len(df) < MIN_BARS_FOR_TRENDLINE:
        return []
    vol_avg = _volume_average(df)
    if all_pivots is None:
        all_pivots = _zigzag_or_empty(df)

    confirmed: list = []
    for bar_idx, _close_price, pkind in all_pivots:
        if pkind != kind or bar_idx >= len(df):
            continue
        # Use High/Low of the pivot bar for line fitting accuracy.
        price = float(df["High" if kind == "high" else "Low"].iloc[bar_idx])
        ratio = _pivot_ratio(df, vol_avg, bar_idx)
        if ratio is not None:
            confirmed.append((bar_idx, price, ratio))
    return confirmed


# ── Line scoring ──────────────────────────────────────────────────────────────

def _eval_line(slope: float, intercept: float, bar_idx: int) -> float:
    """Price of the line at absolute bar_idx (0 = oldest bar in df)."""
    return slope * bar_idx + intercept


def _pair_line(p0: tuple, p1: tuple) -> tuple[float, float] | None:
    """(slope, intercept) of the line through two pivots, None for a skipped pair."""
    x0, y0, _ = p0
    x1, y1, _ = p1
    if x1 == x0 or y0 <= 0 or y1 <= 0:
        return None
    slope = (y1 - y0) / (x1 - x0)
    return slope, y0 - slope * x0


def _touches(slope: float, intercept: float, pivots) -> list:
    """Every pivot (anchors included) within TOUCH_TOLERANCE_PCT of the line, in pivot order."""
    touches: list = []
    for bar_idx, price, vol_ratio in pivots:
        line_here = _eval_line(slope, intercept, bar_idx)
        if line_here > 0 and abs(price - line_here) / line_here * 100 <= TOUCH_TOLERANCE_PCT:
            touches.append((bar_idx, price, vol_ratio))
    return touches


def _price_gates_pass(slope: float, line_at_now: float, current_price: float, side: str) -> bool:
    """Side check (1 % tolerance: a line right at price still counts) and slope cap."""
    if side == "support" and line_at_now > current_price * 1.01:
        return False
    if side == "resistance" and line_at_now < current_price * 0.99:
        return False
    return not (current_price > 0 and abs(slope / current_price * 100) > MAX_SLOPE_PCT_PER_BAR)


def _scored(slope: float, intercept: float, touches: list, n_bars: int, line_at_now: float) -> dict | None:
    """The candidate dict, or None under two touches."""
    if len(touches) < 2:
        return None
    avg_vol = sum(v for _, _, v in touches) / len(touches)
    last_touch_bar = max(b for b, _, _ in touches)
    recency = last_touch_bar / max(n_bars - 1, 1)          # 0 … 1
    score = len(touches) * avg_vol * (0.4 + 0.6 * recency)
    return {"slope": slope, "intercept": intercept, "touches": touches,
            "strength": len(touches), "score": score, "line_at_now": line_at_now}


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
    if not _price_gates_pass(slope, line_at_now, current_price, side):
        return None
    return _scored(slope, intercept, _touches(slope, intercept, pivots), n_bars, line_at_now)


def _trimmed_zigzag(df: pd.DataFrame) -> list:
    """The zigzag _find_best_trendline's pivot scan runs: over the last
    MAX_PIVOT_SCAN_BARS rows, at PIVOT_THRESHOLD_PCT. Computed once per frame
    and shared by both sides (v245); a failure gives [] (no pivots), as each
    side's own zigzag would."""
    return _zigzag_or_empty(trimmed_frame(df)[0])


def _shift_to_full_frame(best: dict | None, trim_start: int) -> dict | None:
    """Pivot indices are relative to the trimmed frame. Convert the line
    back to the caller's full-frame coordinate system before any
    display-window conversion uses it."""
    if best is None or not trim_start:
        return best
    best["intercept"] -= best["slope"] * trim_start
    best["touches"] = [
        (bar_idx + trim_start, price, vol_ratio)
        for bar_idx, price, vol_ratio in best["touches"]
    ]
    return best


def _empty_prefix(side: str) -> TrendlinePrefix:
    return TrendlinePrefix(side, 0, (), ())


def _prefix_row(confirmed: tuple, i: int) -> tuple:
    row = []
    for j in range(i + 1, len(confirmed)):
        line = _pair_line(confirmed[i], confirmed[j])
        row.append(None if line is None else (*line, tuple(_touches(*line, confirmed))))
    return tuple(row)


def build_trendline_prefix(trimmed: pd.DataFrame, side: str, m: int) -> TrendlinePrefix:
    """The cacheable half of the pair search over ``trimmed.iloc[:m]``: its
    confirmed pivots (minus the last UNSTABLE_PREFIX_PIVOTS) and, per pair,
    the line and its touches over those pivots."""
    found = _volume_confirmed_pivots(trimmed.iloc[:m], "low" if side == "support" else "high")
    confirmed = tuple(found[:max(len(found) - UNSTABLE_PREFIX_PIVOTS, 0)])
    return TrendlinePrefix(side, m, confirmed, tuple(_prefix_row(confirmed, i) for i in range(len(confirmed))))


def _verified_prefix(prefix: TrendlinePrefix | None, pivots: list, side: str) -> TrendlinePrefix:
    """``prefix`` when the window's pivots start with its confirmed pivots, else the empty prefix."""
    if prefix is None or prefix.side != side:
        return _empty_prefix(side)
    k = len(prefix.confirmed)
    if k > len(pivots) or tuple(pivots[:k]) != prefix.confirmed:
        return _empty_prefix(side)
    return prefix


def _cached_pair_result(cell, tail: list, n_bars: int, current_price: float, side: str) -> dict | None:
    if cell is None:
        return None
    slope, intercept, prefix_touches = cell
    line_at_now = _eval_line(slope, intercept, n_bars - 1)
    if not _price_gates_pass(slope, line_at_now, current_price, side):
        return None
    touches = list(prefix_touches) + _touches(slope, intercept, tail)
    return _scored(slope, intercept, touches, n_bars, line_at_now)


def _live_pair_result(p0, p1, pivots: list, n_bars: int, current_price: float, side: str) -> dict | None:
    line = _pair_line(p0, p1)
    if line is None:
        return None
    return _score_candidate(line[0], line[1], pivots, n_bars, current_price, side)


def _pick_best(pivots: list, prefix: TrendlinePrefix, n_bars: int, current_price: float, side: str) -> dict | None:
    """The old i < j pair loop with strict ``>``; pairs inside the prefix read its cells."""
    k = len(prefix.confirmed)
    tail = pivots[k:]
    best: dict | None = None
    for i in range(len(pivots)):
        for j in range(i + 1, len(pivots)):
            if j < k:
                result = _cached_pair_result(prefix.pairs[i][j - i - 1], tail, n_bars, current_price, side)
            else:
                result = _live_pair_result(pivots[i], pivots[j], pivots, n_bars, current_price, side)
            if result and (best is None or result["score"] > best["score"]):
                best = result
    return best


def _find_best_trendline(df: pd.DataFrame, current_price: float, side: str, *,
                         all_pivots: list | None = None,
                         prefix: TrendlinePrefix | None = None) -> dict | None:
    """
    Finds the strongest volume-confirmed S/R trendline for `side`
    ("support" or "resistance") by scanning the FULL df history.

    Algorithm:
      1. Collect volume-confirmed swing lows (support) or highs (resistance).
      2. For every pair (i, j) fit the line through their bar_index/price.
      3. Score the line by how many other confirmed pivots also touch it.
      4. Return the highest-scoring valid line, or None.

    `df` is trimmed to MAX_PIVOT_SCAN_BARS here, before pivot detection --
    the single point both the hot scan path (trendline_levels) and the
    chart-drawing path (strongest_trendline_pair) funnel through, so the
    two can never disagree about which bars were even considered.

    ``all_pivots``: ``_trimmed_zigzag(df)`` when the caller scans both sides
    of the same frame (v245); None computes it inside the pivot filter.

    ``prefix`` (v245): used only when the window's pivots start with its
    confirmed pivots; otherwise every pair runs live. Same result either way.
    """
    df, trim_start = trimmed_frame(df)
    pivots = _volume_confirmed_pivots(df, "low" if side == "support" else "high", all_pivots=all_pivots)
    if len(pivots) < 2:
        return None
    best = _pick_best(pivots, _verified_prefix(prefix, pivots, side), len(df), current_price, side)
    return _shift_to_full_frame(best, trim_start)


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

def custom_scanner_levels(df: pd.DataFrame, current_price: float, prefixes: dict | None = None) -> list:
    """
    The volume-confirmed custom-scanner half of trendline_levels() --
    everything except the trendln-library fallback. Its result depends
    only on (df, current_price), NOT on any horizon-specific value (the
    old signature took `lookback` but never used it here) -- so a caller
    scanning the same ticker across every horizon (engine.py's per-ticker
    horizon loop) can compute this ONCE and pass it into
    collect_candidate_levels()/trendline_levels() for every horizon
    instead of repeating the same O(pivots^3) scan 10 times over
    identical input (v56: measured live, this was the dominant cost of a
    production scan -- see MAX_PIVOT_SCAN_BARS's comment above).

    ``prefixes``: side -> TrendlinePrefix (v245); same result.
    """
    if len(df) < MIN_BARS_FOR_TRENDLINE or current_price <= 0:
        return []

    shared = _trimmed_zigzag(df)
    prefixes = prefixes or {}
    candidates: list = []
    for side in ("support", "resistance"):
        try:
            result = _find_best_trendline(df, current_price, side, all_pivots=shared,
                                          prefix=prefixes.get(side))
            if result:
                candidates.append((
                    float(result["line_at_now"]),
                    f"Trendline ({result['strength']}x touch)",
                ))
        except Exception:
            pass

    return _positive_levels(candidates)


def _positive_levels(candidates: list) -> list:
    """The (price, label) candidates with a positive, non-NaN price."""
    return [(p, s) for p, s in candidates if p and p > 0 and not pd.isna(p)]


def trendline_levels(df: pd.DataFrame, lookback: int, current_price: float,
                      custom_candidates: list | None = None) -> list:
    """
    Fits volume-confirmed support/resistance trendlines through the
    (MAX_PIVOT_SCAN_BARS-capped) df history and returns (price,
    source_label) candidates in the exact shape every other levels.py
    method produces -- 0 to 2 entries.

    ``lookback`` is kept in the signature for API compatibility; the
    actual scan always uses the capped df so anchor points can be far
    apart. Falls back to trendln (scoped to `lookback`, unlike the custom
    scanner) if the custom scanner finds nothing on either side.

    `custom_candidates`: pass custom_scanner_levels(df, current_price)'s
    own result in when the caller already computed it (e.g. once per
    ticker instead of once per horizon) to skip redoing that scan here.
    None (the default) computes it fresh, unchanged behavior for every
    other caller.

    Never raises.
    """
    if len(df) < MIN_BARS_FOR_TRENDLINE or current_price <= 0:
        return []

    candidates = (custom_scanner_levels(df, current_price)
                  if custom_candidates is None else custom_candidates)

    # Fallback: trendln when custom scanner finds nothing. Still per-call
    # (horizon-scoped via `lookback`) -- only the custom scanner above is
    # ever hoisted, since this fallback is cheap (only reached for the
    # minority of tickers with no reliable volume data) and its result
    # genuinely depends on the horizon's own lookback window.
    if not candidates and _TRENDLN_AVAILABLE:
        candidates = _trendln_fallback_levels(df, lookback, current_price)

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

    shared = _trimmed_zigzag(df)
    support_raw: dict | None = None
    resistance_raw: dict | None = None
    try:
        support_raw = _find_best_trendline(df, current_price, "support", all_pivots=shared)
    except Exception:
        pass
    try:
        resistance_raw = _find_best_trendline(df, current_price, "resistance", all_pivots=shared)
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
