"""Session-cookie login page (/login, /logout) -- coexists with the
existing Basic Auth check (see conftest.py's `auth` fixture) rather than
replacing it. See swingbot/admin/app.py's Auth section.

NG19 TRIAGE — **MIXED · DELETE at cutover, coverage migrated.** `GET /login`
is a recorded drop (the SPA renders its own login view), so the page-render
and `next`-param tests go with it -- including the open-redirect one, which
protects a parameter that ceases to exist.

Everything about the session itself is behavioural and now has a v1
successor in test_api_v1_session.py: login, wrong password, logout, Basic
Auth coexisting with the cookie, and -- added during this triage --
`test_a_session_stops_working_when_the_password_changes`. That last one was
the only assertion in this directory whose v1 equivalent was missing
entirely, and it is a security property, not a UI one."""


def test_login_page_renders_without_auth(client):
    r = client.get("/login")
    assert r.status_code == 200
    assert b"Sign in" in r.data


def test_dashboard_redirects_to_login_when_unauthenticated(client):
    r = client.get("/")
    assert r.status_code == 302
    assert "/login" in r.headers["Location"]


def test_login_with_correct_credentials_sets_session_and_redirects(client):
    r = client.post("/login", data={"username": "admin", "password": "admin"})
    assert r.status_code == 302
    assert r.headers["Location"] == "/"
    # Session cookie now authenticates subsequent requests with no auth header at all.
    r2 = client.get("/jinja/dashboard")
    assert r2.status_code == 200


def test_login_with_wrong_password_shows_error_and_no_session(client):
    r = client.post("/login", data={"username": "admin", "password": "wrong"})
    assert r.status_code == 401
    assert b"Invalid username or password" in r.data
    r2 = client.get("/")
    assert r2.status_code == 302
    assert "/login" in r2.headers["Location"]


def test_login_next_param_round_trips(client):
    r = client.get("/login?next=/settings")
    assert r.status_code == 200
    assert b'value="/settings"' in r.data
    r2 = client.post("/login", data={"username": "admin", "password": "admin", "next": "/settings"})
    assert r2.headers["Location"] == "/settings"


def test_login_rejects_open_redirect_next(client):
    r = client.post("/login", data={
        "username": "admin", "password": "admin", "next": "https://evil.example/",
    })
    assert r.headers["Location"] == "/"


def test_logout_clears_session(client):
    client.post("/login", data={"username": "admin", "password": "admin"})
    assert client.get("/jinja/dashboard").status_code == 200

    r = client.post("/logout")
    assert r.status_code == 302
    assert "/login" in r.headers["Location"]

    r2 = client.get("/")
    assert r2.status_code == 302
    assert "/login" in r2.headers["Location"]


def test_session_invalidated_when_password_changes(client, admin_app):
    client.post("/login", data={"username": "admin", "password": "admin"})
    assert client.get("/jinja/dashboard").status_code == 200

    import swingbot.admin.app as admin_app_module
    admin_app_module.ADMIN_PASSWORD = "rotated"
    try:
        r = client.get("/")
        assert r.status_code == 302
        assert "/login" in r.headers["Location"]
    finally:
        admin_app_module.ADMIN_PASSWORD = "admin"


def test_basic_auth_still_works_alongside_session_login(client, auth):
    """Existing Basic-Auth callers (scripts, this suite's own fixture) are
    unaffected by the new session check -- coexistence, not replacement."""
    # /dashboard rather than /: since NG53 the root's answer depends on the
    # ADMIN_UI flag and on whether a bundle is built, and neither is what
    # this test is about.
    r = client.get("/jinja/dashboard", headers=auth)
    assert r.status_code == 200


def test_basic_auth_failure_still_returns_401_challenge(client):
    import base64
    bad = base64.b64encode(b"admin:wrong").decode("ascii")
    r = client.get("/", headers={"Authorization": f"Basic {bad}"})
    assert r.status_code == 401
    assert "WWW-Authenticate" in r.headers
