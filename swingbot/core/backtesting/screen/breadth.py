"""BREADTH_ATR1: the share of point-in-time index members that fell by at
least one ATR on a session.

``BREADTH_ATR1[t]`` = (members on ``t`` with a finite move and move <= -1.0)
/ (members on ``t`` with a finite move), where the move is
``(Close[t] - Close[t-1]) / ATR14[t-1]``.

It is precomputed into a context file because the idea interface has no
cross-sectional input (spec Track 2). Every value at ``t`` reads bars dated
``<= t`` and the ATR dated ``<= t-1``. A member's move counts only when its
previous bar is the previous session, so a missing member bar leaves the
denominator on that session and on the next one.
"""
from __future__ import annotations

from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from swingbot.core.backtesting.screen import indicators

NAME = "BREADTH_ATR1"
ATR_MOVE = -1.0


def member_atr_moves(df: pd.DataFrame) -> pd.Series:
    """One-bar close change in units of the prior bar's ATR14."""
    return (df["Close"] - df["Close"].shift(1)) / indicators.atr(df).shift(1)


def member_mask(spans: Sequence[tuple[str, str]], sessions: pd.DatetimeIndex) -> np.ndarray:
    """True on sessions inside any half-open ISO span [start, end)."""
    iso = sessions.strftime("%Y-%m-%d").to_numpy(dtype=str)
    mask = np.zeros(len(sessions), dtype=bool)
    for start, end in spans:
        mask |= (iso >= start) & (iso < end)
    return mask


def _session_moves(df: pd.DataFrame, sessions: pd.DatetimeIndex) -> np.ndarray:
    moves = member_atr_moves(df).reindex(sessions)
    own_prev = pd.Series(df.index, index=df.index).shift(1).reindex(sessions)
    spy_prev = pd.Series(sessions, index=sessions).shift(1)
    contiguous = (own_prev == spy_prev).to_numpy()
    return np.where(contiguous, moves.to_numpy(dtype=float), np.nan)


def breadth_atr1(frames: Mapping[str, pd.DataFrame], intervals: Mapping[str, list],
                 sessions: pd.DatetimeIndex) -> pd.DataFrame:
    counted = np.zeros(len(sessions), dtype=int)
    hits = np.zeros(len(sessions), dtype=int)
    for symbol, df in frames.items():
        spans = intervals.get(symbol)
        if not spans:
            continue
        moves = _session_moves(df, sessions)
        ok = member_mask(spans, sessions) & np.isfinite(moves)
        counted += ok
        with np.errstate(invalid="ignore"):
            hits += ok & (moves <= ATR_MOVE)
    share = np.divide(hits, counted, out=np.zeros(len(sessions)), where=counted > 0)
    index = pd.DatetimeIndex(sessions, name="Date")
    return pd.DataFrame({"Open": share, "High": share, "Low": share, "Close": share,
                         "Volume": counted}, index=index)
