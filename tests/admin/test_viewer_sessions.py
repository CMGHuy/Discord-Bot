"""v207: disable, password reset and delete end a viewer's live session on its
next request; disable -> re-enable leaves it dead (credential_version)."""
import pytest
from tests.admin.api_v1_contract import assert_error

from swingbot.admin import api_v1 as v1  # noqa: F401  (reload-safe import idiom)

READ = "/api/v1/system/preferences"  # allowlisted viewer GET with no fixture data


@pytest.fixture
def admin(admin_app, auth):
    """A SECOND client for the admin: the viewer's client carries a viewer
    cookie, and the session principal wins over a Basic header."""
    other = admin_app.test_client()

    def call(method, path, **kwargs):
        return other.open(f"/api/v1{path}", method=method, headers=auth, **kwargs)
    return call


def _signed_in(client) -> bool:
    return client.get("/api/v1/session").get_json()["authenticated"]


def _assert_dead(client):
    assert_error(client.get(READ), "auth", 401)
    assert _signed_in(client) is False


def test_the_viewer_session_works_before_anything_changes(viewer_client, admin):
    client, _row = viewer_client
    assert admin("GET", "/users").status_code == 200
    assert client.get(READ).status_code == 200
    assert _signed_in(client) is True


def test_disable_ends_the_session(viewer_client, admin):
    client, row = viewer_client
    assert admin("PATCH", f"/users/{row['id']}", json={"disabled": True}).status_code == 200
    _assert_dead(client)


def test_disable_then_enable_leaves_the_old_session_dead(viewer_client, admin):
    client, row = viewer_client
    admin("PATCH", f"/users/{row['id']}", json={"disabled": True})
    admin("PATCH", f"/users/{row['id']}", json={"disabled": False})
    _assert_dead(client)


def test_enabling_an_enabled_user_keeps_the_session(viewer_client, admin):
    client, row = viewer_client
    admin("PATCH", f"/users/{row['id']}", json={"disabled": False})
    assert client.get(READ).status_code == 200


def test_password_reset_ends_the_session(viewer_client, admin):
    client, row = viewer_client
    r = admin("POST", f"/users/{row['id']}/password", json={"password": "a-new-password-2"})
    assert r.status_code == 204
    _assert_dead(client)


def test_after_a_reset_the_new_password_signs_in(viewer_client, admin):
    client, row = viewer_client
    admin("POST", f"/users/{row['id']}/password", json={"password": "a-new-password-2"})
    r = client.post("/api/v1/session",
                    json={"username": "viewer1", "password": "a-new-password-2"})
    assert r.status_code == 200
    assert r.get_json()["role"] == "viewer"
    assert client.get(READ).status_code == 200


def test_delete_ends_the_session(viewer_client, admin):
    client, row = viewer_client
    assert admin("DELETE", f"/users/{row['id']}").status_code == 204
    _assert_dead(client)
