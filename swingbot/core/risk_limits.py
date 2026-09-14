"""Non-negotiable risk boundaries shared by scanning and plan execution."""
from __future__ import annotations

from math import inf


# This limits the intended entry-to-initial-stop loss. It cannot prevent a
# market gap or slippage from producing a worse *realized* exit.
HARD_MAX_PLANNED_LOSS_PCT = 2.0


def capped_planned_loss_pct(configured_pct: float) -> float:
    """Return the stricter of the operator setting and the hard safety cap."""
    return min(float(configured_pct), HARD_MAX_PLANNED_LOSS_PCT)


def planned_loss_pct(entry_price: float | None, stop_loss: float | None) -> float:
    """Initial stop distance as a percentage of entry, or infinity if invalid."""
    if entry_price is None or stop_loss is None or entry_price <= 0:
        return inf
    return abs(entry_price - stop_loss) / entry_price * 100
