# tests/market/structure_tier_fixtures.py
"""Hand-built frames with known swing tiers and BOS/CHoCH events (v130).

Bars have an ABSOLUTE half-range (not a percent of price), so ATR14 at a pivot
is easy to reason about. ``mirror=True`` reflects every close around 250, which
turns each swing low into a swing high at the same bar."""
import numpy as np

from tests.conftest import make_ohlcv
from tests.market.structure_fixtures import zigzag

# One swing low at bar 16 below a swing high at bar 8; the low's reference high is 110.5.
IMPACT_LATER = [100, 110, 104, 118]     # reaction is there by bar 19; the close clears 110.5 at bar 20
NO_BREAK = [100, 120, 104, 114]         # 5 ATR of reaction, never closes above 120.5
EARLY = [100, 103, 101, 115]            # both conditions already hold at bar 18 = i + 2
UNDERCUT = [100, 110, 104, 109, 103, 118]   # the bar-16 low is undercut before any break
NO_REF = [110, 100, 120]                # leg=16: a swing low at bar 16 with no swing high before it
# Wide bars up to the bar-32 low (ATR14 = 4.0), narrow bars after: the close clears the
# reference high (109.0) at bar 36 on 1.6 ATR of reaction; 2 ATR arrives at bar 38.
WEAK = [100, 110, 104, 107, 105.5, 114]
# Falling major highs AND falling major lows, then a relief rally. Events (bar, kind, direction):
# (70, bos, bearish), (94, choch, bullish), (102, bos, bearish), (110, bos, bullish).
# Mirrored: the same bars with bullish <-> bearish swapped.
DOWN = [130, 120, 124, 116, 128, 110, 113, 106, 118, 100, 103, 96, 108, 90, 115]


def tier_frame(points, *, mirror=False, leg=8, half=0.5):
    closes = zigzag([250 - p for p in points] if mirror else points, leg=leg)
    df = make_ohlcv(closes, spread_pct=0.0)
    df["High"], df["Low"] = df["Close"] + half, df["Close"] - half
    return df


def weak_frame(*, mirror=False):
    half = np.where(np.arange(41) <= 32, 2.0, 0.25)
    return tier_frame(WEAK, mirror=mirror, half=half)

