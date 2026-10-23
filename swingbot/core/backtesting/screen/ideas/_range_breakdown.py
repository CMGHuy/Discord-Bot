"""v182 range breakdown: the one frozen range and trend definition.

Shared by range_breakdown_close and range_breakdown_stop (spec Part C). The
numbers are the idea and are never tuned after the run. Every series here
describes bar t from bars <= t-1 only; the trigger, which reads bar t, lives
in each idea module.

- window: the 30 bars t-30..t-1; S = min Low, R = max High over it;
- a range, not a slide: R - S <= 5 x ATR14[t-1];
- touches: at least two window bars with Low <= S + 0.25 x ATR14[t-1], the
  earliest and latest at least 5 bars apart; the same for High >= R - 0.25 x
  ATR14[t-1];
- own downtrend: SMA50[t-1] < SMA50[t-11] and Close[t-1] < SMA50[t-1];
- first break: Close[t-1] >= S[t-1], the support of bar t-1's own window
  (t-31..t-2), so a breakdown sets up once, not on every following bar;
- ATR14[t-1] NaN or <= 0 means no event; warm-up: bar position t >= 61.

Not an idea module (no CAP, no events): the leading underscore keeps it out
of IDEA_MODULES.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

from swingbot.core.backtesting.screen import indicators

WINDOW = 30
HEIGHT_ATR = 5.0
TOUCH_ATR = 0.25
TOUCH_SPAN = 5
SMA_LEN = 50
SMA_LAG = 10
WARMUP = 61
PARAMS = {"window": WINDOW, "height_atr": HEIGHT_ATR, "touch_atr": TOUCH_ATR,
          "touch_span": TOUCH_SPAN, "sma": SMA_LEN, "sma_lag": SMA_LAG,
          "warmup": WARMUP}
SOURCE = ('Schwab, "The Ins and Outs of a Swing Trade" (2025-03-07), '
          "downswing breakout")
FAMILY = ("range_breakdown_close", "range_breakdown_stop")


def prior_atr(df: pd.DataFrame) -> pd.Series:
    """ATR14[t-1]: the ATR known before bar t opens."""
    return indicators.atr(df).shift(1)


def support(df: pd.DataFrame) -> pd.Series:
    """S for bar t: min Low over t-30..t-1."""
    return indicators.rolling_min(df["Low"].shift(1), WINDOW)


def resistance(df: pd.DataFrame) -> pd.Series:
    """R for bar t: max High over t-30..t-1."""
    return indicators.rolling_max(df["High"].shift(1), WINDOW)


def _spread(hit: np.ndarray) -> np.ndarray:
    """Per window row: at least two touches, the earliest and latest at least
    TOUCH_SPAN bars apart (two distinct bars follow from the span)."""
    first = hit.argmax(axis=1)
    last = hit.shape[1] - 1 - hit[:, ::-1].argmax(axis=1)
    return hit.any(axis=1) & (last - first >= TOUCH_SPAN)


def _touched(df: pd.DataFrame, column: str, low: pd.Series, high: pd.Series) -> pd.Series:
    """Bar t: the window t-30..t-1 of ``column`` has spread touches inside
    [low[t], high[t]]. A NaN bound is no touch."""
    values = df[column].to_numpy(dtype=float)
    out = np.zeros(len(values), dtype=bool)
    if len(values) > WINDOW:
        # Row r holds bars r..r+29: the window of bar t = r + 30.
        windows = sliding_window_view(values[:-1], WINDOW)
        lo = low.to_numpy(dtype=float)[WINDOW:, None]
        hi = high.to_numpy(dtype=float)[WINDOW:, None]
        with np.errstate(invalid="ignore"):
            out[WINDOW:] = _spread((windows >= lo) & (windows <= hi))
    return pd.Series(out, index=df.index)


def in_range(df: pd.DataFrame) -> pd.Series:
    """Height and both touch clauses."""
    s, r, atr = support(df), resistance(df), prior_atr(df)
    band = TOUCH_ATR * atr
    height = ((r - s) <= HEIGHT_ATR * atr).fillna(False)
    lows = _touched(df, "Low", s - np.inf, s + band)
    highs = _touched(df, "High", r - band, r + np.inf)
    return (height & lows & highs).fillna(False)


def downtrend(df: pd.DataFrame) -> pd.Series:
    """SMA50[t-1] < SMA50[t-11] and Close[t-1] < SMA50[t-1]."""
    sma = indicators.sma(df["Close"], SMA_LEN).shift(1)
    falling = (sma < sma.shift(SMA_LAG)).fillna(False)
    below = (df["Close"].shift(1) < sma).fillna(False)
    return falling & below


def first_break(df: pd.DataFrame) -> pd.Series:
    """Close[t-1] >= S[t-1]: the prior bar closed at or above its own
    range support (window t-31..t-2), so only the first breakdown bar sets up."""
    return (df["Close"].shift(1) >= support(df).shift(1)).fillna(False)


def _ready(df: pd.DataFrame) -> pd.Series:
    """ATR14[t-1] finite and > 0, and 61 completed bars before t."""
    atr_ok = (prior_atr(df) > 0).fillna(False)
    return atr_ok & pd.Series(np.arange(len(df)) >= WARMUP, index=df.index)


def control_setup(df: pd.DataFrame) -> pd.Series:
    """The trend-only control: trend and first-break clauses, no range
    clauses (spec Part C descriptive block; printed, never gating)."""
    return downtrend(df) & first_break(df) & _ready(df)


def setup(df: pd.DataFrame) -> pd.Series:
    """Every clause except the trigger on bar t."""
    return control_setup(df) & in_range(df)
