"""/api/v1/session and /api/v1/health.

Spec v11 Decision 5. The SPA authenticates with the EXISTING signed session
cookie -- no JWT, no token endpoint, no refresh flow. These routes are a
JSON front door onto the same `session["admin_authed"]` + `pw_hash`
mechanism `/login` and `/logout` already drive, so a session established
through either door is valid on the other. That matters for the whole
migration: both UIs are live at once until cutover.

Auth helpers are imported from `.app` rather than reimplemented, so there
is exactly one place that decides what "logged in" means. The decorator
comes from `.auth`, not from api.py -- same predicate, v1 error body.
"""
from __future__ import annotations

from flask import jsonify, request, session

from swingbot.admin.app import (
    ADMIN_PASSWORD,
    ADMIN_USERNAME,
    _password_hash,
    _session_authenticated,
)
from swingbot.admin.helpers import get_versions

from . import api_v1, error
from .auth import require_auth


def _identity() -> dict:
    """The one body all three /session methods return.

    Always the same shape, so the SPA's SessionStore has a single reducer
    for login, logout and the boot check rather than three.
    """
    authed = _session_authenticated()
    return {"authenticated": authed, "username": ADMIN_USERNAME if authed else None}


@api_v1.route("/session", methods=["GET"])
def session_get():
    """Deliberately NOT auth-guarded.

    This is the question "am I logged in", asked by the SPA at boot before
    the shell renders. Returning 401 to an unauthenticated caller would make
    the question unanswerable to the only caller that needs to ask it, so it
    answers 200 with `authenticated: false` instead.
    """
    return jsonify(_identity())


@api_v1.route("/session", methods=["POST"])
def session_create():
    payload = request.get_json(silent=True) or {}
    username = payload.get("username", "")
    password = payload.get("password", "")
    if username != ADMIN_USERNAME or password != ADMIN_PASSWORD:
        return error("auth", "Invalid username or password.", 401)
    # Same four lines as login_submit() in app.py: clear first so a partially
    # populated older session cannot survive, then pin the credential hash so
    # changing ADMIN_PASSWORD invalidates this session (see _password_hash).
    session.clear()
    session["admin_authed"] = True
    session["pw_hash"] = _password_hash()
    session.permanent = True
    return jsonify(_identity())


@api_v1.route("/session", methods=["DELETE"])
def session_delete():
    """Idempotent. The SPA calls this on a 401 to clear local state, and that
    path must not itself fail when there is no session to clear."""
    session.clear()
    return jsonify(_identity())


@api_v1.route("/health", methods=["GET"])
@require_auth
def health():
    return jsonify({"ok": True, "versions": get_versions()})
