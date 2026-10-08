"""Matched random baseline for the v140 screen (spec § The matched baseline).

Eligible bar: member at t, warm-up complete, race completes inside the
frame, t not an event bar (any raw event, kept or not). Per event: draw
min(K, candidates) eligible bars without replacement from the same ticker,
same YYYY-MM, same trend state (close > SMA200); fewer than 5 candidates
drops the event. Null bars are not subject to the one-open-race rule: they
are a counterfactual, not a book.
"""
from __future__ import annotations

import zlib
from dataclasses import dataclass

import numpy as np
import pandas as pd

from swingbot.core.backtesting.screen import race as race_mod

K = 20
MIN_CANDIDATES = 5
SEED_BASE = 42


def null_seed(idea: str, ticker: str, base: int = SEED_BASE) -> list:
    """Deterministic per (idea, ticker), derived from 42."""
    return [base, zlib.crc32(idea.encode()), zlib.crc32(ticker.encode())]


def member_mask(index, spans) -> np.ndarray:
    """``pit_membership.is_member`` for every bar: [start, end) ISO spans."""
    days = np.asarray(pd.DatetimeIndex(index).strftime("%Y-%m-%d"))
    if spans is None:
        return np.ones(len(days), dtype=bool)
    out = np.zeros(len(days), dtype=bool)
    for start, end in spans:
        out |= (days >= start) & (days < end)
    return out


def trend_state(df: pd.DataFrame, sma200) -> np.ndarray:
    return (df["Close"] > sma200).to_numpy(dtype=bool)


def month_key(index) -> np.ndarray:
    index = pd.DatetimeIndex(index)
    return np.asarray(index.year * 12 + index.month)


def eligible_mask(events, member, warm, cap: int) -> np.ndarray:
    events = np.asarray(events, dtype=bool)
    complete = np.arange(len(events)) + cap <= len(events) - 1
    return (np.asarray(member, dtype=bool) & np.asarray(warm, dtype=bool)
            & complete & ~events)


def candidates(pos: int, eligible, months, trend) -> np.ndarray:
    return np.flatnonzero(eligible & (months == months[pos]) & (trend == trend[pos]))


@dataclass(frozen=True, eq=False)
class NullDraw:
    event_pos: np.ndarray
    groups: tuple
    null_mean_r: np.ndarray
    null_race: race_mod.RaceResult
    dropped_no_match: int


def _empty(dropped: int) -> NullDraw:
    return NullDraw(np.array([], dtype=int), (), np.array([], dtype=float),
                    race_mod.RaceResult.empty(), dropped)


def matched_null(df, event_pos, eligible, k: int, seed, *, cap: int, atr,
                 trend, slippage_bps=None, commission=None) -> NullDraw:
    rng = np.random.default_rng(seed)
    months = month_key(df.index)
    kept, groups, dropped = [], [], 0
    for pos in np.asarray(event_pos, dtype=int):
        pool = candidates(pos, eligible, months, trend)
        if len(pool) < MIN_CANDIDATES:
            dropped += 1
            continue
        kept.append(pos)
        groups.append(np.sort(rng.choice(pool, size=min(k, len(pool)), replace=False)))
    if not kept:
        return _empty(dropped)
    raced = race_mod.race(df, np.concatenate(groups), cap, atr=atr,
                          slippage_bps=slippage_bps, commission=commission)
    bounds = np.cumsum([len(g) for g in groups])[:-1]
    means = np.array([part.mean() for part in np.split(raced.r, bounds)])
    return NullDraw(np.asarray(kept, dtype=int), tuple(groups), means, raced, dropped)
