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
