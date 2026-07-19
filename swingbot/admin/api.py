"""JSON API blueprint for the admin cockpit — /api/*. Every view here is
consumed by this plan's own AJAX-driven pages (Plans board polling, job
progress streaming, journal note edits) as well as anything scripted
against the admin UI directly. Auth-guarded like every other admin route,
but returns a JSON 401 body instead of an HTML challenge page/redirect,
since a JS fetch() caller needs a body it can actually parse rather than
a login-style response.
"""
from functools import wraps

from flask import Blueprint, jsonify, request

from swingbot.core.analytics.rank import follow_score, rank_plans
from swingbot.core.analytics.snapshots import load_snapshot
from swingbot.core.analytics.snapshots import refresh_snapshot as _rebuild_snapshot
from swingbot.core.plan_engine import PlanStatus, plan_to_dict
from swingbot.core.plan_store import PlanStore

from .app import ADMIN_PASSWORD, ADMIN_USERNAME
from .helpers import get_versions

api = Blueprint("api", __name__, url_prefix="/api")

_ALL_PLAN_STATUSES = (
    PlanStatus.PENDING, PlanStatus.ACTIVE, PlanStatus.PARTIAL,
    PlanStatus.CLOSED, PlanStatus.CANCELLED,
)


def refresh_snapshot() -> dict | None:
    """Local wrapper around analytics.snapshots.refresh_snapshot: the real
    function is fire-and-forget (rebuilds + persists analytics_snapshot.json,
    returns None -- see its other callers in scanning.py/performance.py,
    which never use a return value). This route needs the freshly-built
    dict back, so it rebuilds then re-reads what was just saved."""
    _rebuild_snapshot()
    return load_snapshot(max_age_seconds=3600)


def require_auth_json(view):
    """Same Basic-Auth check as app.py's require_auth, but the failure
    response is a JSON body ({"error": "auth"}) rather than a plain-text
    401 challenge -- a fetch() caller can branch on r.status === 401 and
    still get a parseable body instead of an HTML/text blob."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        auth = request.authorization
        if not auth or auth.username != ADMIN_USERNAME or auth.password != ADMIN_PASSWORD:
            return jsonify({"error": "auth"}), 401
        return view(*args, **kwargs)
    return wrapped


@api.route("/health", methods=["GET"])
@require_auth_json
def health():
    return jsonify({"ok": True, "versions": get_versions()})


@api.route("/stats", methods=["GET"])
@require_auth_json
def api_stats():
    """The Plan A snapshot, forwarded verbatim -- this route computes
    nothing itself (see the plan's "UI renders, analytics computes"
    constraint). ?fresh=1 always rebuilds; otherwise a missing/expired
    snapshot self-heals on this very request rather than 500ing."""
    if request.args.get("fresh") == "1":
        snap = refresh_snapshot()
    else:
        snap = load_snapshot(max_age_seconds=3600)
        if snap is None:
            snap = refresh_snapshot()
    return jsonify(snap)


def _ranked_plan_rows(plans: list) -> list[dict]:
    """Ranks `plans` by analytics.rank.rank_plans (the one shared ordering)
    and serializes each to a JSON-safe dict with its follow_score attached.
    rank_plans itself returns ordered TradePlanV2 objects, not dicts -- this
    is the one place /api/plans converts between the two."""
    ranked = rank_plans(plans)
    return [dict(plan_to_dict(p), follow_score=follow_score(p)) for p in ranked]


def _plan_rows(status: str | None = None, tier: str | None = None,
               badge: str | None = None) -> dict:
    """Shared data-fetch for /api/plans (this task) and the Plans board
    page (extracted to pages.py and imported back here in Task C14, so
    both surfaces slice identically per the plan's Global Constraints).
    Counts are always computed from the UNFILTERED set -- the lifecycle
    strip (C15) must show the true per-status totals no matter which
    status/tier/badge filter is currently applied to the row list."""
    all_plans = PlanStore().all()
    counts = {s: 0 for s in _ALL_PLAN_STATUSES}
    for p in all_plans:
        counts[p.status] = counts.get(p.status, 0) + 1

    rows = _ranked_plan_rows(all_plans)
    if status:
        rows = [r for r in rows if r["status"] == status]
    if tier:
        rows = [r for r in rows if r["tier"] == tier]
    if badge:
        rows = [r for r in rows if r["badge"] == badge]
    return {"plans": rows, "counts": counts}


@api.route("/plans", methods=["GET"])
@require_auth_json
def api_plans():
    return jsonify(_plan_rows(
        status=request.args.get("status") or None,
        tier=request.args.get("tier") or None,
        badge=request.args.get("badge") or None,
    ))
