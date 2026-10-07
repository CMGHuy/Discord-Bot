"""
Fair Value Gaps (FVG) -- a classic price-action/ICT-style imbalance
concept, added here as one more independent vote for levels.py's
confluence system.

A (3-candle) FVG forms when candle 1 and candle 3 don't overlap at all,
leaving a gap that candle 2's impulsive move jumped straight through
without any trading taking place in between:
  - Bullish FVG: candle 1's high sits below candle 3's low. The zone
    between them is "unfilled" price -- an imbalance the market often
    revisits later, which then tends to act as a demand/support zone.
  - Bearish FVG: candle 1's low sits above candle 3's high. Same idea,
    mirrored -- the zone tends to act as a supply/resistance zone.

Only UNFILLED gaps are kept as candidate levels: if any later bar has
already traded back through the full gap zone, the imbalance has been
resolved and it's dropped (a filled gap isn't a level anymore). This
mirrors how every other levels.py source only contributes a level that
still means something today, not a historical curiosity.

The candidate price contributed is the midpoint of the gap zone -- the
zone itself has width, but every other method in levels.py contributes
a single price, so the midpoint keeps FVG candidates on equal footing
for clustering purposes.
"""
import math

import pandas as pd

from swingbot.core.market.indicators import atr

# How many trailing bars to scan for gap FORMATION. Older gaps are far
# more likely to have already been filled (or are simply too stale to
# matter for a swing setup), so this keeps the search bounded and
# relevant, the same way Donchian/Bollinger here use a fixed recent
# window regardless of horizon.
LOOKBACK_BARS = 100

# How many of the most recent unfilled gaps to keep per side -- the
# freshest few, not every unfilled gap ever formed in the window.
MAX_GAPS_PER_SIDE = 3

# v128 (docs/superpowers/specs/2026-10-02-v128-fvg-displacement-audit-design.md).
# Which unfilled gaps reach levels.py: every one ("all", the pre-v128
# behaviour), only displacement gaps, or none. The filter runs AFTER
# find_fair_value_gaps_detailed's freshest-3-per-side truncation, so
# "displacement" is always a subset of "all" -- it never reaches back for an
# older displacement gap. Charts call find_fair_value_gaps_detailed and are
# unaffected by the mode.
FVG_MODES = ("all", "displacement", "off")
DEFAULT_DISPLACEMENT_ATR_K = 1.5
DISPLACEMENT_ATR_PERIOD = 14


def _check_mode(mode: str) -> None:
    if mode not in FVG_MODES:
        raise ValueError(f"unknown FVG mode {mode!r}; expected one of {FVG_MODES}")


def _atr_at(df: pd.DataFrame, m: int, atr_series) -> float:
    """ATR14 at row m. Wilder's EWM is recursive, so the value at m reads rows <= m only."""
    series = atr(df.iloc[:m + 1], DISPLACEMENT_ATR_PERIOD) if atr_series is None else atr_series
    return float(series.iloc[m])


def _closes_in_gap_third(direction: str, close: float, high: float, low: float) -> bool:
    span = high - low
    if direction == "bullish":
        return close >= low + (2.0 / 3.0) * span
    return close <= low + (1.0 / 3.0) * span


def is_displacement_gap(df: pd.DataFrame, gap: dict, k: float, atr_series=None) -> bool:
    """True iff the gap's MIDDLE candle m = bar_index - 1 is a displacement candle:
    |Close[m] - Open[m]| >= k * ATR14[m], and the close sits in the gap-side third
    of the candle's range (top third for a bullish gap, bottom third for a
    bearish one). A non-finite or non-positive ATR14[m] is never displacement.

    Causal: reads row m and earlier only. The gap itself needs bar m + 1 closed,
    so this never reads a bar the gap's existence did not already need, and
    appending later bars cannot change the verdict. `atr_series`, when given,
    must be indicators.atr(df, 14) over the same frame (filter_gaps passes it
    to avoid one ATR per gap)."""
    m = int(gap["bar_index"]) - 1
    if m < 0 or m >= len(df):
        return False
    atr_m = _atr_at(df, m, atr_series)
    if not math.isfinite(atr_m) or atr_m <= 0:
        return False
    row = df.iloc[m]
    open_, high, low, close = (float(row[col]) for col in ("Open", "High", "Low", "Close"))
    if abs(close - open_) < k * atr_m:
        return False
    return _closes_in_gap_third(gap["direction"], close, high, low)


