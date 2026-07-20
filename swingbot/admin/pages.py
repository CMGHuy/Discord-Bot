"""Page-rendering blueprint for the cockpit's new sections: Plans,
Strategies, Calibration, Journal, Tuning. Split out of app.py (which keeps
Dashboard/Performance/Watchlist/Settings/Logs) purely to keep any one file
from growing unbounded -- same reasoning as api.py. Every view here uses
app.py's existing require_auth (HTML 401 challenge, not JSON) and _render
helper, since these are full pages a human loads in a browser, not fetch()
targets (those live in api.py).
"""
from flask import Blueprint, render_template, request

from swingbot.core.analytics.rank import follow_score, rank_plans
from swingbot.core.plan_engine import PlanStatus, plan_to_dict
from swingbot.core.plan_store import PlanStore

from .app import _is_today_berlin, _render, require_auth

pages = Blueprint("pages", __name__)

_ALL_PLAN_STATUSES = (
    PlanStatus.PENDING, PlanStatus.ACTIVE, PlanStatus.PARTIAL,
    PlanStatus.CLOSED, PlanStatus.CANCELLED,
)


def _ranked_plan_rows(plans: list) -> list[dict]:
    """Ranks `plans` by analytics.rank.rank_plans (the one shared ordering)
    and serializes each to a JSON-safe dict with its follow_score attached.
    rank_plans itself returns ordered TradePlanV2 objects, not dicts -- this
    is the one place the Plans board / /api/plans convert between the two."""
    ranked = rank_plans(plans)
    return [dict(plan_to_dict(p), follow_score=follow_score(p)) for p in ranked]


def _plan_rows(status: str | None = None, tier: str | None = None,
               badge: str | None = None) -> dict:
    """Shared by the Plans board page (this task) and /api/plans (api.py
    imports this function instead of keeping its own copy). Counts are
    always computed from the UNFILTERED set (Task C15 refines this
    further to scope CLOSED/CANCELLED counts to "today")."""
    all_plans = PlanStore().all()
    counts = {s: 0 for s in _ALL_PLAN_STATUSES}
    for p in all_plans:
        if p.status in (PlanStatus.CLOSED, PlanStatus.CANCELLED):
            last_at = p.status_history[-1]["at"] if p.status_history else None
            if not _is_today_berlin(last_at):
                continue  # only today's closes/cancels count toward the strip
        counts[p.status] = counts.get(p.status, 0) + 1

    rows = _ranked_plan_rows(all_plans)
    if status:
        rows = [r for r in rows if r["status"] == status]
    if tier:
        rows = [r for r in rows if r["tier"] == tier]
    if badge:
        rows = [r for r in rows if r["badge"] == badge]
    return {"plans": rows, "counts": counts}


def _render_plans_board(rows: list, counts: dict, filters: dict) -> str:
    return render_template("_plans_board.html", plans=rows, counts=counts, filters=filters)


@pages.route("/plans", methods=["GET"])
@require_auth
def plans_page():
    filters = {
        "status": request.args.get("status", ""),
        "tier": request.args.get("tier", ""),
        "badge": request.args.get("badge", ""),
    }
    result = _plan_rows(status=filters["status"] or None, tier=filters["tier"] or None,
                        badge=filters["badge"] or None)
    fragment = _render_plans_board(result["plans"], result["counts"], filters)
    return _render("Plans", "plans", "plans.html", fragment=fragment)


@pages.route("/strategies", methods=["GET"])
@require_auth
def strategies_page():
    return _render("Strategies", "strategies", "strategies.html")


@pages.route("/calibration", methods=["GET"])
@require_auth
def calibration_page():
    return _render("Calibration", "calibration", "calibration.html")


@pages.route("/journal", methods=["GET"])
@require_auth
def journal_page():
    return _render("Journal", "journal", "journal.html")


@pages.route("/tuning", methods=["GET"])
@require_auth
def tuning_page():
    return _render("Tuning", "tuning", "tuning.html")
