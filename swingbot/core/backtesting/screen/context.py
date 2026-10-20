"""v174 context hook: other markets an idea may read, point in time.

An idea module that exports ``CONTEXT = ("TLT",)`` receives those frames as
``events(df, context)``. Everything here is pure: the trailing z of a
5-day return, the gate on it, and the exact-date alignment onto a stock's
own index. A value at t reads context bars dated <= t only, and a stock date
the context lacks is ``False``, never forward-filled (v174 spec § 1, § 3).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

#: First bar of backtest_cache_ext/SPY.csv: the context window starts here,
#: so 5 + 252 warm-up bars exist well before EVENT_START (2011-01-01).
CONTEXT_START = "2009-06-01"
LOOKBACK = 5
Z_WINDOW = 252
#: std(W) at or below this is the floating-point form of std(W) == 0.
STD_FLOOR = 1e-12

#: Defined z must cover this share of SPY sessions in the event window, or
#: the file would spend a shot on an idea that can hardly fire (v174 § 1).
MIN_Z_COVERAGE = 0.95


def r_lookback(close: pd.Series, lookback: int = LOOKBACK) -> pd.Series:
    """close(t) / close(t - lookback) - 1, by row offset (the contiguity
    check against SPY sessions makes the row offset a session offset)."""
    close = close.astype(float)
    return close / close.shift(lookback) - 1.0


def trailing_z(close: pd.Series, lookback: int = LOOKBACK,
               window: int = Z_WINDOW) -> pd.Series:
    """z(t) = (r(t) - mean(W)) / std(W, ddof=0), W = r[t-window .. t-1].

    W is trailing and excludes t. NaN when W is short, W or r(t) holds a
    NaN, or std(W) <= STD_FLOOR."""
    values = r_lookback(close, lookback).to_numpy(dtype=float)
    z = np.full(len(values), np.nan)
    if len(values) > window:
        win = sliding_window_view(values[:-1], window)   # win[i] = r[i .. i+window-1], t = i+window
        with np.errstate(invalid="ignore", divide="ignore"):
            mean = win.mean(axis=1)                      # NaN when W holds a NaN
            std = win.std(axis=1)                        # population std (ddof=0)
            cur = values[window:]
            ok = np.isfinite(cur) & np.isfinite(mean) & (std > STD_FLOOR)
            z[window:] = np.where(ok, (cur - mean) / np.where(ok, std, 1.0), np.nan)
    return pd.Series(z, index=close.index, name="z", dtype=float)


def z_gate(z: pd.Series, threshold: float) -> pd.Series:
    """z >= threshold for a positive threshold, z <= threshold otherwise.
    An undefined z is no event."""
    hit = z >= threshold if threshold > 0 else z <= threshold
    return hit.fillna(False).astype(bool)


def context_on(df_index: pd.DatetimeIndex, series: pd.Series) -> pd.Series:
    """A context series on a stock's dates, by exact date. A stock date the
    context lacks is False, never forward-filled; a context-only date is
    dropped."""
    return series.astype(bool).reindex(df_index, fill_value=False).astype(bool)


def near_mask(raw: np.ndarray, cap: int) -> np.ndarray:
    """True at i when some True position p in ``raw`` has |i - p| < cap
    (the restricted-null diagnostic drops these bars from the null pool)."""
    raw = np.asarray(raw, dtype=bool)
    n = len(raw)
    pos = np.flatnonzero(raw)
    marks = np.zeros(n + 1, dtype=int)            # +1 opens a run, -1 closes it
    np.add.at(marks, np.maximum(pos - cap + 1, 0), 1)
    np.add.at(marks, np.minimum(pos + cap, n), -1)
    return np.cumsum(marks[:n]) > 0


class ContextError(ValueError):
    """A context file the screen must not run on; the runner refuses with it."""


def check_raw_index(index: pd.Index, name: str) -> None:
    """The CSV index as written, before load_frame repairs it: one date
    index, tz-naive, sorted, unique, every stamp at midnight."""
    if not isinstance(index, pd.DatetimeIndex):
        raise ContextError(f"{name}: the Date column is not a date index")
    if index.tz is not None:
        raise ContextError(f"{name}: the raw index is tz-aware ({index.tz}); "
                           f"the cache is tz-naive")
    if not index.is_monotonic_increasing:
        raise ContextError(f"{name}: the raw index is not sorted")
    if index.has_duplicates:
        raise ContextError(f"{name}: the raw index is not unique "
                           f"({int(index.duplicated().sum())} repeated dates)")
    if (index != index.normalize()).any():
        raise ContextError(f"{name}: the raw index is not normalised "
                           f"(a stamp other than midnight)")


def check_contiguous(index: pd.DatetimeIndex, sessions: pd.DatetimeIndex,
                     name: str) -> None:
    """Context bars match SPY sessions, so r5's row offset is a session offset."""
    missing = sessions.difference(index)
    if len(missing):
        raise ContextError(
            f"{name}: {len(missing)} SPY session(s) missing between "
            f"{sessions[0]:%Y-%m-%d} and {sessions[-1]:%Y-%m-%d}, "
            f"first {missing[0]:%Y-%m-%d}")
    extra = index.difference(sessions)
    if len(extra):
        raise ContextError(
            f"{name}: {len(extra)} extra bar date(s) absent from SPY sessions, "
            f"first {extra[0]:%Y-%m-%d}; row offsets must follow SPY sessions")


def check_z_coverage(z: pd.Series, sessions: pd.DatetimeIndex, name: str, *,
                     event_start: str, minimum: float = MIN_Z_COVERAGE) -> None:
    """Defined z on at least ``minimum`` of the SPY sessions from
    ``event_start``; a session z never saw counts as undefined."""
    window = sessions[sessions >= pd.Timestamp(event_start)]
    if not len(window):
        raise ContextError(f"{name}: no SPY session from {event_start}")
    share = float(z.reindex(window).notna().mean())
    if share < minimum:
        raise ContextError(
            f"{name}: defined z covers {share:.1%} of {len(window)} SPY sessions "
            f"from {event_start}; the floor is {minimum:.0%}")


def file_record(path) -> dict:
    """What the results doc prints and the hash file pins for one CSV."""
    path = Path(path)
    if not path.is_file():
        raise ContextError(f"{path.stem}: context file {path} is missing")
    try:
        dates = pd.read_csv(path, usecols=["Date"])["Date"].astype(str)
    except (ValueError, OSError) as exc:
        raise ContextError(f"{path.stem}: cannot read Date column from {path}: {exc}") from exc
    if dates.empty:
        raise ContextError(f"{path.stem}: context file {path} has no rows")
    return {"ticker": path.stem, "rows": int(len(dates)),
            "first": dates.min()[:10], "last": dates.max()[:10],
            "fetched": date.fromtimestamp(path.stat().st_mtime).isoformat(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


@dataclass(frozen=True)
class ContextData:
    """The context frames an idea reads, the SPY calendar they were checked
    against, and one file record per frame."""
    frames: Mapping[str, pd.DataFrame]
    calendar: pd.DataFrame
    records: Mapping[str, dict]
    # The runner retains the whole registered union before loading any frames.
    checked_records: Mapping[str, dict] = field(default_factory=dict)
