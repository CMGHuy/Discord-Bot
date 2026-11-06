"""v207: /api/v1/users -- viewer accounts, managed by the .env admin only."""
import logging

import pytest
from tests.admin.api_v1_contract import NULLABLE_STR, assert_error, assert_shape

from swingbot.admin import api_v1 as v1  # noqa: F401  (reload-safe import idiom)
from swingbot.admin import principals
from swingbot.core.db.repositories.admin_users import admin_users_repo

USER_SHAPE = {"id": int, "username": str, "role": str, "disabled": bool,
              "created_at": str, "last_login_at": NULLABLE_STR}
NEW = {"username": "viewer1", "password": "viewer-password-1"}


@pytest.fixture
def api(client, auth):
    """Admin over Basic: no session cookie, so the access hook steps aside."""
    def call(method, path, **kwargs):
        return client.open(f"/api/v1{path}", method=method, headers=auth, **kwargs)
    return call


def _create(api, **overrides):
    return api("POST", "/users", json={**NEW, **overrides})


def test_the_list_starts_empty(api):
    r = api("GET", "/users")
    assert r.status_code == 200
    assert r.get_json() == {"users": []}


def test_create_returns_the_user_and_never_the_hash(api):
    r = _create(api)
    assert r.status_code == 201
    body = r.get_json()
    assert_shape(body, USER_SHAPE)
    assert body["username"] == "viewer1" and body["role"] == "viewer"
    assert body["disabled"] is False and body["last_login_at"] is None


def test_the_list_never_carries_a_hash(api):
    _create(api)
    r = api("GET", "/users")
    stored = admin_users_repo().get_by_username("viewer1")["password_hash"]
    text = r.get_data(as_text=True)
    assert "password_hash" not in text and stored not in text
    assert "credential_version" not in text
    [user] = r.get_json()["users"]
    assert_shape(user, USER_SHAPE)


def test_a_duplicate_is_a_conflict_whatever_its_case(api):
    _create(api)
    assert_error(_create(api, username="Viewer1"), "conflict", 409)


@pytest.mark.parametrize("name", ["admin", "ADMIN", "Admin"])
def test_the_env_admins_name_cannot_be_taken(api, name):
    assert_error(_create(api, username=name), "conflict", 409)
    assert admin_users_repo().list_users() == []


@pytest.mark.parametrize("body,field", [
    ({"username": "viewer1", "password": "x" * 11}, "password"),
    ({"username": "a b", "password": "viewer-password-1"}, "username"),
    ({"username": "ab", "password": "viewer-password-1"}, "username"),
    ({"password": "viewer-password-1"}, "username"),
    ({"username": "viewer1"}, "password"),
    ({}, "username"),
])
def test_bad_input_is_invalid_and_names_the_field(api, body, field):
    r = api("POST", "/users", json=body)
    assert_error(r, "invalid", 400)
    assert r.get_json()["error"]["message"].startswith(field)


def test_a_non_object_body_is_invalid(api):
    assert_error(api("POST", "/users", json=["viewer1"]), "invalid", 400)


def test_disable_bumps_the_credential_version_and_enable_does_not(api):
    user = _create(api).get_json()
    r = api("PATCH", f"/users/{user['id']}", json={"disabled": True})
    assert r.status_code == 200
    assert r.get_json()["disabled"] is True
    assert admin_users_repo().get_by_id(user["id"])["credential_version"] == 2
    r = api("PATCH", f"/users/{user['id']}", json={"disabled": False})
    assert r.get_json()["disabled"] is False
    assert admin_users_repo().get_by_id(user["id"])["credential_version"] == 2


@pytest.mark.parametrize("value", ["yes", 1, None])
def test_disabled_must_be_a_bool(api, value):
    user = _create(api).get_json()
    assert_error(api("PATCH", f"/users/{user['id']}", json={"disabled": value}), "invalid", 400)


def test_reset_password_is_204_and_the_new_password_works(api):
    user = _create(api).get_json()
    r = api("POST", f"/users/{user['id']}/password", json={"password": "a-new-password-2"})
    assert r.status_code == 204
    assert r.get_data() == b""
    assert admin_users_repo().get_by_id(user["id"])["credential_version"] == 2
    assert principals.authenticate_viewer("viewer1", "a-new-password-2") is not None
    assert principals.authenticate_viewer("viewer1", "viewer-password-1") is None


def test_reset_with_a_short_password_is_invalid(api):
    user = _create(api).get_json()
    r = api("POST", f"/users/{user['id']}/password", json={"password": "short"})
    assert_error(r, "invalid", 400)
    assert r.get_json()["error"]["message"].startswith("password")


def test_delete_is_204_then_404(api):
    user = _create(api).get_json()
    r = api("DELETE", f"/users/{user['id']}")
    assert r.status_code == 204
    assert api("GET", "/users").get_json() == {"users": []}
    assert_error(api("DELETE", f"/users/{user['id']}"), "not_found", 404)


@pytest.mark.parametrize("method,path,body", [
    ("PATCH", "/users/999", {"disabled": True}),
    ("POST", "/users/999/password", {"password": "a-new-password-2"}),
    ("DELETE", "/users/999", None),
])
def test_an_unknown_id_is_404(api, method, path, body):
    assert_error(api(method, path, json=body), "not_found", 404)


def test_mutations_log_the_action_and_nothing_secret(api, caplog):
    caplog.set_level(logging.INFO, logger="swingbot.admin.api_v1.users")
    user = _create(api).get_json()
    api("PATCH", f"/users/{user['id']}", json={"disabled": True})
    api("PATCH", f"/users/{user['id']}", json={"disabled": False})
    api("POST", f"/users/{user['id']}/password", json={"password": "a-new-password-2"})
    api("DELETE", f"/users/{user['id']}")
    lines = [rec.getMessage() for rec in caplog.records if rec.name.endswith("users")]
    assert lines == ["users: create viewer1 by admin", "users: disable viewer1 by admin",
                     "users: enable viewer1 by admin", "users: reset-password viewer1 by admin",
                     "users: delete viewer1 by admin"]
    assert "viewer-password-1" not in caplog.text and "a-new-password-2" not in caplog.text


def test_without_a_principal_every_route_is_401(client):
    assert_error(client.get("/api/v1/users"), "auth", 401)
    assert_error(client.post("/api/v1/users", json=NEW), "auth", 401)


@pytest.mark.parametrize("method,suffix,body", [
    ("GET", "", None), ("POST", "", NEW), ("PATCH", "/{id}", {"disabled": True}),
    ("POST", "/{id}/password", {"password": "a-new-password-2"}), ("DELETE", "/{id}", None),
])
def test_a_viewer_is_refused_every_users_route(viewer_client, method, suffix, body):
    client, row = viewer_client
    path = "/api/v1/users" + suffix.format(id=row["id"])
    assert_error(client.open(path, method=method, json=body), "forbidden", 403)
    assert admin_users_repo().get_by_id(row["id"])["disabled"] is False
