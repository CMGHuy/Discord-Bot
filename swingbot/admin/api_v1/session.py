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

from swingbot import config

# The app/helpers MODULES, not names out of them -- see the note in auth.py.
from swingbot.admin import app as _app
from swingbot.admin import helpers as _helpers

from . import api_v1, error
from .auth import require_auth


def _identity() -> dict:
    """The one body all three /session methods return.

    Always the same shape, so the SPA's SessionStore has a single reducer
    for login, logout and the boot check rather than three.
    """
    authed = _app._session_authenticated()
    return {"authenticated": authed,
            "username": _app.ADMIN_USERNAME if authed else None}


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
    if username != _app.ADMIN_USERNAME or password != _app.ADMIN_PASSWORD:
        return error("auth", "Invalid username or password.", 401)
    # Same four lines as login_submit() in app.py: clear first so a partially
    # populated older session cannot survive, then pin the credential hash so
    # changing ADMIN_PASSWORD invalidates this session (see _password_hash).
    session.clear()
    session["admin_authed"] = True
    session["pw_hash"] = _app._password_hash()
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
    """The "am I up" probe, and the shell's footer.

    Auth-guarded, unlike a public liveness probe --
    `test_health_requires_auth_and_returns_json_401` pins that and it is not
    changed here. The shell only reads it once signed in anyway.

    SR58 adds `market_active`. It belongs HERE rather than on `/dashboard`
    even though the parity row was found on the dashboard: "are these prices
    live" is a global fact, the indicator sits beside the connection status
    in the shell, and a shell that read a workspace's endpoint to render its
    own chrome would break the moment that workspace is not open.

    (`api_v1/session.py` is outside SR58's declared `Owns:` set. Recorded in
    the plan rather than worked around: the alternative was putting a
    shell-level fact on a workspace endpoint, and no concurrent task owns
    this file.)

    Never raises: an unavailable market check reports False rather than
    failing the probe that monitoring uses to decide the admin is down.
    """
    try:
        from swingbot.core.marketdata.data import is_us_market_active
        market_active = bool(is_us_market_active())
    except Exception:
        market_active = False

    return jsonify({
        "ok": True,
        "versions": _helpers.get_versions(),
        "market_active": market_active,
        # The account's currency symbol, for the same reason `market_active`
        # is here: it is a global fact about every figure the SPA renders, not
        # a property of one workspace's response. The SPA had "USD" hardcoded
        # beside the balance, the realised P&L and the total P&L, which was
        # simply wrong -- CURRENCY_SYMBOL has defaulted to EUR since it was
        # introduced, and nothing was reading it.
        #
        # This is the FALLBACK symbol, i.e. the account's own currency. It is
        # not per-ticker: `/market/chart` resolves that per instrument through
        # `get_currency_symbol`, because a Euronext listing and a NASDAQ one
        # genuinely price in different units. Account-level totals have one
        # currency and this is it.
        "currency": config.CURRENCY_SYMBOL,
    })
