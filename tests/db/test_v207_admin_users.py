"""v207: revision v207_001 -- admin_users, the viewer accounts table.

The `.env` admin is never stored; every row is a viewer (CHECK role IN
('viewer')). Usernames are unique case-insensitively through a functional
index on lower(username)."""
import pathlib

import pytest
import sqlalchemy as sa
from alembic.command import downgrade, upgrade
from alembic.config import Config
from alembic.script import ScriptDirectory

from swingbot.core.db import events, schema

REPO = pathlib.Path(__file__).resolve().parents[2]
PROMOTED = ("username", "password_hash", "role", "disabled",
            "credential_version", "created_at", "last_login_at")


def test_registered_with_reasons_contract_and_no_sse():
    table = schema.METADATA.tables["admin_users"]
    assert schema.promoted_for("admin_users") == PROMOTED
    assert set(schema.PROMOTION_REASONS["admin_users"]) == set(PROMOTED)
    assert schema.contract_violations(table) == []
    assert [c.name for c in table.primary_key.columns] == ["id"]
    assert table.c.last_login_at.nullable is True
    assert all(table.c[name].nullable is False for name in PROMOTED if name != "last_login_at")
    assert "admin_users" not in events.TABLE_CHANNELS


def test_column_types_and_defaults():
    t = schema.admin_users
    assert isinstance(t.c.id.type, sa.BigInteger)
    assert isinstance(t.c.disabled.type, sa.Boolean)
    assert isinstance(t.c.credential_version.type, sa.Integer)
    assert t.c.created_at.type.timezone is True and t.c.last_login_at.type.timezone is True
    assert "viewer" in str(t.c.role.server_default.arg)
    assert "false" in str(t.c.disabled.server_default.arg).lower()
    assert str(t.c.credential_version.server_default.arg) == "1"


def test_lower_username_index_and_role_check_are_declared():
    t = schema.admin_users
    index = {i.name: i for i in t.indexes}["admin_users_username_lower_uq"]
    assert index.unique is True
    assert "lower" in str(index.expressions[0]).lower()
    checks = {c.name: str(c.sqltext) for c in t.constraints
              if isinstance(c, sa.CheckConstraint)}
    assert checks == {"admin_users_role_ck": "role IN ('viewer')"}


def _insert(conn, username, **extra):
    conn.execute(sa.insert(schema.admin_users).values(
        username=username, password_hash="x", **extra))


def test_usernames_are_unique_case_insensitively(db_conn):
    _insert(db_conn, "Alice")
    with pytest.raises(sa.exc.IntegrityError):
        with db_conn.begin_nested():
            _insert(db_conn, "alice")


def test_only_the_viewer_role_is_allowed(db_conn):
    with pytest.raises(sa.exc.IntegrityError):
        with db_conn.begin_nested():
            _insert(db_conn, "bob", role="admin")


def test_server_defaults_fill_a_bare_row(db_conn):
    _insert(db_conn, "carol")
    row = db_conn.execute(sa.select(schema.admin_users)).one()._mapping
    assert row["role"] == "viewer" and row["disabled"] is False
    assert row["credential_version"] == 1 and row["last_login_at"] is None
    assert row["created_at"] is not None and isinstance(row["id"], int)


def test_v207_001_sits_on_the_single_prior_head():
    scripts = ScriptDirectory.from_config(Config(str(REPO / "alembic.ini")))
    revision = scripts.get_revision("v207_001")
    assert scripts.get_revision(revision.down_revision) is not None
    heads = scripts.get_heads()
    assert len(heads) == 1      # later revisions may stack on v207_001; never branch
    assert "v207_001" in {r.revision for r in scripts.iterate_revisions(heads[0], "base")}


def _index_defs(connection) -> list[str]:
    return [r[0] for r in connection.execute(sa.text(
        "select indexdef from pg_indexes where tablename = 'admin_users'"))]


def _check_names(connection) -> set[str]:
    return {r[0] for r in connection.execute(sa.text(
        "select conname from pg_constraint "
        "where conrelid = 'admin_users'::regclass and contype = 'c'"))}


def test_downgrade_drops_it_and_upgrade_restores_it(db_engine_empty):
    cfg = Config(str(REPO / "alembic.ini"))
    with db_engine_empty.begin() as connection:
        cfg.attributes["connection"] = connection
        upgrade(cfg, "head")
        assert "admin_users" in sa.inspect(connection).get_table_names()
        assert any("admin_users_username_lower_uq" in d and "lower(username)" in d
                   for d in _index_defs(connection))
        assert _check_names(connection) == {"admin_users_role_ck"}
        downgrade(cfg, ScriptDirectory.from_config(cfg).get_revision("v207_001").down_revision)
        remaining = set(sa.inspect(connection).get_table_names())
        assert "admin_users" not in remaining and "fx_daily_rates" in remaining
        upgrade(cfg, "head")    # leave the shared empty-schema engine at head
        assert "admin_users" in sa.inspect(connection).get_table_names()
