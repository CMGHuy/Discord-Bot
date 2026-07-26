"""Stops and targets sized by the strategy's OWN excursion history
instead of one ATR multiple for everything.

MAE (maximum adverse excursion): how far winners went against you before
working. Stops inside the winners' P90 MAE amputate trades that were
about to work; stops far beyond it buy nothing but smaller position
sizes. MFE (E32) is the mirror image for targets. Everything here is
flag-gated (DATA_DRIVEN_STOPS_ENABLED) and fold-validated before live.
"""
from __future__ import annotations

import numpy as np

MIN_SAMPLE = 40          # winners needed before the distribution means anything
MAE_CUSHION_R = 0.15     # breathing room beyond the winners' P90
CLAMP = (0.8, 1.3)       # never move a stop by more than this factor


def mae_informed_stop_mult(entries: list, strategy: str) -> float | None:
    """Winners-only by design: a LOSER's MAE is by definition at least the
    stop it hit, so feeding losers in would ratchet stops wider on exactly
    the trades that should have been cut."""
    maes = [e["mae_r"] for e in entries
            if e.get("strategy") == strategy and e.get("outcome") == "win"
            and e.get("mae_r") is not None]
    if len(maes) < MIN_SAMPLE:
        return None
    p90 = float(np.percentile(maes, 90))
    return float(min(max(p90 + MAE_CUSHION_R, CLAMP[0]), CLAMP[1]))


TP2_FLOOR_R = 0.5
TIME_STOP_COVERAGE = 0.80


def mfe_informed_tp2_r(entries: list, strategy: str) -> float | None:
    """P60 of winners' max favorable excursion: a TP2 the runner actually
    reaches more often than not, instead of a hope."""
    mfes = [e["mfe_r"] for e in entries
            if e.get("strategy") == strategy and e.get("outcome") == "win"
            and e.get("mfe_r") is not None]
    if len(mfes) < MIN_SAMPLE:
        return None
    return float(max(np.percentile(mfes, 60), TP2_FLOOR_R))


def optimal_time_stop_days(entries: list, strategy: str) -> int | None:
    """Day by which TIME_STOP_COVERAGE of eventual winners had already
    reached +0.5R. A position slower than that is statistically dead
    capital -- frequency (the compounding lever) says recycle it.

    Advisory only: nothing in this codebase closes a position on it. E48's
    recycler is the intended consumer."""
    days = sorted(e["days_to_half_r"] for e in entries
                  if e.get("strategy") == strategy and e.get("outcome") == "win"
                  and e.get("days_to_half_r") is not None)
    if len(days) < MIN_SAMPLE:
        return None
    idx = int(np.ceil(TIME_STOP_COVERAGE * len(days))) - 1
    return int(days[idx])
