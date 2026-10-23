"""v182 descriptive maths for short and level ideas: pure, never reads R.

Check 5 (spec Part B) is the only function here that decides anything, and it
decides only whether range_breakdown_stop may be run at all: it compares the
fill depths of the events with those of their matched null, outcome-blind,
inside --count-only. V182-17 adds the results-doc blocks (overlap, SPY
regime split, trend-only control), all printed and never gating.
"""
from __future__ import annotations

import numpy as np

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
