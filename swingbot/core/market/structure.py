"""Causal swing structure and volume-in-context features (v121).

The pivot contract: bar ``i`` is a swing high when ``High[i]`` is strictly
greater than the ``k`` highs before it and >= the ``k`` highs after it
(mirror for lows). A pivot at ``i`` is knowable only from bar ``i + k``; at
decision bar ``t`` only pivots with ``i <= t - k`` exist. Every consumer
(v121 snapshot, v122 gate, v123 exit) calls ``confirmed_pivots`` -- this is
the single place the confirmation lag lives. ``k`` is frozen at 3.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

PIVOT_K = 3   # frozen; not a search knob
PIVOT_COLUMNS = ("last_sh_pos", "last_sh", "prior_sh_pos", "prior_sh",
                 "last_sl_pos", "last_sl", "prior_sl_pos", "prior_sl")


def _num(value) -> float | None:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return round(value, 6) if math.isfinite(value) else None


def pivot_confirmations(df: pd.DataFrame, k: int = PIVOT_K) -> tuple[np.ndarray, np.ndarray]:
    """Boolean arrays indexed by CONFIRMATION bar ``j``: True when bar ``j - k``
    is a swing high / swing low. Row ``j`` reads only bars ``j - 2k .. j``."""
    high, low = df["High"], df["Low"]
    pivot_high, pivot_low = high.shift(k), low.shift(k)
    sh = (pivot_high > high.shift(k + 1).rolling(k).max()) & (pivot_high >= high.rolling(k).max())
    sl = (pivot_low < low.shift(k + 1).rolling(k).min()) & (pivot_low <= low.rolling(k).min())
    return sh.fillna(False).to_numpy(bool), sl.fillna(False).to_numpy(bool)


def _last_two(flags: np.ndarray, prices: np.ndarray, k: int) -> tuple[np.ndarray, ...]:
    """Per bar: (last_pos, last_price, prior_pos, prior_price) of confirmed pivots."""
    n = len(flags)
    events = np.flatnonzero(flags) - k
    count = np.cumsum(flags)
    out = [np.full(n, np.nan) for _ in range(4)]
    for slot, back in ((0, 1), (2, 2)):
        has = count >= back
        pos = events[count[has] - back]
        out[slot][has] = pos
        out[slot + 1][has] = prices[pos]
    return tuple(out)


def confirmed_pivots(df: pd.DataFrame, k: int = PIVOT_K) -> pd.DataFrame:
    """Per bar ``t``: positional index and price of the last two confirmed swing
    highs and lows known at ``t`` (NaN where fewer exist). Truncation-stable:
    row ``t`` equals the last row of ``confirmed_pivots(df.iloc[:t + 1])``."""
    sh, sl = pivot_confirmations(df, k)
    highs = _last_two(sh, df["High"].to_numpy(float), k)
    lows = _last_two(sl, df["Low"].to_numpy(float), k)
    return pd.DataFrame(dict(zip(PIVOT_COLUMNS, highs + lows)), index=df.index)
