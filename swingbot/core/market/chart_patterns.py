"""Chart-pattern geometry. Currently one pattern: the dead cat bounce.

This is the bot's first multi-pivot pattern, and it exists as a VETO rather
than as a signal -- see the v68 spec for why the obvious version (feeding
patterns into count_confirming_strategies) is a closed branch: v49 measured
cross-family redundancy at 0.628 with N_eff capped at 1.746, and v36 measured
the level-touch primitive underneath double top/bottom at no lift.

PURE BY CONSTRUCTION. Frame and params in, verdict out -- no config reads, no
I/O, no caching. Two reasons, both load-bearing:

  * it is testable against synthetic frames with no fixtures;
  * the v68 TRAIN grid evaluates twelve parameter cells at each entry bar in
    ONE replay pass, which is only possible because calling this twelve times
    is cheap and side-effect-free.

NO-LOOKAHEAD: only df.iloc[-1] and earlier are ever read. No negative shift,
no centered window. tests/market/test_chart_patterns_causality.py proves it.
"""
from __future__ import annotations

import pandas as pd

#: The four fixed values are set from reasoning in the v68 spec and are NOT
#: grid dimensions -- widening the grid to include them is a different
#: pre-registration. The three grid dimensions carry their permissive default.
DEFAULT_DCB_PARAMS = {
    # fixed
    "lookback": 20,          # ~1 trading month, the span a sharp decline occupies
    "retrace_max": 0.50,     # Fibonacci midpoint; past half it is not "dead"
    "bounce_min_bars": 2,    # a bounce, not one green candle
    "gap_pct": 5.0,          # a real breakaway gap; read only when gap_required
    # gridded
    "decline_pct": 20.0,
    "gap_required": False,
    "volume_ratio": None,    # None disables the conviction test
}

_ABSENT = {"detected": False, "decline_pct": None, "retrace": None,
           "gapped": False, "volume_ratio": None}


def dead_cat_bounce(df: pd.DataFrame, params: dict | None = None) -> dict:
    """Is the bar at df.index[-1] sitting in a weak bounce after a hard drop?

    Returns the verdict plus the evidence behind it -- the evidence is not
    decoration, it is what makes a firing veto auditable after the fact.
    """
    p = {**DEFAULT_DCB_PARAMS, **(params or {})}
    lookback, min_bars = int(p["lookback"]), int(p["bounce_min_bars"])

    # An uncomputable gate BLOCKS nothing -- entry_filters.py's convention.
    if df is None or len(df) < lookback + min_bars:
        return dict(_ABSENT)

    window = df.iloc[-lookback:]
    closes = window["Close"]

    trough_pos = int(closes.to_numpy().argmin())
    # The trough must be old enough that what followed is a bounce rather than
    # one bar of noise, and it must not be the window's first bar -- there the
    # decline started before the window and its magnitude is unmeasurable.
    if trough_pos == 0 or (len(window) - 1 - trough_pos) < min_bars:
        return dict(_ABSENT)

    trough = float(closes.iloc[trough_pos])
    peak = float(closes.iloc[:trough_pos].max())
    if peak <= trough:
        return dict(_ABSENT)

    decline_pct = (peak - trough) / peak * 100.0
    if decline_pct < float(p["decline_pct"]):
        return dict(_ABSENT)

    # Clause 3 above is what guarantees peak > trough, so this cannot divide
    # by zero. Order matters; do not reorder these two.
    close_now = float(closes.iloc[-1])
    if close_now <= trough:
        return dict(_ABSENT)                       # still falling, not bouncing
    retrace = (close_now - trough) / (peak - trough)
    if retrace > float(p["retrace_max"]):
        return dict(_ABSENT)                       # a recovery, not a dead cat

    decline_slice = window.iloc[: trough_pos + 1]
    bounce_slice = window.iloc[trough_pos + 1:]

    gapped = _has_gap_down(decline_slice, float(p["gap_pct"]))
    if p["gap_required"] and not gapped:
        return dict(_ABSENT)

    vol_ratio = _volume_ratio(decline_slice, bounce_slice)
    if p["volume_ratio"] is not None:
        if vol_ratio is None or vol_ratio > float(p["volume_ratio"]):
            return dict(_ABSENT)

    return {"detected": True, "decline_pct": decline_pct, "retrace": retrace,
            "gapped": gapped, "volume_ratio": vol_ratio}


def _has_gap_down(decline: pd.DataFrame, gap_pct: float) -> bool:
    """Did any bar of the decline open at least gap_pct below the prior close?"""
    if "Open" not in decline.columns or len(decline) < 2:
        return False
    prior_close = decline["Close"].shift(1)        # positive shift only
    gap = (prior_close - decline["Open"]) / prior_close * 100.0
    return bool((gap >= gap_pct).fillna(False).any())


def _volume_ratio(decline: pd.DataFrame, bounce: pd.DataFrame) -> float | None:
    """Mean bounce volume / mean decline volume, or None when unmeasurable."""
    if "Volume" not in decline.columns or bounce.empty or decline.empty:
        return None
    down = float(decline["Volume"].mean())
    up = float(bounce["Volume"].mean())
    if not down or pd.isna(down) or pd.isna(up):
        return None
    return up / down
