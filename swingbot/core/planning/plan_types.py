"""Plan v2 data model, persistence shape, and legal transition recording."""
from __future__ import annotations

import dataclasses
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
    badge: str                 # "VALIDATED" | "WEAK"
    badge_stats: dict
    status: str
    status_history: list = field(default_factory=list)
    working_stop: float | None = None   # None = "use stop_loss"; live BE/trail floor
    legs_realized: list = field(default_factory=list)  # [{fraction, exit_price, r, reason}]
    runner_high_close: float | None = None  # extreme price since TP1 (bearish: extreme LOW)
    # E31: the MAE-informed factor this plan's ATR stop was actually scaled
    # by, or None when it wasn't (flag off / too few journaled winners /
    # a structure-derived stop). Its own field rather than a
    # quality_breakdown row because it is NOT a scored component -- that
    # list is strictly (name, points) tuples, rendered as `{pts:+d}` by
    # embeds.py and views.py and flattened by plan_to_dict, so a note
    # smuggled in there would crash both renderers and corrupt the
    # persisted JSON. Kept on the plan so E33's folds and E40's shadow
    # gate can audit which plans were sized with it, after the fact.
    stop_mult_applied: float | None = None
    # E32, same rationale: the MFE-derived R-multiple this plan's TP2 was
    # priced at (None when the level-based TP2 stood), and the day by
    # which most of this strategy's winners had already reached +0.5R.
    # time_stop_days is ADVISORY -- nothing here closes a position on it;
    # E48's recycler is the intended consumer.
    tp2_r_applied: float | None = None
    time_stop_days: int | None = None
    # E38: the one pyramid SUGGESTION emitted for this plan, or None. Its
    # presence is what makes the add fire at most once. The bot never sizes
    # real money -- this records what was suggested, not a position.
    pyramid_add: dict | None = None
    # v32 Task 11: A/B/C tier (quality.py's own 0-100 quality_score bands)
    # retired in favour of confidence LEVEL -- confidence.py's
    # ConfidenceResult.level, the method-count-plus-quality gate that
    # actually decides whether an alert fires (score_plan()'s quality_score
    # never gated anything). Set from item.conf.level in
    # _build_quality_inputs, a genuinely different number from
    # quality_score -- optional because not every _apply_quality caller
    # (e.g. the offline decile-audit script) has a live scan's conf in hand.
    confidence_level: int | None = None
    # The ET session dates on which break-even and runner-floor protections
    # armed. None marks legacy plans whose persisted record predates v64.
    be_armed_session: str | None = None
    runner_floor_session: str | None = None


def effective_stop(plan: TradePlanV2) -> float:
    return plan.working_stop if plan.working_stop is not None else plan.stop_loss


_PLAN_FIELDS = None   # cached field list


def plan_to_dict(plan: TradePlanV2) -> dict:
    d = dataclasses.asdict(plan)
    # tuples (quality_breakdown rows) -> lists so json round-trips cleanly
    d["quality_breakdown"] = [list(row) for row in d.get("quality_breakdown", [])]
    return d


def plan_from_dict(d: dict) -> TradePlanV2:
    global _PLAN_FIELDS
    if _PLAN_FIELDS is None:
        _PLAN_FIELDS = {f.name for f in dataclasses.fields(TradePlanV2)}
    known = {k: v for k, v in d.items() if k in _PLAN_FIELDS}
    return TradePlanV2(**known)   # missing fields use dataclass defaults


def record_transition(plan: TradePlanV2, new_status: str, reason: str | None = None,
                      at: str | None = None) -> None:
    """Apply a lifecycle transition, enforcing the legal state machine."""
    allowed = _LEGAL_TRANSITIONS.get(plan.status, set())
    if new_status not in allowed:
        raise ValueError(f"illegal transition {plan.status} -> {new_status}")
    plan.status = new_status
    plan.status_history.append({"status": new_status, "reason": reason, "at": at})



