"""Sweep -> reclaim -> break of structure, buy side. Trigger frozen 2026-10-21.

The ordered price-action chain from the partner's Daiken/BigWhale pages
(steps 4-5): price trades under the latest confirmed swing low, closes back
above it, then closes above the last confirmed swing high known when the
sweep happened. A sweep alone is turtle_soup's question; this idea asks
whether the break of structure after it adds anything. Pivots are v121's
k = 3 fractals, known only once confirmed, so every bar reads bars <= t.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from swingbot.core.market.structure import confirmed_pivots

CAP = 20
PARAMS = {"pivot_k": 3, "min_age": 4, "reclaim_bars": 2, "bos_bars": 10}
SUMMARY = ("low < the last confirmed k=3 swing low (>= 4 bars old), a close back "
           "above it on that bar or within 2 more, then a close above the last "
           "confirmed swing high known at the sweep, within 10 bars of the sweep; "
           "a low under the sweep low after the reclaim cancels; each swing low "
           "arms at most one setup")
SOURCE = ("Daiken/BigWhale price-action pages, steps 4-5 (liquidity sweep, "
          "reclaim, BOS confirmation); partner-shared 2026-10-21")


@dataclass
class _Setup:
    swept_pos: float
    sweep_bar: int
    swept: float
    sweep_low: float
    bos_level: float
    reclaimed: bool = False


def _advance(setup: _Setup, t: int, low: float, close: float) -> tuple[_Setup | None, bool]:
    """One bar of an armed setup: (setup still armed or None, fired)."""
    if not setup.reclaimed:
        setup.sweep_low = min(setup.sweep_low, low)
        if close > setup.swept:
            setup.reclaimed = True
        elif t - setup.sweep_bar >= PARAMS["reclaim_bars"]:
            return None, False
        else:
            return setup, False
    elif low < setup.sweep_low:
        return None, False
    if t - setup.sweep_bar > PARAMS["bos_bars"]:
        return None, False
    if close > setup.bos_level:
        return None, True
    return setup, False


def _try_sweep(t: int, low: float, known: pd.DataFrame, used_pos: float) -> _Setup | None:
    """A new setup when bar t trades under an aged swing low, not armed before
    (``used_pos``), with a swing high above it."""
    swept, pos, high = (known["last_sl"].iat[t], known["last_sl_pos"].iat[t],
                        known["last_sh"].iat[t])
    if np.isnan(swept) or np.isnan(high) or high <= swept:
        return None
    if pos == used_pos or t - pos < PARAMS["min_age"] or not low < swept:
        return None
    return _Setup(swept_pos=float(pos), sweep_bar=t, swept=float(swept),
                  sweep_low=low, bos_level=float(high))


def events(df: pd.DataFrame) -> pd.Series:
    """Event at the close of t: the bar that completes sweep -> reclaim -> BOS."""
    known = confirmed_pivots(df, PARAMS["pivot_k"])
    lows, closes = df["Low"].to_numpy(float), df["Close"].to_numpy(float)
    out = np.zeros(len(df), dtype=bool)
    setup, used_pos = None, np.nan
    for t in range(len(df)):
        if setup is not None:
            setup, out[t] = _advance(setup, t, lows[t], closes[t])
            if setup is not None or out[t]:
                continue
        setup = _try_sweep(t, lows[t], known, used_pos)
        if setup is not None:
            used_pos = setup.swept_pos
            setup, out[t] = _advance(setup, t, lows[t], closes[t])
    return pd.Series(out, index=df.index, name="sweep_reclaim_bos")
