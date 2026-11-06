"""v207: principals -- password hashing, username/password rules, and the
viewer lookups the login and the per-request session check go through."""
import ast
import pathlib

import pytest

from swingbot.admin import principals
from swingbot.core.db.repositories.admin_users import admin_users_repo

SOURCE = pathlib.Path(principals.__file__)


def _viewer(name="viewer1", password="viewer-password-1", **changes):
    repo = admin_users_repo()
    row = repo.create_user(name, principals.hash_password(password))
    if changes.get("disabled"):
        row = repo.set_disabled(row["id"], True)
    return row


# --- hashing -----------------------------------------------------------------

def test_hash_and_verify_round_trip():
    stored = principals.hash_password("correct horse battery")
    assert stored.startswith("pbkdf2:sha256:1$")      # the suite's fast method
    assert principals.verify_password(stored, "correct horse battery") is True
    assert principals.verify_password(stored, "wrong horse battery") is False


def test_production_default_is_scrypt():
    """Read from the source: the autouse fixture has swapped the live value."""
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    values = [node.value.value for node in tree.body
              if isinstance(node, ast.Assign)
              and any(getattr(t, "id", None) == "HASH_METHOD" for t in node.targets)]
    assert values == ["scrypt"]


def test_a_missing_hash_still_runs_one_check_and_fails(monkeypatch):
    calls = []
    monkeypatch.setattr(principals, "check_password_hash",
                        lambda h, p: calls.append(h) or True)
    assert principals.verify_password(None, "anything") is False
    assert len(calls) == 1 and calls[0].startswith("pbkdf2:sha256:1$")


def test_the_dummy_hash_is_made_once_per_method(monkeypatch):
    monkeypatch.setattr(principals, "_DUMMY_HASHES", {})
    made = []
    real = principals.generate_password_hash
    monkeypatch.setattr(principals, "generate_password_hash",
                        lambda pw, method: made.append(method) or real(pw, method=method))
    principals.verify_password(None, "a")
    principals.verify_password(None, "b")
    monkeypatch.setattr(principals, "HASH_METHOD", "pbkdf2:sha256:2")
    principals.verify_password(None, "c")
    assert made == ["pbkdf2:sha256:1", "pbkdf2:sha256:2"]


# --- validation --------------------------------------------------------------

@pytest.mark.parametrize("name", ["abc", "viewer.one_2-x", "A" * 64, "Bob.Smith"])
def test_valid_usernames(name):
    assert principals.validate_username(name) is None


@pytest.mark.parametrize("name", ["ab", "a" * 65, "has space", "émile", "abc\n",
                                  "semi;colon", "", None, 123])
def test_invalid_usernames_name_the_field(name):
    message = principals.validate_username(name)
    assert message is not None and message.startswith("username ")


@pytest.mark.parametrize("password,ok", [("x" * 11, False), ("x" * 12, True),
                                         ("", False), (None, False), (123456789012, False)])
def test_password_minimum_is_twelve(password, ok):
    message = principals.validate_password(password)
    assert (message is None) is ok
    if not ok:
        assert message.startswith("password ")


# --- authenticate_viewer -----------------------------------------------------

def test_a_viewer_authenticates_and_last_login_is_touched():
    made = _viewer()
    row = principals.authenticate_viewer("viewer1", "viewer-password-1")
    assert row is not None and row["id"] == made["id"]
    assert admin_users_repo().get_by_id(made["id"])["last_login_at"] is not None


def test_the_username_matches_case_insensitively():
    _viewer(name="Viewer1")
    assert principals.authenticate_viewer("VIEWER1", "viewer-password-1") is not None


@pytest.mark.parametrize("username,password", [
    ("viewer1", "wrong-password-xx"),     # wrong password
    ("nobody", "viewer-password-1"),      # unknown user
    ("", "viewer-password-1"),            # empty name
])
def test_failures_answer_none_after_exactly_one_hash_check(monkeypatch, username, password):
    _viewer()
    checks = []
    real = principals.check_password_hash
    monkeypatch.setattr(principals, "check_password_hash",
                        lambda h, p: checks.append(1) or real(h, p))
    assert principals.authenticate_viewer(username, password) is None
    assert len(checks) == 1


def test_a_disabled_viewer_is_refused_even_with_the_right_password():
    row = _viewer(disabled=True)
    assert principals.authenticate_viewer("viewer1", "viewer-password-1") is None
    assert admin_users_repo().get_by_id(row["id"])["last_login_at"] is None


def test_a_missing_table_is_no_such_user(admin_users_table_missing):
    assert principals.authenticate_viewer("viewer1", "viewer-password-1") is None


# --- viewer_principal --------------------------------------------------------

def test_a_live_session_resolves_to_the_viewer_principal():
    row = _viewer()
    assert principals.viewer_principal(row["id"], 1) == {
        "role": "viewer", "username": "viewer1", "user_id": row["id"]}


def test_a_bumped_version_disabled_or_deleted_row_ends_the_session():
    repo = admin_users_repo()
    row = _viewer()
    repo.reset_password(row["id"], principals.hash_password("another-password"))
    assert principals.viewer_principal(row["id"], 1) is None
    other = _viewer(name="viewer2")
    repo.set_disabled(other["id"], True)
    repo.set_disabled(other["id"], False)                 # re-enable: version stays 2
    assert principals.viewer_principal(other["id"], 1) is None
    assert principals.viewer_principal(other["id"], 2) is not None
    repo.delete_user(other["id"])
    assert principals.viewer_principal(other["id"], 2) is None


@pytest.mark.parametrize("user_id,version", [(None, 1), ("1", 1), (1, None), (True, 1), (1, True)])
def test_malformed_session_fields_are_no_principal(user_id, version):
    assert principals.viewer_principal(user_id, version) is None


def test_a_missing_table_resolves_no_principal(admin_users_table_missing):
    assert principals.viewer_principal(1, 1) is None


# --- module boundary ---------------------------------------------------------

def test_principals_never_imports_the_admin_app():
    """app.py imports principals; the reverse would be an import cycle, and the
    admin conftest reloads app.py per test."""
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.add((node.module or "") + ":" + ",".join(a.name for a in node.names))
        elif isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
    assert not any(name.startswith("swingbot.admin") or name.startswith(":")
                   for name in imported), imported
