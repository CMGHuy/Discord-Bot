"""Causal Fibonacci impulse leg (v124) -- a pure instrument with no live caller.

Bullish leg at bar t: the origin is the most recent swing low of strength
``origin_k`` confirmed at t (``structure.confirmed_pivots``); the end is the
FIRST bar holding the highest High in (origin, t], and the leg exists only
once that bar is at least MIN_END_AGE bars old. No leg (all NaN) when no
origin is confirmed, the end is too young, a bar in (origin, t] is not
finite, or any Low after the origin undercuts the origin price. A later
confirmed swing low simply becomes the new origin.

Bearish mirrors every comparison. The module works in an oriented space:
bearish negates prices and swaps High/Low (hi = -Low, lo = -High), runs the
bullish logic, and negates the price columns back.

Causality: row t of impulse_leg(df) equals impulse_leg(df.iloc[:t+1]).iloc[-1].
Pivot lag lives only in structure.py; nothing here detects pivots.
"""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd

from swingbot.core.market.indicators import atr
from swingbot.core.market.strategy_types import HORIZONS
from swingbot.core.market.structure import confirmed_pivots, pivot_confirmations

ORIGIN_DIVISOR = 6   # frozen descriptive default (spec "Origin strength")
MIN_ORIGIN_K = 3
MIN_END_AGE = 3      # bars; the lag v121 uses
RATIOS = (0.382, 0.5, 0.618)
LEG_COLUMNS = ("origin_idx", "origin_price", "end_idx", "end_price", "leg_atr", "leg_bars",
               "level_382", "level_500", "level_618", "retrace_now", "retrace_deepest",
               "zone_touch", "broke_structure")
PRICE_COLUMNS = ("origin_price", "end_price", "level_382", "level_500", "level_618")
_SIDES = {"bullish": ("last_sl_pos", 1.0), "bearish": ("last_sh_pos", -1.0)}
_NO_LEG = dict.fromkeys(LEG_COLUMNS, np.nan)


def origin_strength(horizon_key: str, divisor: int = ORIGIN_DIVISOR) -> int:
    """Pivot strength of the leg origin: max(3, fib_lookback // divisor)."""
    return max(MIN_ORIGIN_K, int(HORIZONS[horizon_key]["fib_lookback"]) // divisor)


def _oriented(df: pd.DataFrame, direction: str, origin_k: int) -> SimpleNamespace:
    """Bullish-oriented arrays. ``prior`` holds positions of the opposite-side
    pivots (swing highs for a bullish leg) for the structure-break check."""
    origin_col, sign = _SIDES[direction]
    high, low = df["High"].to_numpy(float), df["Low"].to_numpy(float)
    sh, sl = pivot_confirmations(df, origin_k)
    hi, lo = (high, low) if sign > 0 else (-low, -high)
    prior_flags = sh if sign > 0 else sl
    return SimpleNamespace(
        sign=sign, hi=hi, lo=lo, close=sign * df["Close"].to_numpy(float),
        origin=confirmed_pivots(df, origin_k)[origin_col].to_numpy(float),
        prior=np.flatnonzero(prior_flags) - origin_k,
        atr=atr(df).to_numpy(float))


def _bounds(o: SimpleNamespace, t: int) -> tuple[int, int] | None:
    """(origin, end) positions of the leg at bar t, or None for no leg."""
    origin = o.origin[t]
    if not np.isfinite(origin):
        return None
    origin = int(origin)
    seg_hi, seg_lo = o.hi[origin + 1:t + 1], o.lo[origin + 1:t + 1]
    if seg_hi.size == 0 or not (np.isfinite(seg_hi).all() and np.isfinite(seg_lo).all()):
        return None
    end = origin + 1 + int(np.argmax(seg_hi))          # first occurrence on ties
    if t - end < MIN_END_AGE or seg_lo.min() < o.lo[origin]:
        return None
    return origin, end


def _prior_break(o: SimpleNamespace, origin: int, end_price: float) -> float:
    """1.0 if the end exceeds the last opposite-side pivot BEFORE the origin,
    0.0 if not, NaN if none exists. Any such pivot is confirmed by t: its
    confirmation bar is < origin + k <= t."""
    earlier = o.prior[o.prior < origin]
    if earlier.size == 0:
        return np.nan
    return float(end_price > o.hi[earlier[-1]])


def _features(o: SimpleNamespace, t: int, origin: int, end: int) -> dict | None:
    """Oriented leg row at bar t; None when the leg has no size."""
    origin_price, end_price = float(o.lo[origin]), float(o.hi[end])
    size = end_price - origin_price
    if not size > 0:
        return None
    levels = {f"level_{round(ratio * 1000)}": end_price - ratio * size for ratio in RATIOS}
    atr_t = float(o.atr[t])
    return {"origin_idx": float(origin), "origin_price": origin_price,
            "end_idx": float(end), "end_price": end_price,
            "leg_atr": size / atr_t if atr_t > 0 else np.nan,
            "leg_bars": float(end - origin), **levels,
            "retrace_now": (end_price - float(o.close[t])) / size,
            "retrace_deepest": (end_price - float(o.lo[end + 1:t + 1].min())) / size,
            "zone_touch": float(o.lo[t] <= levels["level_500"] and o.close[t] >= levels["level_618"]),
            "broke_structure": _prior_break(o, origin, end_price)}


def _real(row: dict, sign: float) -> dict:
    return {**row, **{key: sign * row[key] for key in PRICE_COLUMNS}}


def _row(o: SimpleNamespace, t: int) -> dict:
    bounds = _bounds(o, t)
    row = _features(o, t, *bounds) if bounds else None
    return _real(row, o.sign) if row else dict(_NO_LEG)


def impulse_leg(df: pd.DataFrame, direction: str, origin_k: int) -> pd.DataFrame:
    """One row per bar: the leg known at that bar (all NaN when there is none)."""
    if len(df) == 0:
        return pd.DataFrame(columns=list(LEG_COLUMNS), index=df.index, dtype=float)
    o = _oriented(df, direction, origin_k)
    rows = [_row(o, t) for t in range(len(df))]
    return pd.DataFrame(rows, index=df.index, columns=list(LEG_COLUMNS), dtype=float)


def leg_at(df: pd.DataFrame, direction: str, origin_k: int) -> dict:
    """The leg at the last bar only -- equal to impulse_leg(df, ...).iloc[-1]."""
    if len(df) == 0:
        return dict(_NO_LEG)
    return _row(_oriented(df, direction, origin_k), len(df) - 1)
