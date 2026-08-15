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
import pandas as pd

# How many trailing bars to scan for gap FORMATION. Older gaps are far
# more likely to have already been filled (or are simply too stale to
# matter for a swing setup), so this keeps the search bounded and
# relevant, the same way Donchian/Bollinger here use a fixed recent
# window regardless of horizon.
LOOKBACK_BARS = 100

# How many of the most recent unfilled gaps to keep per side -- the
# freshest few, not every unfilled gap ever formed in the window.
MAX_GAPS_PER_SIDE = 3


def find_fair_value_gaps_detailed(df: pd.DataFrame, lookback: int = LOOKBACK_BARS,
                                   max_per_side: int = MAX_GAPS_PER_SIDE) -> list:
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
                          max_per_side: int = MAX_GAPS_PER_SIDE) -> list:
    """
    Scans the last `lookback` bars for 3-candle Fair Value Gaps and
    returns the still-UNFILLED ones as (price, source_label) candidates
    in the exact shape every other levels.py method produces. Thin
    wrapper around find_fair_value_gaps_detailed() -- see that function
    for the full gap geometry (needed by trade_chart.py to draw the
    zone, not just its midpoint).

    Never raises: any failure (too little data, malformed frame) just
    means no FVG candidates this round, same as every other method
    here failing silently.
    """
    gaps = find_fair_value_gaps_detailed(df, lookback, max_per_side)
    return [
        (g["mid"], "FVG (bullish)" if g["direction"] == "bullish" else "FVG (bearish)")
        for g in gaps if g["mid"] > 0
    ]
