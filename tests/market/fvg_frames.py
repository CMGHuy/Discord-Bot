"""Hand-built OHLC frames for the v128 FVG tests. No test_ prefix: not collected.

Every hand-built frame is `flat_bars` identical candles (O=C=100, H=101, L=99:
true range 2.0, so ATR14 settles at exactly 2.0), then a middle candle `m`,
then a third candle `i = m + 1` that opens a gap against candle `m - 1`.
The ATR figures in the comments are Wilder's EWM: ATR[m] = 2.0 * 13/14 + TR[m]/14.
"""
import numpy as np
import pandas as pd

FLAT = (100.0, 101.0, 99.0, 100.0)            # Open, High, Low, Close

STRONG_BULL = (100.0, 104.2, 99.8, 104.0)     # TR 4.4 -> ATR14 2.1714; body 4.0; close at 95% of range
WEAK_BULL = (100.0, 101.6, 99.9, 101.5)       # TR 1.7 -> ATR14 1.9786; body 1.5 < 1.5 x 1.9786
MID_CLOSE_BULL = (97.0, 106.0, 96.9, 101.0)   # TR 9.1 -> ATR14 2.5071; body 4.0 >= 3.76, close at 45% of range
UP_CLOSE_BIG = (96.0, 100.2, 95.8, 100.0)     # TR 4.4 -> ATR14 2.1714; body 4.0, close at 95% of range
STRONG_BEAR = (100.0, 100.2, 95.8, 96.0)      # TR 4.4 -> ATR14 2.1714; body 4.0, close at 5% of range

BULL_THIRD = (104.0, 105.0, 101.5, 104.5)     # Low 101.5 > flat High 101.0: bullish gap 101.0..101.5, mid 101.25
BEAR_THIRD = (96.0, 98.5, 95.0, 96.5)         # High 98.5 < flat Low 99.0: bearish gap 98.5..99.0, mid 98.75


def bar_frame(bars) -> pd.DataFrame:
    bars = list(bars)
    index = pd.bdate_range("2024-01-01", periods=len(bars))
    frame = pd.DataFrame(bars, columns=["Open", "High", "Low", "Close"], index=index)
    frame["Volume"] = 1_000_000.0
    return frame


def gap_frame(middle, third, flat_bars: int = 20) -> pd.DataFrame:
    return bar_frame([FLAT] * flat_bars + [middle, third])


def witness_frame(n: int = 260, seed: int = 126) -> pd.DataFrame:
    """A seeded random walk with ~6% jump days, so it carries unfilled gaps of both kinds."""
    rng = np.random.default_rng(seed)
    steps = rng.normal(0.0, 0.012, n)
    jumps = np.where(rng.random(n) < 0.06, rng.choice([-0.04, 0.04], n), 0.0)
    close = 100.0 * np.exp(np.cumsum(steps + jumps))
    open_ = np.r_[close[0], close[:-1]]
    spread = np.abs(rng.normal(0.0, 0.006, n)) * close
    high = np.maximum(open_, close) + spread
    low = np.minimum(open_, close) - spread
    return bar_frame(zip(open_, high, low, close))
