"""v207: viewer login through POST /api/v1/session, the one principal
resolver, and the identical failure answer for every refused sign-in."""
import base64

import pytest
from tests.admin.api_v1_contract import assert_error

from swingbot.admin import api_v1 as v1  # noqa: F401  (reload-safe import idiom)
from swingbot.admin import login_limiter, principals
from swingbot.core.db.repositories.admin_users import admin_users_repo

VIEWER = {"username": "viewer1", "password": "viewer-password-1"}
FAIL_BODY = {"error": {"code": "auth", "message": "Invalid username or password."}}


def _app():
    import swingbot.admin.app as app_module    # the reloaded module, by attribute
    return app_module


def _make_viewer(name="viewer1", password="viewer-password-1", disabled=False):
    repo = admin_users_repo()
    row = repo.create_user(name, principals.hash_password(password))
    return repo.set_disabled(row["id"], True) if disabled else row


def _basic(username, password):
    token = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
    return {"Authorization": f"Basic {token}"}


# --- login_session_fields ------------------------------------------------------

def test_the_env_admin_wins_before_the_table_is_consulted(admin_app, monkeypatch):
    def boom(*_a):
        raise AssertionError("the .env admin must never reach admin_users")
    monkeypatch.setattr(principals, "authenticate_viewer", boom)
    app = _app()
    assert app.login_session_fields("admin", "admin") == {
        "admin_authed": True, "pw_hash": app._password_hash(), "role": "admin"}


def test_a_viewer_gets_viewer_session_fields(admin_app):
    row = _make_viewer()
    assert _app().login_session_fields("viewer1", "viewer-password-1") == {
        "role": "viewer", "user_id": row["id"], "credential_version": 1,
        "username": "viewer1"}


@pytest.mark.parametrize("username,password", [
    ("admin", "nope-nope-nope"), ("viewer1", "nope-nope-nope"),
    ("ghost", "viewer-password-1"), ("viewer2", "viewer-password-1")])
def test_wrong_unknown_and_disabled_get_no_fields(admin_app, username, password):
    _make_viewer()
    _make_viewer(name="viewer2", disabled=True)
    assert _app().login_session_fields(username, password) is None


def test_a_missing_table_refuses_viewers_and_keeps_the_admin(admin_app, admin_users_table_missing):
    app = _app()
    assert app.login_session_fields("viewer1", "viewer-password-1") is None
    assert app.login_session_fields("admin", "admin")["role"] == "admin"


# --- Basic stays admin-only (spec Decision 7) ---------------------------------

def test_viewer_credentials_over_basic_are_401_without_a_table_lookup(client, monkeypatch):
    _make_viewer()
    looked_up = []
    monkeypatch.setattr(principals, "authenticate_viewer",
                        lambda *a: looked_up.append(a))
    assert_error(client.get("/api/v1/health", headers=_basic(**VIEWER)), "auth", 401)
    assert looked_up == []


# --- the resolver --------------------------------------------------------------

def test_a_viewer_session_never_resolves_as_admin(admin_app):
    app = _app()
    row = _make_viewer()
    forged = {"role": "viewer", "user_id": row["id"], "credential_version": 1,
              "admin_authed": True, "pw_hash": app._password_hash()}
    assert app.principal_from_session(forged) == {
        "role": "viewer", "username": "viewer1", "user_id": row["id"]}


def test_a_stale_viewer_session_resolves_to_none(admin_app):
    row = _make_viewer()
    admin_users_repo().reset_password(row["id"], principals.hash_password("a-new-password"))
    assert _app().principal_from_session(
        {"role": "viewer", "user_id": row["id"], "credential_version": 1}) is None


@pytest.mark.parametrize("data", [{}, {"role": "operator"}, {"role": "admin"},
                                  {"admin_authed": True, "pw_hash": "stale"}])
def test_sessions_that_name_no_one_resolve_to_none(admin_app, data):
    assert _app().principal_from_session(data) is None


def test_the_admin_principal_with_and_without_a_role_key(admin_app):
    app = _app()
    admin = {"role": "admin", "username": "admin", "user_id": None}
    fields = {"admin_authed": True, "pw_hash": app._password_hash()}
    assert app.principal_from_session({**fields, "role": "admin"}) == admin
    assert app.principal_from_session(fields) == admin       # issued before v207


def test_resolve_principal_is_computed_once_per_request(admin_app, monkeypatch):
    app = _app()
    calls = []
    monkeypatch.setattr(app, "principal_from_session",
                        lambda data: calls.append(1) or {"role": "admin"})
    with admin_app.test_request_context("/api/v1/session"):
        app.resolve_principal()
        app.resolve_principal()
        assert app._session_authenticated() is True
        assert len(calls) == 1
        app.forget_principal()
        app.resolve_principal()
        assert len(calls) == 2


# --- login_limiter.attempt_login ----------------------------------------------

def test_attempt_login_returns_the_result_and_counts_failures(admin_app):
    with admin_app.test_request_context("/api/v1/session"):
        ok = login_limiter.attempt_login("u", "p", lambda u, p: {"who": u})
        assert ok.ok is True and ok.result == {"who": "u"} and ok.retry_after is None
        for _ in range(login_limiter.MAX_FAILURES):
            assert login_limiter.attempt_login("u", "p", lambda u, p: None).ok is False
        locked = login_limiter.attempt_login("u", "p", lambda u, p: {"who": u})
        assert locked.ok is False and locked.retry_after is not None


def test_attempt_login_ignores_an_empty_attempt(admin_app):
    called = []
    with admin_app.test_request_context("/api/v1/session"):
        out = login_limiter.attempt_login("", "", lambda u, p: called.append(1))
    assert out.ok is False and out.retry_after is None and called == []
    assert len(login_limiter.LIMITER) == 0


def test_attempt_keeps_its_bool_shape(admin_app):
    with admin_app.test_request_context("/api/v1/health"):
        assert login_limiter.attempt("a", "b", lambda u, p: True) == login_limiter.Attempt(True)
