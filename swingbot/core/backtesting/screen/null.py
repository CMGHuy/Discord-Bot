"""Matched random baseline for the v140 screen (spec § The matched baseline).

Eligible bar: member at t, warm-up complete, race completes inside the
frame, t not an event bar (any raw event, kept or not). Per event: draw
min(K, candidates) eligible bars without replacement from the same ticker,
same YYYY-MM, same trend state (close > SMA200); fewer than 5 candidates
drops the event. Null bars are not subject to the one-open-race rule: they
are a counterfactual, not a book.

v182 level mode (depth=...): each event's null bars copy its fill depth
d_e = (Open[t] - fill) / ATR14[t-1]: a null bar p fills at
Open[p] - d_e x ATR14[p-1] (short; long mirror +) when its range reaches that
level and ATR14[p-1] is finite and > 0. Unfilled first draws are replaced
from the same pool on a child generator default_rng([*seed, LEVEL_STREAM]),
so the position stream, and every next-open null, is unchanged. Slots left
unfilled are counted (null_unfilled); an event with no filled null bar is
dropped_no_match.
"""
from __future__ import annotations

import zlib
from dataclasses import dataclass

import numpy as np
import pandas as pd

from swingbot.core.backtesting.screen import indicators, race as race_mod

K = 20
MIN_CANDIDATES = 5
SEED_BASE = 42
LEVEL_STREAM = 1   # v182: the level null's replacement draws, never the position stream


def null_seed(idea: str, ticker: str, base: int = SEED_BASE) -> list:
    """Deterministic per (idea, ticker), derived from 42."""
    return [base, zlib.crc32(idea.encode()), zlib.crc32(ticker.encode())]


def child_seed(seed) -> list:
    """The level null's replacement stream: the seed extended by LEVEL_STREAM."""
    if isinstance(seed, (list, tuple)):
        return [*seed, LEVEL_STREAM]
    return [int(seed), LEVEL_STREAM]


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
class NullGroups:
    event_pos: np.ndarray
    groups: tuple
    fills: tuple | None
    dropped_no_match: int
    null_slots: int
    null_unfilled: int
    null_depths: tuple


@dataclass(frozen=True, eq=False)
class NullDraw:
    event_pos: np.ndarray
    groups: tuple
    null_mean_r: np.ndarray
    null_race: race_mod.RaceResult
    dropped_no_match: int
    null_slots: int = 0
    null_unfilled: int = 0
    null_depths: tuple = ()


def _empty(dropped: int, slots: int = 0, unfilled: int = 0) -> NullDraw:
    return NullDraw(np.array([], dtype=int), (), np.array([], dtype=float),
                    race_mod.RaceResult.empty(), dropped, slots, unfilled)


def _null_fills(df, positions, d: float, atr_v, direction: str):
    """Fill price per null position and whether it filled (level rule 3).
    The level is computed only where p >= 1 and ATR14[p-1] is finite and > 0."""
    if direction not in ("short", "long"):
        raise ValueError(f"unknown direction {direction!r}; expected 'long' or 'short'")
    positions = np.asarray(positions, dtype=int)
    fill = np.full(positions.size, np.nan)
    a = np.full(positions.size, np.nan)
    ok = positions >= 1
    a[ok] = atr_v[positions[ok] - 1]
    ok &= np.isfinite(a) & (a > 0)
    valid = positions[ok]
    o = df["Open"].to_numpy(dtype=float)[valid]
    if direction == "short":
        level = o - d * a[ok]
        reached = df["Low"].to_numpy(dtype=float)[valid] <= level
    else:
        level = o + d * a[ok]
        reached = df["High"].to_numpy(dtype=float)[valid] >= level
    fill[ok] = level
    ok[ok] = reached
    return fill, ok


def _level_group(df, pool, m: int, first, d: float, atr_v, child, direction: str):
    """One event's filled null positions and fills, sorted by position
    (level rules 3-4): unfilled first draws are replaced in the order of
    ``child.permutation`` of the rest of the pool."""
    fill, ok = _null_fills(df, first, d, atr_v, direction)
    pos, fills = first[ok], fill[ok]
    rest = np.setdiff1d(pool, first)
    if pos.size < m and rest.size:
        order = child.permutation(rest)
        more_fill, more_ok = _null_fills(df, order, d, atr_v, direction)
        need = m - pos.size
        pos = np.concatenate([pos, order[more_ok][:need]])
        fills = np.concatenate([fills, more_fill[more_ok][:need]])
    idx = np.argsort(pos, kind="stable")
    return pos[idx], fills[idx]


