"""NG4 — /api/v1/session and /api/v1/health.

Spec v11 Decision 5: the SPA reuses the EXISTING signed session cookie.
No JWT, no token endpoint, no refresh flow. These endpoints are a JSON
front door onto the same `session["admin_authed"]` + `pw_hash` mechanism
`/login` and `/logout` already drive, so a session created through either
door works on the other.

`GET /api/v1/session` is the one with no Jinja equivalent: it answers "is
my cookie still good" at SPA boot, before the shell renders. Without it the
app flashes a dashboard and then bounces to login (spec v13 Decision 7).
"""
from tests.admin.api_v1_contract import assert_error, assert_shape

from swingbot.admin import api_v1 as v1  # noqa: F401  (reload-safe import idiom)

_LOGIN = {"username": "admin", "password": "admin"}


# --- GET /api/v1/session -------------------------------------------------

def test_session_get_reports_unauthenticated_without_a_cookie(client):
    r = client.get("/api/v1/session")
    assert r.status_code == 200
    assert_shape(r.get_json(), {"authenticated": bool, "username": (str, type(None))})
    assert r.get_json() == {"authenticated": False, "username": None}


def test_session_get_is_not_auth_guarded(client):
    """It must answer 200-with-false rather than 401. It is the question
    'am I logged in', so refusing to answer it unless logged in is circular
    and would make the SPA's boot check impossible."""
    assert client.get("/api/v1/session").status_code == 200


def test_session_get_reports_authenticated_after_login(client):
    client.post("/api/v1/session", json=_LOGIN)
    body = client.get("/api/v1/session").get_json()
    assert body == {"authenticated": True, "username": "admin"}


# --- POST /api/v1/session ------------------------------------------------

def test_login_sets_the_session_and_returns_identity(client):
    r = client.post("/api/v1/session", json=_LOGIN)
    assert r.status_code == 200
    assert_shape(r.get_json(), {"authenticated": bool, "username": (str, type(None))})
    assert r.get_json() == {"authenticated": True, "username": "admin"}


def test_login_with_bad_password_is_401_json(client):
    r = client.post("/api/v1/session", json={"username": "admin", "password": "wrong"})
    assert_error(r, "auth", 401)


def test_login_failure_does_not_authenticate(client):
    client.post("/api/v1/session", json={"username": "admin", "password": "wrong"})
    assert client.get("/api/v1/session").get_json()["authenticated"] is False


def test_login_accepts_a_missing_body_without_crashing(client):
    assert_error(client.post("/api/v1/session"), "auth", 401)


def test_login_grants_access_to_the_jinja_ui_too(client):
    """One session mechanism, two front doors -- the SPA and the Jinja UI
    must not diverge into separate notions of 'logged in' while both exist."""
    client.post("/api/v1/session", json=_LOGIN)
    assert client.get("/").status_code == 200


def test_jinja_login_grants_access_to_the_v1_api(client):
    """The same property in the other direction."""
    client.post("/login", data=_LOGIN)
    assert client.get("/api/v1/session").get_json()["authenticated"] is True


# --- DELETE /api/v1/session ----------------------------------------------

def test_logout_clears_the_session(client):
    client.post("/api/v1/session", json=_LOGIN)
    r = client.delete("/api/v1/session")
    assert r.status_code == 200
    assert r.get_json() == {"authenticated": False, "username": None}
    assert client.get("/api/v1/session").get_json()["authenticated"] is False


def test_logout_when_not_logged_in_is_not_an_error(client):
    """Idempotent: the SPA calls it on a 401 to clear local state, and that
    path must not itself fail."""
    assert client.delete("/api/v1/session").status_code == 200


# --- GET /api/v1/health --------------------------------------------------

def test_health_requires_auth_and_returns_json_401(client):
    assert_error(client.get("/api/v1/health"), "auth", 401)


def test_health_ok_with_basic_auth(client, auth):
    r = client.get("/api/v1/health", headers=auth)
    assert r.status_code == 200
    assert_shape(r.get_json(), {"ok": bool, "versions": dict})
    assert r.get_json()["ok"] is True
    # get_versions() returns ui/bot/last_updated -- NOT VERSION.json verbatim
    # (which also has ui_updated/bot_updated). last_updated is VERSION.json's
    # own mtime and is None when the file is missing or unreadable.
    assert_shape(
        r.get_json()["versions"],
        {"ui": str, "bot": str, "last_updated": (str, type(None))},
        where="versions",
    )


def test_v1_and_legacy_401_bodies_deliberately_differ(client):
    """The two namespaces do NOT share an error shape, and that is intended.

    Legacy `/api/*` answers `{"error": "auth"}` -- a bare string -- and
    dashboard.js branches on it today. v1's contract is
    `{"error": {"code", "message"}}`. Reusing api.py's require_auth_json on
    v1 routes would have leaked the old shape into the new namespace; the
    contract assertions caught it, and this test stops it coming back while
    also pinning that the legacy shape is left untouched.
    """
    assert client.get("/api/health").get_json() == {"error": "auth"}
    assert client.get("/api/v1/health").get_json() == {
        "error": {"code": "auth", "message": "Authentication required."}
    }


def test_v1_401_does_not_send_a_basic_auth_challenge(client):
    """A WWW-Authenticate header would pop the browser's native Basic Auth
    dialog over the SPA, which is not the login UI."""
    assert "WWW-Authenticate" not in client.get("/api/v1/health").headers


def test_health_ok_with_session_cookie(client):
    """Basic Auth stays supported (spec v11 Decision 5) but the SPA uses the
    cookie, so both paths are pinned."""
    client.post("/api/v1/session", json=_LOGIN)
    assert client.get("/api/v1/health").status_code == 200


# --- NG19: behaviour carried over from test_login.py ----------------------

def test_a_session_stops_working_when_the_password_changes(client, admin_app):
    """Rotating ADMIN_PASSWORD must invalidate sessions already issued.

    Carried over from test_login.py's Jinja version during NG19's triage.
    The mechanism is `session["pw_hash"]`, checked by `_session_authenticated`
    -- which v1 shares rather than reimplements -- but "v1 inherits it" is an
    assumption about a security property, and rotating the password is the
    one thing an operator does *because* they believe it locks people out.
    A regression in the shared predicate would otherwise surface only in a
    test of the UI being deleted.
    """
    import swingbot.admin.app as admin_app_module

    client.post("/api/v1/session", json=_LOGIN)
    assert client.get("/api/v1/health").status_code == 200

    admin_app_module.ADMIN_PASSWORD = "rotated"
    try:
        assert_error(client.get("/api/v1/health"), "auth", 401)
    finally:
        admin_app_module.ADMIN_PASSWORD = "admin"
