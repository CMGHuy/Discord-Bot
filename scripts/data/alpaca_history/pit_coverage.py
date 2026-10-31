"""v190 section 2.1: causal coverage cuts for the PIT Alpaca store.

The PIT store's session calendar is SPY's own daily bars: the NYSE calendar in
swingbot/core/market/session.py starts 2018-01-01 and cannot cover 2016-2017.

There is no whole-span verdict. A span-level coverage share would let bars
missing in 2024 decide a 2017 date and push delisted names out of the mask
(quant-engineer finding 1). Instead every missing run is listed, runs longer
than MAX_MISSING_RUN sessions are cut, and the trailing rule reads only the
sessions up to and including the date it judges. An IPO inside a span is cut
until 57 of its trailing 60 sessions exist, which no indicator warm-up would
use anyway.

The thresholds are frozen in _integrity.json and may be recalibrated only in
V190-21, before any strategy result is read. Pure pandas: this module never
imports swingbot, so it runs against any store root.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

STORE_START = "2016-01-04"
STORE_END = "2025-12-31"
STORE_END_EXCL = "2026-01-01"          # the day after STORE_END; spans are half-open

MAX_MISSING_RUN = 5
TRAILING_SESSIONS = 60
MIN_TRAILING_SHARE = 0.95

RUN_REASON = "missing run of {n} sessions"
TRAILING_REASON = "trailing 60-session coverage under 95%"

_NO_SPY = "no SPY daily bars in the PIT store: SPY is the session calendar"


def _iso(ts) -> str:
    return pd.Timestamp(ts).strftime("%Y-%m-%d")


def _days(bars) -> pd.DatetimeIndex:
    """None -> empty; any timestamps -> unique sorted dates."""
    if bars is None:
        return pd.DatetimeIndex([])
    return pd.DatetimeIndex(bars).normalize().unique().sort_values()


def expected_sessions(spy_daily: pd.DataFrame | None) -> pd.DatetimeIndex:
    """SPY's bar dates inside [STORE_START, STORE_END]: the session calendar."""
    if spy_daily is None or spy_daily.empty:
        raise ValueError(_NO_SPY)
    days = _days(spy_daily.index)
    days = days[(days >= pd.Timestamp(STORE_START)) & (days <= pd.Timestamp(STORE_END))]
    if days.empty:
        raise ValueError(_NO_SPY)
    return days


def clip_span(span: tuple[str, str]) -> tuple[str, str] | None:
    """Clip a half-open span to the store window; None when nothing is left."""
    start, end = max(span[0], STORE_START), min(span[1], STORE_END_EXCL)
    return (start, end) if start < end else None


def _span_positions(sessions: pd.DatetimeIndex, span: tuple[str, str]) -> np.ndarray:
    """Integer positions of the calendar sessions with span[0] <= s < span[1]."""
    inside = (sessions >= pd.Timestamp(span[0])) & (sessions < pd.Timestamp(span[1]))
    return np.flatnonzero(inside)


def _group(positions, sessions: pd.DatetimeIndex, span_end: str) -> list[tuple[str, str, int]]:
    """Consecutive calendar positions -> (first session, end_excl, length)."""
    runs, start = [], None
    for i, pos in enumerate(positions):
        if start is None:
            start = pos
        last = i + 1 == len(positions) or positions[i + 1] != pos + 1
        if last:
            nxt = _iso(sessions[pos + 1]) if pos + 1 < len(sessions) else span_end
            runs.append((_iso(sessions[start]), min(nxt, span_end), int(pos - start + 1)))
            start = None
    return runs


def _present(days: pd.DatetimeIndex, sessions: pd.DatetimeIndex) -> np.ndarray:
    return np.asarray(sessions.isin(days), dtype=bool)


def missing_runs(bars, sessions: pd.DatetimeIndex, span: tuple[str, str]) -> list[tuple[str, str, int]]:
    """Every run of consecutive in-span sessions without a bar, in date order."""
    present = _present(_days(bars), sessions)
    positions = _span_positions(sessions, span)
    return _group(positions[~present[positions]], sessions, span[1])


def _trailing_ok(present: np.ndarray) -> np.ndarray:
    """Per calendar position: does its trailing window (up to and including it) pass?"""
    csum = np.cumsum(present.astype(int))
    lagged = np.concatenate([np.zeros(TRAILING_SESSIONS, dtype=int), csum[:-TRAILING_SESSIONS]])
    count = csum - lagged[: len(csum)]
    length = np.minimum(np.arange(1, len(csum) + 1), TRAILING_SESSIONS)
    return count / length >= MIN_TRAILING_SHARE


def trailing_failures(bars, sessions: pd.DatetimeIndex, span: tuple[str, str]) -> list[tuple[str, str]]:
    """Runs of in-span sessions whose trailing-60 coverage is under 95%."""
    ok = _trailing_ok(_present(_days(bars), sessions))
    positions = _span_positions(sessions, span)
    failing = positions[~ok[positions]]
    return [(start, end) for start, end, _ in _group(failing, sessions, span[1])]


def _span_coverage(days: pd.DatetimeIndex, sessions: pd.DatetimeIndex,
                   span: tuple[str, str]) -> tuple[dict, list[tuple[str, str, str]]]:
    """One clipped span's coverage record and its signal cuts."""
    positions = _span_positions(sessions, span)
    runs = missing_runs(days, sessions, span)
    entry = {"span": [span[0], span[1]], "expected": int(len(positions)),
             "present": int(_present(days, sessions)[positions].sum()),
             "missing_runs": [[start, end, n] for start, end, n in runs]}
    cuts = [(start, end, RUN_REASON.format(n=n)) for start, end, n in runs if n > MAX_MISSING_RUN]
    cuts += [(start, end, TRAILING_REASON) for start, end in trailing_failures(days, sessions, span)]
    return entry, cuts


def coverage_entry(bars, sessions: pd.DatetimeIndex,
                   spans) -> tuple[list[dict], list[tuple[str, str, str]]]:
    """Per clipped span a coverage record; signal cuts sorted by (start, end_excl, reason)."""
    days = _days(bars)
    coverage, cuts = [], []
    for raw in spans:
        span = clip_span(tuple(raw))
        if span is None:
            continue
        entry, span_cuts = _span_coverage(days, sessions, span)
        coverage.append(entry)
        cuts.extend(span_cuts)
    return coverage, sorted(cuts)