def _realised_depth(df, pos, fills, atr_v, direction: str) -> np.ndarray:
    o = df["Open"].to_numpy(dtype=float)[pos]
    gap = o - fills if direction == "short" else fills - o
    return gap / atr_v[pos - 1]


def _draw_next_open(df, event_pos, eligible, k: int, seed, trend) -> NullGroups:
    """The v140 draw, call for call on ``default_rng(seed)``."""
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
    return NullGroups(np.asarray(kept, dtype=int), tuple(groups), None, dropped,
                      sum(len(g) for g in groups), 0, ())


def _draw_level(df, event_pos, eligible, k: int, seed, atr, trend, direction,
                depth) -> NullGroups:
    """Level mode (rules 1-5): first draws on the main stream exactly as the
    next-open draw, replacements on the child stream."""
    event_pos = np.asarray(event_pos, dtype=int)
    depth = np.asarray(depth, dtype=float)
    if len(depth) != len(event_pos):
        raise ValueError("depth needs one value per event")
    atr_v = (indicators.atr(df) if atr is None else pd.Series(atr)).to_numpy(dtype=float)
    rng = np.random.default_rng(seed)
    months = month_key(df.index)
    child = np.random.default_rng(child_seed(seed))
    kept, groups, fills, depths = [], [], [], []
    dropped = slots = unfilled = 0
    for pos, d in zip(event_pos, depth):
        pool = candidates(pos, eligible, months, trend)
        if len(pool) < MIN_CANDIDATES:
            dropped += 1
            continue
        m = min(k, len(pool))
        slots += m
        first = rng.choice(pool, size=m, replace=False)
        group, fill = _level_group(df, pool, m, first, float(d), atr_v, child, direction)
        unfilled += m - group.size
        if group.size == 0:
            dropped += 1
            continue
        kept.append(pos)
        groups.append(group)
        fills.append(fill)
        depths.extend(_realised_depth(df, group, fill, atr_v, direction).tolist())
    return NullGroups(np.asarray(kept, dtype=int), tuple(groups), tuple(fills), dropped,
                      slots, unfilled, tuple(depths))


def draw_groups(df, event_pos, eligible, k: int, seed, *, atr, trend,
                direction: str = "long", depth=None) -> NullGroups:
    """The null positions per event, no race. ``depth=None`` is the
    next-open draw; one ``depth`` per event (in ATR14[t-1]) switches on
    level mode (v182)."""
    if depth is None:
        return _draw_next_open(df, event_pos, eligible, k, seed, trend)
    return _draw_level(df, event_pos, eligible, k, seed, atr, trend, direction, depth)


def matched_null(df, event_pos, eligible, k: int, seed, *, cap: int, atr,
                 trend, slippage_bps=None, commission=None,
                 shape: str = "fixed", direction: str = "long", depth=None,
                 level_factor: float = race_mod.LEVEL_SLIPPAGE_FACTOR) -> NullDraw:
    """``shape`` is the idea's race shape: a trail idea's null is a trail
    null (v163). The null is raced in the idea's ``direction`` (v182). The
    next-open draw depends on neither; ``depth`` switches on level mode."""
    race_fn = race_mod.race_for(shape)
    g = draw_groups(df, event_pos, eligible, k, seed, atr=atr, trend=trend,
                    direction=direction, depth=depth)
    if not g.groups:
        return _empty(g.dropped_no_match, g.null_slots, g.null_unfilled)
    extra = {} if direction == "long" else {"direction": direction}
    if g.fills is not None:
        extra.update(fill=np.concatenate(g.fills), level_factor=level_factor)
    raced = race_fn(df, np.concatenate(g.groups), cap, atr=atr,
                    slippage_bps=slippage_bps, commission=commission, **extra)
    bounds = np.cumsum([len(x) for x in g.groups])[:-1]
    means = np.array([part.mean() for part in np.split(raced.r, bounds)])
    return NullDraw(g.event_pos, g.groups, means, raced, g.dropped_no_match,
                    g.null_slots, g.null_unfilled, g.null_depths)
