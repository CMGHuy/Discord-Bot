"""Pre-registered v93 trust rule for enabling strategy alerts."""
from __future__ import annotations

import statistics

from swingbot.core.backtesting.acceptance import NON_INFERIORITY_R

MIN_CLOSED = 30
MAX_ENTRY_DEV = 0.10


def plan_r_total(plan) -> float | None:
    legs = getattr(plan, "legs_realized", None) or []
    return sum(float(leg["fraction"]) * float(leg["r"]) for leg in legs) if legs else None


def _entry_dev(plan) -> float | None:
    entry = plan.entry_price or plan.trigger_price
    if plan.first_seen_price is None or entry is None or plan.stop_loss is None:
        return None
    distance = abs(entry - plan.stop_loss)
    return abs(plan.first_seen_price - entry) / distance if distance else None


def soak_verdict(shadow_plans: list, badge) -> dict:
    closed = [plan for plan in shadow_plans if getattr(plan, "status", None) == "CLOSED"]
    returns = [r for r in (plan_r_total(plan) for plan in closed) if r is not None]
    deviations = [d for d in (_entry_dev(plan) for plan in closed) if d is not None]
    exp_r = statistics.fmean(returns) if returns else None
    badge_exp_r = badge.expectancy_r if getattr(badge, "n", 0) > 0 else None
    median_dev = statistics.median(deviations) if deviations else None
    clauses = {"n": len(closed) >= MIN_CLOSED,
               "non_inferior": exp_r is not None and badge_exp_r is not None and exp_r >= badge_exp_r + NON_INFERIORITY_R,
               "entry_parity": median_dev is not None and median_dev <= MAX_ENTRY_DEV}
    return {"n_closed": len(closed), "exp_r": exp_r, "badge_exp_r": badge_exp_r,
            "median_entry_dev": median_dev, "clauses": clauses, "pass": all(clauses.values())}
