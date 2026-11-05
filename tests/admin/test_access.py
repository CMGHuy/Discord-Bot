"""v207: check_access (pure, data-driven) and the api_v1 before_request hook
that enforces it on every v1 request."""
import pytest
from tests.admin.api_v1_contract import assert_error

from swingbot.admin import access
from swingbot.admin import api_v1 as v1  # noqa: F401  (reload-safe import idiom)

VIEWER = {"role": "viewer", "username": "viewer1", "user_id": 1}
ADMIN = {"role": "admin", "username": "admin", "user_id": None}
FORBIDDEN_BODY = {"error": {"code": "forbidden", "message": "Read-only account."}}


@pytest.mark.parametrize("method,path,allowed", [
    ("GET", "/api/v1/dashboard", True),
    ("HEAD", "/api/v1/dashboard", True),
    ("get", "/api/v1/dashboard", True),
    ("POST", "/api/v1/trades/clear-open", False),
    ("PUT", "/api/v1/trades/t1/note", False),
    ("DELETE", "/api/v1/trades/t1", False),
    ("OPTIONS", "/api/v1/dashboard", False),
    ("GET", "/api/v1/system", False),
    ("GET", "/api/v1/system/settings", False),
    ("GET", "/api/v1/system/scan", True),
    ("GET", "/api/v1/system/preferences", True),
    ("PUT", "/api/v1/system/preferences", False),
    ("GET", "/api/v1/system/scan/trigger", False),
    ("GET", "/api/v1/jobs", False),
    ("GET", "/api/v1/jobs/j1/result", False),
    ("GET", "/api/v1/users", False),
    ("GET", "/api/v1/users/3", False),
    ("GET", "/api/v1/analytics/tuning", False),
    ("GET", "/api/v1/analytics/tuning/proposals", False),
    ("GET", "/api/v1/analytics/performance", True),
    ("GET", "/api/v1/versions", False),
    ("GET", "/api/v1/versionsx", True),
    ("GET", "/api/v1/systematic", True),
    ("GET", "/api/v1/not-yet-written", True),
    ("POST", "/api/v1/not-yet-written", False),
    ("POST", "/api/v1/session", True),
    ("DELETE", "/api/v1/session", True),
])
def test_viewer_rules(method, path, allowed):
    assert access.check_access(VIEWER, method, path) is allowed


@pytest.mark.parametrize("method,path", [
    ("POST", "/api/v1/system/bot/restart"), ("GET", "/api/v1/users"),
    ("DELETE", "/api/v1/trades/t1"), ("PUT", "/api/v1/system/preferences"),
])
def test_admin_and_no_principal_are_always_let_through(method, path):
    assert access.check_access(ADMIN, method, path) is True
    assert access.check_access(None, method, path) is True


@pytest.mark.parametrize("principal", [{"role": "operator"}, {}, {"role": None}])
def test_an_unknown_role_is_denied_even_a_read(principal):
    assert access.check_access(principal, "GET", "/api/v1/dashboard") is False


def test_prefixes_match_on_segment_boundaries_only():
    assert access.is_admin_only("/api/v1/jobs")
    assert access.is_admin_only("/api/v1/jobs/tune/defaults")
    assert not access.is_admin_only("/api/v1/jobsite")


# --- the hook, through real requests -----------------------------------------

def test_the_hook_is_installed_on_the_blueprint(admin_app):
    from swingbot.admin.api_v1 import access_hook

    assert access_hook.enforce_access in admin_app.before_request_funcs["api_v1"]


def test_a_viewer_write_is_refused_before_the_handler_runs(viewer_client, monkeypatch):
    from swingbot.core.marketdata import watchlist

    client, _row = viewer_client
    calls = []
    monkeypatch.setattr(watchlist, "add_ticker", lambda ticker: calls.append(ticker))
    r = client.post("/api/v1/watchlist/tickers", json={"tickers": ["MSFT"]})
    assert_error(r, "forbidden", 403)
    assert r.get_json() == FORBIDDEN_BODY
    assert calls == []


@pytest.mark.parametrize("method,path", [
    ("GET", "/api/v1/system/settings"), ("HEAD", "/api/v1/system/settings"),
    ("PUT", "/api/v1/system/preferences"), ("GET", "/api/v1/versions"),
])
def test_a_viewer_is_refused_admin_paths_and_writes(viewer_client, method, path):
    client, _row = viewer_client
    r = client.open(path, method=method, json={} if method == "PUT" else None)
    assert r.status_code == 403


def test_a_viewer_reads_the_shell_allowlist(viewer_client):
    client, _row = viewer_client
    assert client.get("/api/v1/system/preferences").status_code == 200


def test_the_admin_session_is_not_filtered(client, monkeypatch):
    monkeypatch.setattr("swingbot.core.marketdata.backtest_cache.ensure_cached_background",
                        lambda ticker: None)
    client.post("/api/v1/session", json={"username": "admin", "password": "admin"})
    r = client.post("/api/v1/watchlist/tickers", json={"tickers": ["MSFT"]})
    assert r.status_code == 200, r.get_json()


def test_no_principal_still_gets_the_v1_401(client):
    assert_error(client.get("/api/v1/dashboard"), "auth", 401)


def test_basic_admin_reaches_admin_paths(admin_app, auth):
    r = admin_app.test_client().get("/api/v1/system/settings", headers=auth)
    assert r.status_code == 200


def test_the_hook_denies_a_route_it_has_never_seen(admin_app, monkeypatch):
    """Default-deny: the hook reads the method and path, not a decorator, so a
    route added later without @require_auth is still closed to viewer writes."""
    from swingbot.admin import app as admin_module
    from swingbot.admin.api_v1 import access_hook

    monkeypatch.setattr(admin_module, "resolve_principal", lambda: VIEWER)
    with admin_app.test_request_context("/api/v1/not-yet-written", method="POST"):
        response, status = access_hook.enforce_access()
    assert status == 403
    assert response.get_json() == FORBIDDEN_BODY
