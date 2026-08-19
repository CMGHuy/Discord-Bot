"""Symmetric relative-strength gate (v34).

Tri-state on purpose. 'exempt' is NOT 'pass': an FX pair and a stock whose RS
fetch failed both skip the check, and conflating either with a real pass would
report a comparison that never ran.

The rs_available flag exists because rs_percentile() returns 50.0 -- not None --
when it cannot compute (edge/factors.py:33-37). Without the flag, a failed
fetch is indistinguishable from a genuine median reading, and the middle band
would block it in both directions.
"""
from __future__ import annotations

from swingbot import config
from swingbot.core.marketdata.asset_class import classify, is_rs_eligible


def rs_verdict(symbol: str, direction: str, rs_value: float,
               rs_available: bool) -> dict:
    if not is_rs_eligible(symbol):
        return {"status": "exempt",
                "reason": f"{classify(symbol)} is exempt from RS-vs-SPY"}
    if not rs_available:
        return {"status": "exempt", "reason": "RS unavailable for this ticker"}

    if direction == "bullish":
        if rs_value >= config.RS_LEADER_PERCENTILE:
            return {"status": "pass",
                    "reason": f"RS {rs_value:.0f} is a relative leader"}
        return {"status": "block",
                "reason": f"RS {rs_value:.0f} below the "
                          f"{config.RS_LEADER_PERCENTILE:.0f} leader threshold"}

    if rs_value <= config.RS_LAGGARD_PERCENTILE:
        return {"status": "pass",
                "reason": f"RS {rs_value:.0f} is a relative laggard"}
    return {"status": "block",
            "reason": f"RS {rs_value:.0f} above the "
                      f"{config.RS_LAGGARD_PERCENTILE:.0f} laggard threshold"}
