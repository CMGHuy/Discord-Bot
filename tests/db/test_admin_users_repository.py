"""v207: AdminUsersRepository -- viewer rows, case-insensitive lookup, the
credential_version bumps that end live sessions, and the pre-migration window."""
import logging

import pytest
import sqlalchemy as sa

from swingbot.core.db import schema
from swingbot.core.db.repositories import admin_users as au

ROW_KEYS = {"id", "username", "password_hash", "role", "disabled",
            "credential_version", "created_at", "last_login_at"}


@pytest.fixture
def repo():
    return au.AdminUsersRepository()


def test_create_returns_the_full_row(repo, db_conn):
    row = repo.create_user("Viewer.One", "hash-1", conn=db_conn)
    assert set(row) >= ROW_KEYS
    assert isinstance(row["id"], int) and row["username"] == "Viewer.One"
    assert row["role"] == "viewer" and row["disabled"] is False
    assert row["credential_version"] == 1 and row["last_login_at"] is None
    assert row["password_hash"] == "hash-1" and row["created_at"] is not None


def test_duplicate_name_in_any_case_raises_username_taken(repo):
    repo.create_user("alice", "h")
    with pytest.raises(au.UsernameTaken):
        repo.create_user("ALICE", "h")


def test_get_by_username_is_case_insensitive(repo, db_conn):
    made = repo.create_user("Bob", "h", conn=db_conn)
    assert repo.get_by_username("bob", conn=db_conn)["id"] == made["id"]
    assert repo.get_by_username("BOB", conn=db_conn)["id"] == made["id"]
    assert repo.get_by_username("nobody", conn=db_conn) is None


def test_get_by_id_and_list_in_id_order(repo, db_conn):
    first = repo.create_user("u1", "h", conn=db_conn)
    second = repo.create_user("u2", "h", conn=db_conn)
    assert repo.get_by_id(second["id"], conn=db_conn)["username"] == "u2"
    assert repo.get_by_id(999_999, conn=db_conn) is None
    assert [r["id"] for r in repo.list_users(conn=db_conn)] == [first["id"], second["id"]]


def test_disable_bumps_the_version_and_enable_does_not(repo, db_conn):
    row = repo.create_user("carol", "h", conn=db_conn)
    off = repo.set_disabled(row["id"], True, conn=db_conn)
    assert off["disabled"] is True and off["credential_version"] == 2
    on = repo.set_disabled(row["id"], False, conn=db_conn)
    assert on["disabled"] is False and on["credential_version"] == 2
    assert repo.set_disabled(999_999, True, conn=db_conn) is None


def test_reset_password_replaces_the_hash_and_bumps(repo, db_conn):
    row = repo.create_user("dave", "old", conn=db_conn)
    out = repo.reset_password(row["id"], "new", conn=db_conn)
    assert out["password_hash"] == "new" and out["credential_version"] == 2
    assert repo.reset_password(999_999, "x", conn=db_conn) is None


def test_delete_reports_whether_a_row_went(repo, db_conn):
    row = repo.create_user("erin", "h", conn=db_conn)
    assert repo.delete_user(row["id"], conn=db_conn) is True
    assert repo.delete_user(row["id"], conn=db_conn) is False
    assert repo.get_by_id(row["id"], conn=db_conn) is None


def test_touch_last_login_sets_the_time(repo, db_conn):
    row = repo.create_user("fay", "h", conn=db_conn)
    repo.touch_last_login(row["id"], conn=db_conn)
    assert repo.get_by_id(row["id"], conn=db_conn)["last_login_at"] is not None


def test_the_accessor_is_a_singleton():
    assert au.admin_users_repo() is au.admin_users_repo()
    assert isinstance(au.admin_users_repo(), au.AdminUsersRepository)


# --- before alembic upgrade head has created the table ----------------------

def _ghost_repo() -> au.AdminUsersRepository:
    """Same columns, a table name the database has never seen: a real
    UndefinedTable from Postgres, without dropping the shared test table."""
    ghost = sa.Table("admin_users_not_migrated", sa.MetaData(),
                     *[sa.Column(c.name, c.type, primary_key=c.primary_key)
                       for c in schema.admin_users.columns])
    repo = au.AdminUsersRepository()
    repo.table, repo.key_col = ghost, ghost.c.id
    return repo


def test_a_missing_table_reads_as_no_such_user_and_warns_once(caplog, monkeypatch):
    monkeypatch.setattr(au, "_warned_missing", False)
    repo = _ghost_repo()
    with caplog.at_level(logging.WARNING, logger=au.__name__):
        assert repo.get_by_username("viewer1") is None
        assert repo.get_by_id(1) is None
        assert repo.list_users() == []
        repo.touch_last_login(1)
    warnings = [r for r in caplog.records if "admin_users table missing" in r.getMessage()]
    assert len(warnings) == 1


def test_a_missing_table_still_raises_on_writes():
    with pytest.raises(sa.exc.ProgrammingError):
        _ghost_repo().create_user("viewer1", "h")


def test_other_programming_errors_are_not_swallowed(repo, monkeypatch):
    def broken(*_a, **_kw):
        raise sa.exc.ProgrammingError("select", {}, Exception("syntax error"))
    monkeypatch.setattr(repo, "_select_one", broken)
    with pytest.raises(sa.exc.ProgrammingError):
        repo.get_by_username("x")
