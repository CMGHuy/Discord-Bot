"""v190 section 2.3 -- the reused-symbol detector and the kept side.

Why: MON. The yfinance reference for MON ends at Monsanto's exit from the
index, so the vendor identity check sees nothing after the symbol was reused
by another issuer; the Alpaca series carries on under the same ticker with a
different company's bars. So the break test runs on **every** member, over
the whole stored series, not just where a reference exists.

The series gaps exist because price and volume alone miss a reuse by an
issuer of similar size, and the ~220 ``no-reference`` names have no yfinance
series at all: a stored series running well past the last membership end
(or past the reference's last bar) or starting well before the first
membership start is flagged, and that stretch is then scanned with priority
(``find_breaks(..., sessions_from=...)``).

The kept side follows membership, never the break: a trade open at the
member's exit walks only the member's own bars, and warm-up indicators never
read an earlier issuer's bars. Splits never reach the detector as a jump
because the store is fetched with ``Adjustment.ALL``.

The detector looks forward from a candidate bar (the no-revert window and
the after-median). That is fine here: its output is a frozen data decision
taken before any strategy result is read -- it is never a signal.

The rules (spec 2.3; frozen here, recalibrated only in V190-21 before any
strategy result is read):

| Rule | Definition |
|---|---|
| Candidate | bar `i >= 1` with a finite `abs(Close[i] / Close[i-1] - 1) > break_move`; a NaN or non-positive close is never a candidate |
| Edge | fewer than `edge_sessions` bars before `i` (`i < edge_sessions`) or after it (`n - 1 - i < edge_sessions`): kind `"edge"`, no further test (the no-revert test cannot run) |
| No revert | every close in `Close[i : i + revert_sessions + 1]` differs from the median of `Close[i - revert_sessions : i]` by more than `break_move` (relative); a one-bar spike and its return leg both fail this |
| Level shift | `max(a/b, b/a) >= break_ratio` for the medians of `Volume` (kind `"volume"`) or of `Close` (kind `"price"`), `MEDIAN_WINDOW` bars after (`[i, i+50)`) versus before (`[i-50, i)`); both -> `"price+volume"`; a non-positive or NaN median on one side only is an infinite ratio, on both sides a ratio of 1 |
| Stretch scan | with `sessions_from` set, a non-edge, non-reverting candidate dated on or after it that has **no** level shift is still a break, kind `"move"` -- "the break test runs on that stretch with priority, whatever the price or volume does" (a reuse by an issuer of similar size); before `sessions_from` the level shift stays required |
| Gaps | sessions counted on the SPY calendar `sessions` over half-open ranges: `start` = `[first bar, first membership start)`; `end` = `[last membership end, last bar + 1 day)`; `reference-end` = `[reference_last + 1 day, last bar + 1 day)`; a gap is listed when its count is `> gap_sessions`; no spans -> no start/end gap; an open span (`9999-12-31`) -> no end gap |
| Kept side | break dated before the first membership start -> `trim_before`, `keep_from` = the latest such date; dated on or after the last membership end -> `trim_after`, `keep_before` = the earliest such date; anything else (inside a span, or between two spans) -> `unresolved` when it lies within `edge_sessions` bars of the frame's first or last bar (computed from `frame` and `thresholds`, whatever its kind), else `in_span`. No spans (a context symbol: SPY, an ETF) -> no side can be kept: every break is `in_span` or `unresolved` |

``in_span`` and ``unresolved`` never trim: admission is refused for them with
the break named, so the builder resolves each by hand -- never silently.

No ``swingbot`` import: pandas and numpy only.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

MEDIAN_WINDOW = 50

TRIM_AFTER = "trim_after"
TRIM_BEFORE = "trim_before"
IN_SPAN = "in_span"
UNRESOLVED = "unresolved"

REASON_AFTER = "break after last membership end"
REASON_BEFORE = "break before first membership start"

_SHIFT_KINDS = {(True, True): "price+volume", (True, False): "price", (False, True): "volume"}
_ONE_DAY = pd.Timedelta(days=1)


@dataclass(frozen=True)
class Thresholds:
    break_move: float = 0.50
    break_ratio: float = 10.0
    revert_sessions: int = 20
    gap_sessions: int = 20
    edge_sessions: int = 20


THRESHOLDS = Thresholds()


@dataclass(frozen=True)
class Break:
    date: str
    kind: str


# --- find_breaks ----------------------------------------------------------------------

def _usable(value: float) -> bool:
    return bool(np.isfinite(value)) and value > 0


def _ratio(a: float, b: float) -> float:
    """Level-shift ratio; a bad (non-positive/NaN) median on one side is infinite."""
    a_ok, b_ok = _usable(a), _usable(b)
    if not a_ok and not b_ok:
        return 1.0
    if not (a_ok and b_ok):
        return float("inf")
    return max(a / b, b / a)


def _median(values: np.ndarray) -> float:
    if values.size == 0 or not np.isfinite(values).any():
        return float("nan")
    return float(np.nanmedian(values))


def _persistent(closes: np.ndarray, i: int, thresholds: Thresholds) -> bool:
    """No revert: every close from i over the next revert_sessions bars stays far off."""
    window = thresholds.revert_sessions
    before = _median(closes[max(i - window, 0):i])
    if not _usable(before):
        return False
    after = closes[i:i + window + 1]
    with np.errstate(invalid="ignore"):
        return bool(np.all(np.abs(after / before - 1.0) > thresholds.break_move))


def _shifted(values: np.ndarray, i: int, thresholds: Thresholds) -> bool:
    before = _median(values[max(i - MEDIAN_WINDOW, 0):i])
    after = _median(values[i:i + MEDIAN_WINDOW])
    return _ratio(after, before) >= thresholds.break_ratio


def _shift_kind(frame: pd.DataFrame, i: int, thresholds: Thresholds) -> str | None:
    closes = frame["Close"].to_numpy(dtype=float)
    volumes = frame["Volume"].to_numpy(dtype=float)
    key = (_shifted(closes, i, thresholds), _shifted(volumes, i, thresholds))
    return _SHIFT_KINDS.get(key)


def _iso(stamp) -> str:
    return pd.Timestamp(stamp).strftime("%Y-%m-%d")


def _classify(frame: pd.DataFrame, closes: np.ndarray, i: int, thresholds: Thresholds,
              sessions_from: str | None) -> str | None:
    n = len(closes)
    if i < thresholds.edge_sessions or n - 1 - i < thresholds.edge_sessions:
        return "edge"
    if not _persistent(closes, i, thresholds):
        return None
    kind = _shift_kind(frame, i, thresholds)
    if kind is not None:
        return kind
    if sessions_from is not None and _iso(frame.index[i]) >= sessions_from[:10]:
        return "move"
    return None


def find_breaks(frame: pd.DataFrame | None, thresholds: Thresholds = THRESHOLDS, *,
                sessions_from: str | None = None) -> list[Break]:
    """Every reused-symbol break in the stored series, in date order."""
    if frame is None or len(frame) < 2:
        return []
    closes = frame["Close"].to_numpy(dtype=float)
    prev, cur = closes[:-1], closes[1:]
    with np.errstate(divide="ignore", invalid="ignore"):
        move = np.abs(cur / prev - 1.0)
        candidate = np.isfinite(move) & (move > thresholds.break_move) & (prev > 0) & (cur > 0)
    breaks = []
    for i in np.flatnonzero(candidate) + 1:
        kind = _classify(frame, closes, int(i), thresholds, sessions_from)
        if kind is not None:
            breaks.append(Break(_iso(frame.index[i]), kind))
    return breaks


# --- series_gaps ----------------------------------------------------------------------

def _naive(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    index = pd.DatetimeIndex(index)
    if index.tz is not None:
        index = index.tz_localize(None)
    return index.normalize()


def _count(sessions: pd.DatetimeIndex, start: str, end_excl: str) -> int:
    days = _naive(sessions)
    return int(((days >= pd.Timestamp(start)) & (days < pd.Timestamp(end_excl))).sum())


def _gap_ranges(first: str, after_last: str, spans: list[tuple[str, str]],
                reference_last: str | None) -> list[tuple[str, str, str]]:
    ranges = []
    if spans:
        ranges.append(("start", first, min(start for start, _ in spans)))
        ranges.append(("end", max(end for _, end in spans), after_last))
    if reference_last is not None:
        ranges.append(("reference-end", _iso(pd.Timestamp(reference_last) + _ONE_DAY), after_last))
    return ranges


def series_gaps(frame: pd.DataFrame | None, spans: list[tuple[str, str]],
                reference_last: str | None, sessions: pd.DatetimeIndex,
                thresholds: Thresholds = THRESHOLDS) -> list[dict]:
    """Stretches where the stored series runs past membership or the reference."""
    if frame is None or len(frame) == 0:
        return []
    index = _naive(frame.index)
    first, after_last = _iso(index[0]), _iso(index[-1] + _ONE_DAY)
    gaps = []
    for kind, start, end_excl in _gap_ranges(first, after_last, spans, reference_last):
        if start >= end_excl:
            continue
        count = _count(sessions, start, end_excl)
        if count > thresholds.gap_sessions:
            gaps.append({"kind": kind, "from": start, "to": end_excl, "sessions": count})
    return gaps


# --- resolve --------------------------------------------------------------------------

def _near_frame_edge(frame: pd.DataFrame | None, date: str, thresholds: Thresholds) -> bool:
    n = 0 if frame is None else len(frame)
    if n == 0:
        return True
    pos = int(_naive(frame.index).searchsorted(pd.Timestamp(date)))
    return pos < thresholds.edge_sessions or n - 1 - pos < thresholds.edge_sessions


def _side(date: str, spans: list[tuple[str, str]]) -> str | None:
    if not spans:
        return None
    if date < min(start for start, _ in spans):
        return TRIM_BEFORE
    if date >= max(end for _, end in spans):
        return TRIM_AFTER
    return None


def _trim(before: list[str], after: list[str]) -> dict | None:
    if not before and not after:
        return None
    reasons = ([REASON_BEFORE] if before else []) + ([REASON_AFTER] if after else [])
    return {"keep_from": max(before) if before else None,
            "keep_before": min(after) if after else None,
            "reason": "; ".join(reasons)}


def resolve(breaks: list[Break], spans: list[tuple[str, str]], frame: pd.DataFrame,
            thresholds: Thresholds = THRESHOLDS) -> dict:
    """The kept side of each break, which follows the membership spans."""
    rows, kept = [], {TRIM_BEFORE: [], TRIM_AFTER: []}
    for brk in sorted(breaks, key=lambda b: b.date):
        resolution = _side(brk.date, spans)
        if resolution is not None:
            kept[resolution].append(brk.date)
        elif _near_frame_edge(frame, brk.date, thresholds):
            resolution = UNRESOLVED
        else:
            resolution = IN_SPAN
        rows.append({"date": brk.date, "kind": brk.kind, "resolution": resolution})
    return {"trim": _trim(kept[TRIM_BEFORE], kept[TRIM_AFTER]), "breaks": rows}
