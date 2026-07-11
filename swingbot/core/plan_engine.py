"""Unified trade-plan engine v2.

Single authority for plan construction and exit policy (spec:
docs/superpowers/specs/2026-07-11-unified-plan-engine-design.md).
Everything that emits a trade plan — scan alerts, strategy signals,
backtests, the live plan manager — builds and prices it here.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from swingbot.core.registry import Badge, get_badge


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


# Strategy-source plans enter at the signal close ("market") — this is the
# entry the round-1 validation measured. Task 30's TRAIN grid may flip
# breakout-class strategies to stop_entry iff it clears the acceptance gates.
STRATEGY_ENTRY_TYPE: dict[str, str] = {}

# Rendered verbatim by embeds for plans whose source failed the 80% OOS bar.
WEAK_CAUTION_TEXT = (
    "⚠️ WEAK: this setup did not reach 80% win rate out-of-sample "
    "(WR {win_rate:.1f}%, N={n}). Treat with extra care — reduced size, "
    "manual confirmation recommended."
)


def entry_type_for(strategy: str, source: str) -> str:
    if source == "confluence":
        return "stop_entry"
    return STRATEGY_ENTRY_TYPE.get(strategy, "market")


def stamp_badge(plan: TradePlanV2) -> None:
    """Set badge + badge_stats from the committed validation registry."""
    b = get_badge(plan.source, plan.strategy, plan.horizon_key)
    plan.badge = b.status
    plan.badge_stats = {"status": b.status, "n": b.n, "win_rate": b.win_rate,
                        "expectancy_r": b.expectancy_r, "window": b.window}


def badge_stats_line(badge: Badge) -> str:
    window = badge.window.replace("-01-01..", "-").replace("-12-31", "") or "n/a"
    return (f"OOS {window}: N={badge.n}, WR {badge.win_rate:.1f}%, "
            f"ExpR {badge.expectancy_r:+.3f}")


def record_transition(plan: TradePlanV2, new_status: str, reason: str | None = None,
                      at: str | None = None) -> None:
    """Apply a lifecycle transition, enforcing the legal state machine."""
    allowed = _LEGAL_TRANSITIONS.get(plan.status, set())
    if new_status not in allowed:
        raise ValueError(f"illegal transition {plan.status} -> {new_status}")
    plan.status = new_status
    plan.status_history.append({"status": new_status, "reason": reason, "at": at})
