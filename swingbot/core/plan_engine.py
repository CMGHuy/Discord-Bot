"""Unified trade-plan engine v2.

Single authority for plan construction and exit policy (spec:
docs/superpowers/specs/2026-07-11-unified-plan-engine-design.md).
Everything that emits a trade plan — scan alerts, strategy signals,
backtests, the live plan manager — builds and prices it here.
"""
from __future__ import annotations

from dataclasses import dataclass, field


class PlanStatus:
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    PARTIAL = "PARTIAL"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


_LEGAL_TRANSITIONS = {
    PlanStatus.PENDING: {PlanStatus.ACTIVE, PlanStatus.CANCELLED},
    PlanStatus.ACTIVE: {PlanStatus.PARTIAL, PlanStatus.CLOSED},
    PlanStatus.PARTIAL: {PlanStatus.CLOSED},
}


@dataclass
class TradePlanV2:
    plan_id: str
    ticker: str
    created_at: str            # ISO date of the bar/scan that created the plan
    source: str                # "strategy" | "confluence"
    strategy: str              # exact ALL_STRATEGIES string of the generating strategy
    horizon_key: str
    direction: str             # "bullish" | "bearish"
    entry_type: str            # "stop_entry" | "market"
    trigger_price: float
    entry_price: float | None
    expiry_bars: int
    stop_loss: float
    tp1: float
    tp1_fraction: float
    tp2: float | None
    breakeven_trigger_fraction: float
    trail_atr_mult: float
    quality_score: int
    quality_breakdown: list
    tier: str                  # "A" | "B" | "C"
    badge: str                 # "VALIDATED" | "WEAK"
    badge_stats: dict
    status: str
    status_history: list = field(default_factory=list)


def record_transition(plan: TradePlanV2, new_status: str, reason: str | None = None,
                      at: str | None = None) -> None:
    """Apply a lifecycle transition, enforcing the legal state machine."""
    allowed = _LEGAL_TRANSITIONS.get(plan.status, set())
    if new_status not in allowed:
        raise ValueError(f"illegal transition {plan.status} -> {new_status}")
    plan.status = new_status
    plan.status_history.append({"status": new_status, "reason": reason, "at": at})
