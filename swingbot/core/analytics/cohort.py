"""v144: one cohort's own numbers -- the outlook lane's fill rate, win rate,
ExpR of the filled trades and cancellation-reason histogram. Never pooled: the
caller passes the whole book and this reads only `origin == cohort`. Whether
the cohort ever pools is a later, measured decision (spec v144 § Analytics)."""
from __future__ import annotations

from collections import Counter

from swingbot.core.analytics import metrics as m
from swingbot.core.analytics.partials import is_filled
from swingbot.core.analytics.scope import CLOSED_STATUSES
from swingbot.core.planning.session_expiry import cancel_reason
from swingbot.core.tracking.origin import in_cohort


def cohort_report(plans: list, trades: list[dict], origin: str) -> dict:
    issued = [plan for plan in plans if in_cohort(plan, origin)]
    filled = [plan for plan in issued if is_filled(plan)]
    closed = [t for t in trades if in_cohort(t, origin) and t.get("status") in CLOSED_STATUSES]
    reasons = Counter(reason for reason in map(cancel_reason, issued) if reason)
    return {
        "origin": origin, "n": len(issued), "issued": len(issued), "filled": len(filled),
        "fill_rate_pct": round(len(filled) / len(issued) * 100, 2) if issued else None,
        "closed": len(closed), "win_rate": m.win_rate(closed),
        "expectancy_r": m.expectancy_r(closed),
        "cancel_reasons": dict(sorted(reasons.items())),
    }
