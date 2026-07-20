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

from swingbot.core.analytics.journal import JournalStore
from swingbot.core.analytics.snapshots import load_snapshot
from swingbot.core.analytics.snapshots import refresh_snapshot as _rebuild_snapshot

from .app import ADMIN_PASSWORD, ADMIN_USERNAME
from .helpers import get_versions
from .pages import _plan_rows, _registry_rows

api = Blueprint("api", __name__, url_prefix="/api")


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


@api.route("/plans", methods=["GET"])
@require_auth_json
def api_plans():
    return jsonify(_plan_rows(
        status=request.args.get("status") or None,
        tier=request.args.get("tier") or None,
        badge=request.args.get("badge") or None,
    ))


def _parse_bool_param(v: str | None) -> bool | None:
    if v is None or v == "":
        return None
    return v.lower() in ("1", "true", "yes")


@api.route("/journal", methods=["GET"])
@require_auth_json
def api_journal():
    # The real JournalStore.entries() has no `limit` kwarg (it returns
    # every matching entry, newest first) -- this route applies the
    # documented ?limit= query param itself rather than passing it
    # through to a parameter that doesn't exist.
    store = JournalStore()
    entries = store.entries(
        strategy=request.args.get("strategy") or None,
        tag=request.args.get("tag") or None,
        outcome=request.args.get("outcome") or None,
        has_note=_parse_bool_param(request.args.get("has_note")),
    )
    limit = int(request.args.get("limit", 100))
    return jsonify({"entries": entries[:limit]})


@api.route("/journal/<trade_id>/note", methods=["POST"])
@require_auth_json
def api_journal_note(trade_id):
    payload = request.get_json(silent=True) or {}
    note = request.form.get("note", payload.get("note", ""))
    ok = JournalStore().set_note(trade_id, note)
    if not ok:
        return jsonify({"ok": False}), 404
    return jsonify({"ok": True})


@api.route("/calibration", methods=["GET"])
@require_auth_json
def api_calibration():
    snap = load_snapshot(max_age_seconds=3600) or refresh_snapshot()
    calibration = snap.get("calibration", {}) if snap else {}
    return jsonify({
        "deciles": calibration.get("deciles", []),
        "tiers": calibration.get("tiers", []),
        "drift": calibration.get("drift", []),
    })


@api.route("/registry", methods=["GET"])
@require_auth_json
def api_registry():
    return jsonify({"registry": _registry_rows()})