def filter_gaps(df: pd.DataFrame, gaps: list, mode: str = "all",
                k: float = DEFAULT_DISPLACEMENT_ATR_K) -> list:
    """The gaps `mode` keeps, as the same dict objects (never copies)."""
    _check_mode(mode)
    if mode == "all":
        return list(gaps)
    if mode == "off" or not gaps:
        return []
    atr_series = atr(df, DISPLACEMENT_ATR_PERIOD)
    return [gap for gap in gaps if is_displacement_gap(df, gap, k, atr_series)]


def find_fair_value_gaps_detailed(df: pd.DataFrame, lookback: int = LOOKBACK_BARS,
                                   max_per_side: int = MAX_GAPS_PER_SIDE, mode: str = "all",
                          k: float = DEFAULT_DISPLACEMENT_ATR_K) -> list:
    """
    Same detection as find_fair_value_gaps(), but returns the full gap
    geometry instead of just a midpoint price -- {"bottom", "top", "mid",
    "bar_index", "direction"} per gap, where bar_index is the (0-based,
    positional) index of the THIRD candle of the 3-candle pattern that
    formed the gap. Used by trade_chart.py to actually draw the zone as
    a shaded rectangle instead of a single line; find_fair_value_gaps()
    itself only needs the price for levels.py's confluence system, so it
    stays a thin wrapper around this rather than duplicating the scan.
    """
    try:
        highs = df["High"].values
        lows = df["Low"].values
        n = len(df)
        if n < 3:
            return []

        start = max(2, n - lookback)
        bullish_gaps = []
        bearish_gaps = []

        for i in range(start, n):
            h0, l2 = highs[i - 2], lows[i]
            if l2 > h0:
                gap_bottom, gap_top = h0, l2
                filled = any(
                    lows[j] <= gap_top and highs[j] >= gap_bottom
                    for j in range(i + 1, n)
                )
                if not filled:
                    bullish_gaps.append({
                        "bottom": float(gap_bottom), "top": float(gap_top),
                        "mid": float((gap_bottom + gap_top) / 2), "bar_index": i, "direction": "bullish",
                    })
                continue

            l0, h2 = lows[i - 2], highs[i]
            if h2 < l0:
                gap_bottom, gap_top = h2, l0
                filled = any(
                    lows[j] <= gap_top and highs[j] >= gap_bottom
                    for j in range(i + 1, n)
                )
                if not filled:
                    bearish_gaps.append({
                        "bottom": float(gap_bottom), "top": float(gap_top),
                        "mid": float((gap_bottom + gap_top) / 2), "bar_index": i, "direction": "bearish",
                    })

        return bullish_gaps[-max_per_side:] + bearish_gaps[-max_per_side:]
    except Exception:
        return []


def find_fair_value_gaps(df: pd.DataFrame, lookback: int = LOOKBACK_BARS,
                          max_per_side: int = MAX_GAPS_PER_SIDE, mode: str = "all",
                          k: float = DEFAULT_DISPLACEMENT_ATR_K) -> list:
    """
    Scans the last `lookback` bars for 3-candle Fair Value Gaps and
    returns the still-UNFILLED ones as (price, source_label) candidates
    in the exact shape every other levels.py method produces. Thin
    wrapper around find_fair_value_gaps_detailed() -- see that function
    for the full gap geometry (needed by trade_chart.py to draw the
    zone, not just its midpoint).

    `mode`/`k` (v128): "all" (default) returns every unfilled gap exactly
    as before; "displacement" keeps only is_displacement_gap(..., k) gaps;
    "off" returns []. See FVG_MODES.

    Never raises on data: too little data or a malformed frame just means
    no FVG candidates this round, same as every other method here failing
    silently. An unknown `mode` is a programming error and raises ValueError.
    """
    _check_mode(mode)
    gaps = filter_gaps(df, find_fair_value_gaps_detailed(df, lookback, max_per_side), mode, k)
    return [
        (g["mid"], "FVG (bullish)" if g["direction"] == "bullish" else "FVG (bearish)")
        for g in gaps if g["mid"] > 0
    ]
