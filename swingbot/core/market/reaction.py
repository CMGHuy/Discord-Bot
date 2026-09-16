"""v88: did price test a level and react there?

Pure bar predicates for the armed-entry measurement
(backtesting/armed_replay.py). They live in market/ rather than
backtesting/ so a live path -- v88 spec §5's A2, written only if the
measurement passes VALIDATION -- would share this one source, the way
entry_filters.py is shared by the backtest and the live scanner.

Bullish: `level` is a SUPPORT below price (the plan's stop level). Bearish
mirrors it: `level` is a RESISTANCE above price, highs for lows, every
inequality flipped.

NO-LOOKAHEAD: every predicate at bar `t` reads bar `t` and earlier only.
Callers pass whole arrays for speed; nothing here indexes past `t`.
No config reads, no I/O.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

R1, R2, R3 = "R1", "R2", "R3"   # rejection, follow-through, reclaim

REJECTION_WICK_MIN = 0.5          # wick >= half the bar's range
REJECTION_CLOSE_FRACTION = 2.0 / 3.0  # close in the top (bullish) third
RECLAIM_BARS = 2                  # a close through the level may be undone within 2 bars


@dataclass(frozen=True, eq=False)
class Bars:
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray

    @classmethod
    def from_frame(cls, df) -> "Bars":
        return cls(df["Open"].to_numpy(dtype=float), df["High"].to_numpy(dtype=float),
                   df["Low"].to_numpy(dtype=float), df["Close"].to_numpy(dtype=float))


def is_test(bars: Bars, t: int, level: float, direction: str, k: float, atr_t: float) -> bool:
    """Bar t came within k*ATR of the level, or went through it."""
    if not np.isfinite(atr_t):
        return False
    if direction == "bullish":
        return bool(bars.low[t] <= level + k * atr_t)
    return bool(bars.high[t] >= level - k * atr_t)


def is_rejection(bars: Bars, t: int, level: float, direction: str) -> bool:
    """R1 shape: a long wick into the level, a close far from it, on the
    trade's side of the level."""
    o, h, l, c = bars.open[t], bars.high[t], bars.low[t], bars.close[t]
    rng = h - l
    if not rng > 0:
        return False
    if direction == "bullish":
        wick = min(o, c) - l
        return bool(wick >= REJECTION_WICK_MIN * rng
                    and c >= l + REJECTION_CLOSE_FRACTION * rng and c >= level)
    wick = h - max(o, c)
    return bool(wick >= REJECTION_WICK_MIN * rng
                and c <= h - REJECTION_CLOSE_FRACTION * rng and c <= level)


def is_follow_through(bars: Bars, t: int, direction: str) -> bool:
    """R2 shape: bar t closed beyond the previous bar's extreme."""
    if t < 1:
        return False
    if direction == "bullish":
        return bool(bars.close[t] > bars.high[t - 1])
    return bool(bars.close[t] < bars.low[t - 1])


def is_reclaim(bars: Bars, t: int, level: float, direction: str, floor_index: int) -> bool:
    """R3: a close through the level within the last RECLAIM_BARS bars --
    counting only bars at or after `floor_index` (the arm bar) -- undone by
    bar t's close."""
    lo = max(floor_index, t - RECLAIM_BARS)
    if lo > t - 1:
        return False
    prior = bars.close[lo:t]
    if direction == "bullish":
        return bool((prior < level).any() and bars.close[t] >= level)
    return bool((prior > level).any() and bars.close[t] <= level)


def reaction_kind(bars: Bars, t: int, level: float, direction: str, *,
                  tested_now: bool, tested_prev: bool, floor_index: int) -> str | None:
    """The strongest reaction bar t shows, or None. R3 > R2 > R1.

    R2 needs a test on bar t or t-1 (the caller passes tested_prev=False
    when t-1 precedes the arm bar). R1 needs bar t itself to be the test:
    a rejection wick that never reached the level rejected nothing.
    R3 needs no separate test flag -- closing through the level is one.
    """
    if is_reclaim(bars, t, level, direction, floor_index):
        return R3
    if (tested_now or tested_prev) and is_follow_through(bars, t, direction):
        return R2
    if tested_now and is_rejection(bars, t, level, direction):
        return R1
    return None
