"""Risk-on/off composite — a pure function over the upstream context dicts.

Post-audit scope: the win-rate audit cut credit stress (G22) and the yield
curve (G19) with the FRED series layer, so the composite runs on the three
inputs that actually move day to day — VIX regime, sector rotation posture,
and breadth — and renormalizes over whichever of them are available.
"""
from __future__ import annotations

from swingbot.core.macro.breadth import breadth_state

_VIX_VOTE = {"calm": 1, "normal": 0, "elevated": 0, "stress": -1}
_TRI_VOTE = {"risk_on": 1, "mixed": 0, "risk_off": -1,
             "healthy": 1, "weak": -1}


def risk_composite(vix, rotation, breadth) -> dict:
    """Each available input votes -1/0/+1; score = mean * 100.
    Fewer than 2 usable inputs -> label "unknown" (never a guess)."""
    votes, detail = [], []

    def _vote(value: int, text: str):
        votes.append(value)
        detail.append(f"{text} ({value:+d})")

    if vix and vix.get("regime"):
        _vote(_VIX_VOTE.get(vix["regime"], 0), f"VIX {vix['regime']}")
    if rotation and rotation.get("posture") in ("risk_on", "mixed", "risk_off"):
        _vote(_TRI_VOTE[rotation["posture"]], f"rotation {rotation['posture']}")
    if breadth and breadth.get("pct_above_50dma") is not None:
        state = breadth_state(breadth)
        _vote(_TRI_VOTE.get(state, 0), f"breadth {state}")

    if len(votes) < 2:
        return {"score": 0, "label": "unknown",
                "inputs_used": len(votes), "detail": detail}
    score = round(100.0 * sum(votes) / len(votes))
    label = "risk_on" if score > 33 else "risk_off" if score < -33 else "neutral"
    return {"score": score, "label": label,
            "inputs_used": len(votes), "detail": detail}
