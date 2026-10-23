"""v182 descriptive maths for short and level ideas: pure, never reads R.

Check 5 (spec Part B) is the only function here that decides anything, and it
decides only whether range_breakdown_stop may be run at all: it compares the
fill depths of the events with those of their matched null, outcome-blind,
inside --count-only. V182-17 adds the results-doc blocks (overlap, SPY
regime split, trend-only control), all printed and never gating.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from swingbot.core.backtesting.screen import indicators

#: |median null depth - median event depth| allowed, in ATR14[t-1] (check 5).
DEPTH_MEDIAN_TOL = 0.05
#: Share of null slots left unfilled allowed (check 5).
NULL_UNFILLED_MAX = 0.20

_EMPTY = {"n": 0, "q1": None, "median": None, "q3": None, "gap_share": None}


def depth_summary(values) -> dict:
    """Quartiles, median and the share of gap fills (depth exactly 0)."""
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        return dict(_EMPTY)
    q1, median, q3 = np.percentile(arr, [25, 50, 75])
    return {"n": int(arr.size), "q1": float(q1), "median": float(median),
            "q3": float(q3), "gap_share": float(np.mean(arr == 0.0))}


def _verdict(ok: bool) -> str:
    return "pass" if ok else "FAIL"


def _depth_clause(event_depths, null_depths) -> tuple[bool, str]:
    events, nulls = depth_summary(event_depths), depth_summary(null_depths)
    if events["n"] == 0:
        return False, "median depth: no event depths -> FAIL"
    if nulls["n"] == 0:
        return False, "median depth: no filled null -> FAIL"
    gap = abs(nulls["median"] - events["median"])
    ok = gap <= DEPTH_MEDIAN_TOL
    return ok, (f"median depth: events {events['median']:.3f} ATR, null "
                f"{nulls['median']:.3f} ATR, |difference| {gap:.3f} "
                f"{'<=' if ok else '>'} {DEPTH_MEDIAN_TOL} -> {_verdict(ok)}")


def _unfilled_clause(null_slots: int, null_unfilled: int) -> tuple[bool, str]:
    if null_slots <= 0:
        return False, "null_unfilled: no null slots -> FAIL"
    share = null_unfilled / null_slots
    ok = share <= NULL_UNFILLED_MAX
    return ok, (f"null_unfilled: {null_unfilled} of {null_slots} null slots "
                f"({100.0 * share:.1f}%) {'<=' if ok else '>'} "
                f"{100.0 * NULL_UNFILLED_MAX:.0f}% -> {_verdict(ok)}")


def check_fill_depth(event_depths, null_depths, null_slots: int,
                     null_unfilled: int) -> tuple[bool, list[str]]:
    """Check 5: the null's median fill depth within DEPTH_MEDIAN_TOL ATR of
    the events', and at most NULL_UNFILLED_MAX of the null slots unfilled."""
    depth_ok, depth_line = _depth_clause(event_depths, null_depths)
    fill_ok, fill_line = _unfilled_clause(null_slots, null_unfilled)
    return depth_ok and fill_ok, [depth_line, fill_line]


#: SPY's regime average, in bars (spec Part C: "SPY above/below its 200-day average").
SPY_SMA = 200


def event_overlap(own, other) -> dict:
    """Bars flagged by each idea and by both (spec Part C: the two ideas are nested)."""
    own, other = np.asarray(own, dtype=bool), np.asarray(other, dtype=bool)
    if own.shape != other.shape:
        raise ValueError(f"event_overlap needs equal-length flags, got {own.shape} and {other.shape}")
    return {"own": int(own.sum()), "other": int(other.sum()), "both": int((own & other).sum())}


def spy_above_200(spy: pd.DataFrame) -> pd.Series:
    """SPY's close above its 200-day SMA, only on the bars where the SMA exists."""
    average = indicators.sma(spy["Close"], SPY_SMA)
    return (spy["Close"] > average)[average.notna()]


def paired_delta(rows) -> tuple[int, float | None]:
    """(n, mean(R_event - mean R_null)) of event rows; (0, None) for none."""
    d = [row["r_event"] - row["r_null"] for row in rows]
    return len(d), (float(np.mean(d)) if d else None)


def regime_split(events, above: pd.Series) -> dict:
    """The event pairs by SPY's regime at the last SPY close strictly before
    entry: the signal close for a next-open entry, bar t-1 for a level entry
    -- known when the order is placed either way. Reported, never gating."""
    index = pd.DatetimeIndex(above.index)
    flags = above.to_numpy(dtype=bool)
    groups = {"above": [], "below": [], "unknown": []}
    for row in events:
        pos = index.searchsorted(pd.Timestamp(row["entry_date"]), side="left") - 1
        groups["unknown" if pos < 0 else ("above" if flags[pos] else "below")].append(row)
    return {"above": paired_delta(groups["above"]), "below": paired_delta(groups["below"]),
            "unknown": len(groups["unknown"])}
