"""v104 stop scope and ceiling helpers for structural stops."""
from __future__ import annotations

from swingbot.core.market.strategy_types import HORIZONS, SHORT_STRATEGIES
from swingbot.core.risk_limits import HARD_MAX_PLANNED_LOSS_PCT, capped_planned_loss_pct

CAP = "cap"
DROP = "drop"
_ALWAYS_IN_SCOPE = frozenset(name.lower() for name in SHORT_STRATEGIES)


def scope_pairs(raw: str | None = None) -> frozenset[tuple[str, str]]:
    """Parse case- and space-insensitive ``Strategy:direction`` pairs."""
    if raw is None:
        from swingbot import config

        raw = getattr(config, "STRUCTURAL_STOP_SCOPE", "") or ""
    pairs = set()
    for item in str(raw).split(","):
        name, separator, direction = item.rpartition(":")
        if separator and name.strip() and direction.strip():
            pairs.add((name.strip().lower(), direction.strip().lower()))
    return frozenset(pairs)


def in_scope(strategy: str, direction: str, raw: str | None = None) -> bool:
    """Return whether the strategy-direction pair retains its structural stop."""
    name = str(strategy).strip().lower()
    if name in _ALWAYS_IN_SCOPE:
        return True
    return (name, str(direction).strip().lower()) in scope_pairs(raw)


def stop_ceiling(
    strategy: str,
    direction: str,
    horizon_key: str,
    raw: str | None = None,
) -> tuple[float, str]:
    """Return the stop ceiling percent and whether to cap or drop beyond it."""
    max_risk = HORIZONS[horizon_key]["max_risk_pct"]
    if in_scope(strategy, direction, raw):
        return float(max_risk), DROP
    return capped_planned_loss_pct(max_risk), CAP


def plan_stop_ceiling(plan) -> float:
    """Return the persisted plan's allowed planned-loss percentage."""
    if getattr(plan, "source", None) != "strategy":
        return HARD_MAX_PLANNED_LOSS_PCT
    return stop_ceiling(plan.strategy, plan.direction, plan.horizon_key)[0]


def risk_sizing_ok(plan, sizing_fn=None) -> bool:
    """Return whether an in-scope plan has safe risk-based dollar sizing."""
    if not in_scope(plan.strategy, plan.direction):
        return True
    if sizing_fn is None:
        from swingbot.core.planning.account import compute_position_size as sizing_fn
    try:
        sizing = sizing_fn(plan.trigger_price, plan.stop_loss)
    except Exception:
        return False
    if not sizing or sizing.get("mode") != "risk_pct":
        return False
    try:
        budget = float(sizing.get("balance") or 0.0) * float(sizing.get("risk_pct") or 0.0) / 100.0
        shares = float(sizing.get("shares") or 0.0)
        actual_risk = shares * abs(plan.trigger_price - plan.stop_loss)
    except (TypeError, ValueError):
        return False
    return 0.0 < actual_risk <= budget
