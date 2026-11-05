# v207 part 1 — `admin_users` table, repository, principals, login and `/session` role

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [v207 — Viewer accounts](../specs/2026-11-05-v207-viewer-accounts-design.md)
**Index:** [`2026-11-05-v207-viewer-accounts_0-index.md`](2026-11-05-v207-viewer-accounts_0-index.md) — Goal, Architecture, `## Global Constraints`, `## Parallelisation` and the task ledger live there and bind every task below.

Tasks V207-1..V207-4 (index groups A and B, strictly sequential). V207-4 passed the 20 KB cap and was split; its second half, V207-4b (`/api/v1/session` + `viewer_client`), is in [`_1b-session.md`](2026-11-05-v207-viewer-accounts_1b-session.md): this file would otherwise pass the 1500-line cap. `<wt>` is the implementation worktree, `E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-11-05-v207-viewer-accounts`; every command runs with that path, never in the main tree. Python tests run narrow (`cd "<wt>" && python scripts/dev/testrun.py file <test>`); no task runs the full suite. Every task here reaches the local Postgres: run `/replicate-prod-db` once before the first test run of the session (shared `swing-db` container, port 56789).

**Two facts the ledger rests on, checked against the code:**

- `id` is a reserved infrastructure key (`swingbot/core/db/codec.py:RESERVED_KEYS`): it cannot be promoted (`schema.register` raises) and `merge_doc` drops it from every record. So `admin_users` promotes the seven other columns, and `AdminUsersRepository` overrides `_record` to put `id` (and an explicit `last_login_at: None`) back into its row dicts, which is the row shape the ledger fixes.
- `tests/db/test_unknown_field_round_trip.py:test_every_table_is_covered_or_excused` fails for any table in neither `CASES` nor `NOT_REPOSITORY_BACKED`. V207-1 adds `admin_users` to `NOT_REPOSITORY_BACKED` ("repository arrives in V207-2"); V207-2 moves it to `CASES`.

# Phase A — data

### Task V207-1: `admin_users` table + Alembic `v207_001`

**Model:** opus — schema migration on the production database: a functional unique index and a CHECK constraint with no precedent in this repo, and the revision must chain onto the live head.

**Files:**
- Modify: `swingbot/core/db/schema.py` (new table after `fx_daily_rates` at :323-333; new `PROMOTION_REASONS["admin_users"]` entry after the `fx_daily_rates` one at :557)
- Create: `swingbot/core/db/migrations/versions/v207_001_admin_users.py`
- Create: `tests/db/test_v207_admin_users.py`
- Modify: `tests/db/test_unknown_field_round_trip.py` (`NOT_REPOSITORY_BACKED` gains `admin_users` until V207-2)

**Interfaces:**
- Consumes: `schema.register`, `schema.standard_columns`, `schema.METADATA`, `schema.PROMOTION_REASONS` (all exist).
- Produces: `schema.admin_users` (`sa.Table`): `id` BigInteger PK (bigserial), `username` Text NOT NULL, `password_hash` Text NOT NULL, `role` Text NOT NULL default `'viewer'`, `disabled` Boolean NOT NULL default false, `credential_version` Integer NOT NULL default 1, `created_at` TIMESTAMPTZ NOT NULL default `now()`, `last_login_at` TIMESTAMPTZ NULL, plus `doc` / `updated_at`. Promoted (in this order): `("username", "password_hash", "role", "disabled", "credential_version", "created_at", "last_login_at")`. Unique index `admin_users_username_lower_uq` on `lower(username)`; CHECK `admin_users_role_ck` = `role IN ('viewer')`. Alembic revision `v207_001`. Not in `events.TABLE_CHANNELS` (no SSE for user rows).

- [ ] **Step 1: Confirm the head the revision sits on**

Run: `cd "<wt>" && python -m alembic heads`
Expected: `v205_001 (head)`. If it prints another single head, use that id as `down_revision` below; two heads is a stop-and-ask.

- [ ] **Step 2: Write the failing tests**

Create `tests/db/test_v207_admin_users.py`:

```python
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
```

- [ ] **Step 3: Run them to see them fail**

Run: `cd "<wt>" && python scripts/dev/testrun.py file tests/db/test_v207_admin_users.py`
Expected: FAIL — `KeyError: 'admin_users'` / `AttributeError: module 'swingbot.core.db.schema' has no attribute 'admin_users'`, and `get_revision("v207_001")` failing.

- [ ] **Step 4: Declare the table in `schema.py`**

Insert directly after the `fx_daily_rates = register(...)` block (ends :333):

```python
# v207: viewer accounts. The `.env` admin is never stored here; every row is a
# read-only viewer. `id` is the surrogate key (reserved, so not promoted).
admin_users = register(sa.Table("admin_users", METADATA,
    sa.Column("id", sa.BigInteger, primary_key=True),
    sa.Column("username", sa.Text, nullable=False),
    sa.Column("password_hash", sa.Text, nullable=False),
    sa.Column("role", sa.Text, nullable=False, server_default=sa.text("'viewer'")),
    sa.Column("disabled", sa.Boolean, nullable=False, server_default=sa.false()),
    sa.Column("credential_version", sa.Integer, nullable=False, server_default=sa.text("1")),
    sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False,
              server_default=sa.func.now()),
    sa.Column("last_login_at", sa.TIMESTAMP(timezone=True)),
    *standard_columns(),
    sa.CheckConstraint("role IN ('viewer')", name="admin_users_role_ck")),
    ("username", "password_hash", "role", "disabled", "credential_version",
     "created_at", "last_login_at"))
sa.Index("admin_users_username_lower_uq", sa.func.lower(admin_users.c.username), unique=True)
```

Insert directly after the `"fx_daily_rates": {...},` entry of `PROMOTION_REASONS` (each reason one line, at most 100 chars — `test_schema_contract.py` enforces it):

```python
    "admin_users": {
        "username": "admin_users_username_lower_uq: one viewer per name, case-insensitive",
        "password_hash": "NOT NULL werkzeug hash the login compares against",
        "role": "admin_users_role_ck: only 'viewer' today; a column so a role needs no data move",
        "disabled": "NOT NULL flag the per-request principal check reads",
        "credential_version": "NOT NULL; a session is valid only while it matches",
        "created_at": "NOT NULL creation time shown on the Users page",
        "last_login_at": "last successful login shown on the Users page; NULL until then",
    },
```

- [ ] **Step 5: Write the migration**

Create `swingbot/core/db/migrations/versions/v207_001_admin_users.py`:

```python
"""v207: admin_users -- read-only viewer accounts beside the `.env` admin.

Additive: rollback is redeploying the previous image (the old code never reads
the table, so it can stay). This revision's downgrade drops the table and
every viewer account with it.

Revision ID: v207_001
Revises: v205_001
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "v207_001"
down_revision = "v205_001"   # = python -m alembic heads on the branch at implementation time
branch_labels = None
depends_on = None

_TS = sa.TIMESTAMP(timezone=True)


def _standard():
    return [sa.Column("doc", postgresql.JSONB(), nullable=False,
                      server_default=sa.text("'{}'::jsonb")),
            sa.Column("updated_at", _TS, nullable=False, server_default=sa.func.now())]


def upgrade() -> None:
    op.create_table("admin_users",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("username", sa.Text, nullable=False),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column("role", sa.Text, nullable=False, server_default=sa.text("'viewer'")),
        sa.Column("disabled", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("credential_version", sa.Integer, nullable=False,
                  server_default=sa.text("1")),
        sa.Column("created_at", _TS, nullable=False, server_default=sa.func.now()),
        sa.Column("last_login_at", _TS),
        *_standard(),
        sa.CheckConstraint("role IN ('viewer')", name="admin_users_role_ck"))
    op.create_index("admin_users_username_lower_uq", "admin_users",
                    [sa.text("lower(username)")], unique=True)


def downgrade() -> None:
    op.drop_index("admin_users_username_lower_uq", table_name="admin_users")
    op.drop_table("admin_users")
```

If Step 1 printed a head other than `v205_001`, put that id in `down_revision` and the `Revises:` line.

- [ ] **Step 6: Excuse the table from the round-trip registry until its repository exists**

In `tests/db/test_unknown_field_round_trip.py`, add to `NOT_REPOSITORY_BACKED` (after the `fx_daily_rates` entry):

```python
    "admin_users": "v207: its repository arrives in V207-2, which moves this entry to CASES",
```

- [ ] **Step 7: Run the tests to see them pass**

Run: `cd "<wt>" && python scripts/dev/testrun.py file tests/db/test_v207_admin_users.py`
Expected: PASS (8 tests).

Run: `cd "<wt>" && python scripts/dev/testrun.py file tests/db/test_schema_contract.py`
Expected: PASS (the migrated-database contract reflects `admin_users` too).

Run: `cd "<wt>" && python scripts/dev/testrun.py file tests/db/test_unknown_field_round_trip.py`
Expected: PASS.

Run: `cd "<wt>" && python scripts/dev/testrun.py file tests/db/test_schema.py`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git -C "<wt>" add swingbot/core/db/schema.py swingbot/core/db/migrations/versions/v207_001_admin_users.py tests/db/test_v207_admin_users.py tests/db/test_unknown_field_round_trip.py
git -C "<wt>" commit -m "feat(v207): admin_users table and Alembic v207_001 (V207-1)"
```

### Task V207-2: `AdminUsersRepository` with the `UndefinedTable` guard

**Model:** sonnet — one repository on the existing `Repository` base with focused DB tests; the only subtlety (the missing-table guard) is spelled out below.

**Files:**
- Create: `swingbot/core/db/repositories/admin_users.py`
- Create: `tests/db/test_admin_users_repository.py`
- Modify: `tests/db/test_unknown_field_round_trip.py` (move `admin_users` from `NOT_REPOSITORY_BACKED` to `CASES`)

**Interfaces:**
- Consumes: `schema.admin_users` (V207-1); `repositories/base.py:Repository` (`_tx`, `_record`, `insert`, `delete`).
- Produces (V207-3, V207-4, V207-6 call these):
  - `class UsernameTaken(Exception)`.
  - `class AdminUsersRepository(Repository)`; every method takes an optional keyword `conn: sa.Connection | None = None`.
  - `list_users() -> list[dict]` ordered by `id`; `get_by_username(username: str) -> dict | None` (case-insensitive); `get_by_id(user_id: int) -> dict | None`; `create_user(username, password_hash, *, role="viewer") -> dict` (raises `UsernameTaken`); `set_disabled(user_id, disabled: bool) -> dict | None` (bumps `credential_version` only when `disabled` is True); `reset_password(user_id, password_hash) -> dict | None` (bumps); `delete_user(user_id) -> bool`; `touch_last_login(user_id) -> None`.
  - Row dict keys always include `id, username, password_hash, role, disabled, credential_version, created_at, last_login_at` (`last_login_at` is `None` until the first login), plus any `doc` keys.
  - `admin_users_repo() -> AdminUsersRepository` module singleton (module attribute `_repo`; tests swap it).
  - Before `v207_001` has run: `list_users` → `[]`, `get_by_username` / `get_by_id` → `None`, `touch_last_login` → no-op; one `WARNING` per process (`admin_users table missing; viewer logins are refused until alembic upgrade head`). Mutations (`create_user`, `set_disabled`, `reset_password`, `delete_user`) still raise: only the admin reaches them, and a 500 there during the deploy window is honest.

`UndefinedTable` reaches this code as `sqlalchemy.exc.ProgrammingError` whose `.orig` is `psycopg.errors.UndefinedTable` (driver: psycopg 3, `engine.py:96`). The test produces a real one by pointing a repository at a table name that does not exist, rather than dropping the shared test table.

- [ ] **Step 1: Write the failing tests**

Create `tests/db/test_admin_users_repository.py`:

```python
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
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd "<wt>" && python scripts/dev/testrun.py file tests/db/test_admin_users_repository.py`
Expected: FAIL — `ImportError: cannot import name 'admin_users' from 'swingbot.core.db.repositories'`.

- [ ] **Step 3: Write the repository**

Create `swingbot/core/db/repositories/admin_users.py`:

```python
"""v207: viewer accounts (`admin_users`).

The `.env` admin is never stored; every row is a read-only viewer. Lookups
answer "no such user" while the table does not exist yet: the containers start
before `alembic upgrade head` runs on a deploy (deploy/deploy.sh), and a viewer
login in that window must be invalid credentials, not a 500. Writes are not
guarded -- only the admin reaches them, and the admin is checked against
`.env` without touching this table.
"""
from __future__ import annotations

import logging
from typing import Callable, TypeVar

import psycopg
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError, ProgrammingError

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import admin_users

log = logging.getLogger(__name__)

T = TypeVar("T")

ROW_FIELDS = ("id", "username", "password_hash", "role", "disabled",
              "credential_version", "created_at", "last_login_at")

_warned_missing = False


class UsernameTaken(Exception):
    """The username exists already, compared case-insensitively."""


def _is_undefined_table(exc: ProgrammingError) -> bool:
    return isinstance(getattr(exc, "orig", None), psycopg.errors.UndefinedTable)


def _warn_missing_once() -> None:
    global _warned_missing
    if not _warned_missing:
        _warned_missing = True
        log.warning("admin_users table missing; viewer logins are refused "
                    "until alembic upgrade head")


def _missing_table_as(default: T, read: Callable[[], T]) -> T:
    """Run a read; a not-yet-migrated table answers `default`."""
    try:
        return read()
    except ProgrammingError as exc:
        if not _is_undefined_table(exc):
            raise
        _warn_missing_once()
        return default


class AdminUsersRepository(Repository):
    def __init__(self):
        super().__init__(admin_users, key="id")

    def _record(self, row) -> dict:
        # `id` is a reserved key merge_doc drops, and a NULL last_login_at
        # would be omitted; the Users API and the session need both.
        mapping = row._mapping
        return {**super()._record(row), **{name: mapping[name] for name in ROW_FIELDS}}

    def _select_one(self, where, conn) -> dict | None:
        with self._tx(conn) as connection:
            row = connection.execute(sa.select(self.table).where(where)).one_or_none()
        return None if row is None else self._record(row)

    def _update(self, user_id: int, values: dict, conn) -> dict | None:
        statement = (sa.update(self.table).where(self.table.c.id == user_id)
                     .values(**values, updated_at=sa.func.clock_timestamp())
                     .returning(self.table))
        with self._tx(conn) as connection:
            row = connection.execute(statement).one_or_none()
        return None if row is None else self._record(row)

    def list_users(self, *, conn: sa.Connection | None = None) -> list[dict]:
        return _missing_table_as([], lambda: self.list_all(conn=conn, order_by=self.table.c.id))

    def get_by_username(self, username: str, *,
                        conn: sa.Connection | None = None) -> dict | None:
        where = sa.func.lower(self.table.c.username) == username.lower()
        return _missing_table_as(None, lambda: self._select_one(where, conn))

    def get_by_id(self, user_id: int, *, conn: sa.Connection | None = None) -> dict | None:
        return _missing_table_as(None, lambda: self._select_one(self.table.c.id == user_id, conn))

    def create_user(self, username: str, password_hash: str, *, role: str = "viewer",
                    conn: sa.Connection | None = None) -> dict:
        record = {"username": username, "password_hash": password_hash, "role": role}
        try:
            if conn is None:
                return self.insert(record)
            with conn.begin_nested():   # keep the caller's transaction usable on a clash
                return self.insert(record, conn=conn)
        except IntegrityError as exc:
            if isinstance(exc.orig, psycopg.errors.UniqueViolation):
                raise UsernameTaken(username) from exc
            raise

    def set_disabled(self, user_id: int, disabled: bool, *,
                     conn: sa.Connection | None = None) -> dict | None:
        values: dict = {"disabled": disabled}
        if disabled:   # re-enabling must not revive sessions issued before the disable
            values["credential_version"] = self.table.c.credential_version + 1
        return self._update(user_id, values, conn)

    def reset_password(self, user_id: int, password_hash: str, *,
                       conn: sa.Connection | None = None) -> dict | None:
        return self._update(user_id, {
            "password_hash": password_hash,
            "credential_version": self.table.c.credential_version + 1}, conn)

    def delete_user(self, user_id: int, *, conn: sa.Connection | None = None) -> bool:
        return self.delete(user_id, conn=conn)

    def touch_last_login(self, user_id: int, *, conn: sa.Connection | None = None) -> None:
        _missing_table_as(None, lambda: self._update(
            user_id, {"last_login_at": sa.func.now()}, conn))


_repo: AdminUsersRepository | None = None


def admin_users_repo() -> AdminUsersRepository:
    global _repo
    if _repo is None:
        _repo = AdminUsersRepository()
    return _repo
```

`test_duplicate_name_in_any_case_raises_username_taken` uses no `conn` on purpose: the autouse `_store_database` fixture (`tests/conftest.py:228`) points `base.get_engine` at the worker's test database and truncates `admin_users` after the test, so the failed insert runs in its own transaction.

- [ ] **Step 4: Run them to see them pass**

Run: `cd "<wt>" && python scripts/dev/testrun.py file tests/db/test_admin_users_repository.py`
Expected: PASS (12 tests).

- [ ] **Step 5: Move the table into the round-trip registry**

In `tests/db/test_unknown_field_round_trip.py`: delete the `"admin_users": "v207: ..."` line from `NOT_REPOSITORY_BACKED`; add the import beside the other repository imports

```python
from swingbot.core.db.repositories.admin_users import AdminUsersRepository
```

and this `CASES` entry (after the v201 entries; `_write` inserts because the key is `id`):

```python
    # v207: viewer accounts.
    "admin_users": (AdminUsersRepository, {"username": "probe-user", "password_hash": "h"}),
```

Run: `cd "<wt>" && python scripts/dev/testrun.py file tests/db/test_unknown_field_round_trip.py`
Expected: PASS, including `test_an_unseen_field_round_trips_unchanged[admin_users]`.

- [ ] **Step 6: Complexity gate**

Run: `cd "<wt>" && python scripts/dev/complexity_gate.py`
Expected: exit 0; every function in `admin_users.py` is at most 4.

- [ ] **Step 7: Commit**

```bash
git -C "<wt>" add swingbot/core/db/repositories/admin_users.py tests/db/test_admin_users_repository.py tests/db/test_unknown_field_round_trip.py
git -C "<wt>" commit -m "feat(v207): AdminUsersRepository with the pre-migration UndefinedTable guard (V207-2)"
```

# Phase B — principals and login

### Task V207-3: `principals.py`: hashing, validation, viewer authentication

**Model:** sonnet — a small new module of pure-ish functions over the V207-2 repository, with table-driven tests; no cross-package seam beyond the repository call.

**Files:**
- Create: `swingbot/admin/principals.py`
- Create: `tests/admin/test_principals.py`
- Modify: `tests/admin/conftest.py` (autouse `_fast_password_hash`; fixture `admin_users_table_missing`)

**Interfaces:**
- Consumes: `swingbot.core.db.repositories.admin_users` (V207-2) — `admin_users_repo()`, `get_by_username`, `get_by_id`, `touch_last_login`, module attribute `_repo`, `AdminUsersRepository`; `schema.admin_users` (V207-1).
- Produces (V207-4 and V207-6 call these through the module, `from swingbot.admin import principals`):
  - `HASH_METHOD = "scrypt"` (module attribute, read at call time; the admin test suite swaps in `"pbkdf2:sha256:1"`).
  - `PASSWORD_MIN = 12`.
  - `hash_password(password: str) -> str`.
  - `verify_password(pw_hash: str | None, password: str) -> bool` — `None` still runs one `check_password_hash` against a dummy hash computed once per `HASH_METHOD`, then answers False.
  - `validate_username(name) -> str | None` — `None` when valid, else a message starting `"username "`.
  - `validate_password(password) -> str | None` — `None` when valid, else a message starting `"password "`.
  - `authenticate_viewer(username: str, password: str) -> dict | None` — the repository row on success (and `last_login_at` touched); `None` for unknown, disabled, wrong password or a missing table. Exactly one hash check on every path.
  - `viewer_principal(user_id, credential_version) -> dict | None` — `{"role": "viewer", "username": <row's current name>, "user_id": <id>}` while the row exists, is enabled and has that `credential_version`; else `None`.
  - Test fixtures in `tests/admin/conftest.py`: autouse `_fast_password_hash`; `admin_users_table_missing` (swaps `admin_users._repo` for a repository on a table that does not exist).
- `principals.py` imports nothing from `swingbot.admin` (it is imported BY `app.py`; a test pins it).

- [ ] **Step 1: Add the fixtures to `tests/admin/conftest.py`**

Append after `_clear_login_limiter`:

```python
@pytest.fixture(autouse=True)
def _fast_password_hash(monkeypatch):
    """v207: scrypt costs tens of milliseconds per hash. Viewer tests hash and
    check passwords constantly, so the suite uses a one-iteration PBKDF2;
    production keeps principals.HASH_METHOD = "scrypt". A stored hash names its
    own method, so checks keep working whichever method made it."""
    from swingbot.admin import principals

    monkeypatch.setattr(principals, "HASH_METHOD", "pbkdf2:sha256:1")


@pytest.fixture
def admin_users_table_missing(monkeypatch):
    """v207: the deploy window before `alembic upgrade head` -- the admin_users
    repository points at a table Postgres has never seen, so every lookup
    raises a real UndefinedTable (the shared test table is left alone)."""
    import sqlalchemy as sa

    from swingbot.core.db import schema
    from swingbot.core.db.repositories import admin_users as au

    ghost = sa.Table("admin_users_not_migrated", sa.MetaData(),
                     *[sa.Column(c.name, c.type, primary_key=c.primary_key)
                       for c in schema.admin_users.columns])
    repo = au.AdminUsersRepository()
    repo.table, repo.key_col = ghost, ghost.c.id
    monkeypatch.setattr(au, "_repo", repo)
    monkeypatch.setattr(au, "_warned_missing", False)
    return repo
```

- [ ] **Step 2: Write the failing tests**

Create `tests/admin/test_principals.py`:

```python
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
```

- [ ] **Step 3: Run them to see them fail**

Run: `cd "<wt>" && python scripts/dev/testrun.py file tests/admin/test_principals.py`
Expected: FAIL — `ImportError: cannot import name 'principals' from 'swingbot.admin'` (collection error; the autouse fixture fails the same way).

- [ ] **Step 4: Write `principals.py`**

Create `swingbot/admin/principals.py`:

```python
"""v207: viewer principals -- the database half of "who is this".

The `.env` admin stays in app.py (`credentials_match`, `_password_hash`) and
is never stored. Every `admin_users` row is a read-only viewer. This module
hashes and checks viewer passwords, validates new usernames and passwords, and
answers the two lookups the admin needs: "do these credentials name a live
viewer" (login) and "is this session's viewer still valid" (every request).

It imports nothing from swingbot.admin: app.py imports it, and the admin test
suite reloads app.py per test. HASH_METHOD is read at call time so that suite
can swap scrypt for a cheap method. Nothing here logs, returns or serialises a
password; only authenticate_viewer returns the stored hash, inside the row the
login code discards.
"""
from __future__ import annotations

import re
import secrets

from werkzeug.security import check_password_hash, generate_password_hash

from swingbot.core.db.repositories import admin_users

HASH_METHOD = "scrypt"
PASSWORD_MIN = 12
USERNAME_RE = re.compile(r"[A-Za-z0-9._-]{3,64}")
USERNAME_RULE = "username must be 3-64 characters: letters, digits, '.', '_' or '-'."
PASSWORD_RULE = f"password must be at least {PASSWORD_MIN} characters."

# One dummy hash per method, made on first use: an unknown username still pays
# for one real check, so response time does not reveal which names exist.
_DUMMY_HASHES: dict[str, str] = {}


def hash_password(password: str) -> str:
    return generate_password_hash(password, method=HASH_METHOD)


def _dummy_hash() -> str:
    method = HASH_METHOD
    if method not in _DUMMY_HASHES:
        _DUMMY_HASHES[method] = generate_password_hash(secrets.token_urlsafe(24),
                                                       method=method)
    return _DUMMY_HASHES[method]


def verify_password(pw_hash: str | None, password: str) -> bool:
    if pw_hash is None:
        check_password_hash(_dummy_hash(), password)
        return False
    return check_password_hash(pw_hash, password)


def validate_username(name) -> str | None:
    if isinstance(name, str) and USERNAME_RE.fullmatch(name):
        return None
    return USERNAME_RULE


def validate_password(password) -> str | None:
    if isinstance(password, str) and len(password) >= PASSWORD_MIN:
        return None
    return PASSWORD_RULE


def authenticate_viewer(username: str, password: str) -> dict | None:
    """The viewer row these credentials name, or None. Unknown, disabled and
    wrong-password cases each run exactly one hash check."""
    repo = admin_users.admin_users_repo()
    row = repo.get_by_username(username) if username else None
    matched = verify_password(row["password_hash"] if row else None, password)
    if row is None or row["disabled"] or not matched:
        return None
    repo.touch_last_login(row["id"])
    return row


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def viewer_principal(user_id, credential_version) -> dict | None:
    """The principal for a viewer session's fields while they are still valid."""
    if not (_is_int(user_id) and _is_int(credential_version)):
        return None
    row = admin_users.admin_users_repo().get_by_id(user_id)
    if row is None or row["disabled"] or row["credential_version"] != credential_version:
        return None
    return {"role": "viewer", "username": row["username"], "user_id": row["id"]}
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `cd "<wt>" && python scripts/dev/testrun.py file tests/admin/test_principals.py`
Expected: PASS (every test, parametrized cases included).

Run: `cd "<wt>" && python scripts/dev/testrun.py file tests/admin/test_api_v1_session.py`
Expected: PASS unchanged (the autouse fixture only patches a module attribute).

- [ ] **Step 6: Complexity gate**

Run: `cd "<wt>" && python scripts/dev/complexity_gate.py`
Expected: exit 0; every function in `principals.py` is at most 5 (cap 12 for auth code, index § Global Constraints).

- [ ] **Step 7: Commit**

```bash
git -C "<wt>" add swingbot/admin/principals.py tests/admin/test_principals.py tests/admin/conftest.py
git -C "<wt>" commit -m "feat(v207): principals -- viewer password hashing, validation, authentication (V207-3)"
```

### Task V207-4: `resolve_principal` and the principal-returning login check

**Model:** opus — the security boundary itself: every auth path (both `require_auth` decorators, `/session`, the later access hook and SSE) changes meaning through this resolver, and a mistake lets a viewer session pass as the admin.

Split from the ledger's V207-4 at the 20 KB cap: this task builds the resolver and the limiter variant; V207-4b wires them into `/api/v1/session` and adds the `viewer_client` fixture.

**Files:**
- Modify: `swingbot/admin/app.py` (auth block :119-162; flask import :42; package imports :50-52)
- Modify: `swingbot/admin/login_limiter.py` (`Attempt` / `attempt` :109-130)
- Create: `tests/admin/test_viewer_login.py`

**Interfaces:**
- Consumes: `principals.authenticate_viewer`, `principals.viewer_principal`, `principals.hash_password` (V207-3); `admin_users_repo()`, `set_disabled` (V207-2); conftest fixture `admin_users_table_missing` (V207-3).
- Produces (V207-4b..V207-8 call these through the module, `from swingbot.admin import app as _app`):
  - `app.login_session_fields(username: str, password: str) -> dict | None` — admin: `{"admin_authed": True, "pw_hash": <_password_hash()>, "role": "admin"}`; viewer: `{"role": "viewer", "user_id": int, "credential_version": int, "username": str}`; else `None`. The `.env` admin is tried first and never touches the table.
  - `app.principal_from_session(data: Mapping) -> dict | None` — no request context needed (V207-8 calls it on a snapshot). Missing `role` means admin (sessions issued before the deploy).
  - `app.resolve_principal() -> dict | None` — `principal_from_session(flask.session)`, cached on `flask.g` for the request.
  - `app.forget_principal() -> None` — drops the cached value (V207-4b calls it after the session changes inside a request).
  - `app._session_authenticated() -> bool` — now `resolve_principal() is not None`; signature unchanged, so both `require_auth` decorators and `tests/admin/test_api_v1_risk.py:800`'s monkeypatch keep working.
  - Principal dict: `{"role": "admin" | "viewer", "username": str, "user_id": int | None}`.
  - `login_limiter.LoginAttempt(result: dict | None = None, retry_after: int | None = None)` with property `.ok` (`result is not None`); `login_limiter.attempt_login(username, password, authenticate: Callable[[str, str], dict | None]) -> LoginAttempt`. `attempt()` keeps its `Attempt` bool shape for Basic and now delegates to `attempt_login`.

After this task `/session` still signs in only the admin (V207-4b switches it); existing admin sessions resolve through the new path with no behaviour change.

- [ ] **Step 1: Write the failing tests**

Create `tests/admin/test_viewer_login.py`:

```python
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
        assert login_limiter.attempt("a", "b", lambda u, p: False) == login_limiter.Attempt(False)
```

- [ ] **Step 2: Run them to see them fail**

Run: `cd "<wt>" && python scripts/dev/testrun.py file tests/admin/test_viewer_login.py`
Expected: FAIL — `AttributeError: module 'swingbot.admin.app' has no attribute 'login_session_fields'` / `'principal_from_session'`, `module 'swingbot.admin.login_limiter' has no attribute 'attempt_login'`. (The Basic test already passes: Basic never reached a table.)

- [ ] **Step 3: `login_limiter.py` — the principal-returning variant**

Replace the `Attempt` / `attempt` block (:109-130) with:

```python
@dataclass(frozen=True)
class Attempt:
    """One gated credential check. `retry_after` is set only when locked."""
    ok: bool
    retry_after: int | None = None


@dataclass(frozen=True)
class LoginAttempt:
    """One gated sign-in that names who signed in (v207). `result` is what the
    authenticate callable returned; `retry_after` is set only when locked."""
    result: dict | None = None
    retry_after: int | None = None

    @property
    def ok(self) -> bool:
        return self.result is not None


def attempt_login(username: str, password: str,
                  authenticate: Callable[[str, str], dict | None]) -> LoginAttempt:
    """Gate one sign-in through LIMITER (read at call time).

    A locked key is refused before the credentials are checked. Empty
    username AND password is not an attempt and is never counted. Every other
    outcome -- wrong password, unknown user, disabled user -- is one failure."""
    key = client_key()
    wait = LIMITER.check(key)
    if wait is not None:
        return LoginAttempt(None, wait)
    if not username and not password:
        return LoginAttempt()
    result = authenticate(username, password)
    if result is None:
        LIMITER.fail(key)
        return LoginAttempt()
    LIMITER.succeed(key)
    return LoginAttempt(result)


def attempt(username: str, password: str, match: Callable[[str, str], bool]) -> Attempt:
    """The bool-shaped gate Basic auth keeps (v207 Decision 7)."""
    outcome = attempt_login(username, password,
                            lambda u, p: {} if match(u, p) else None)
    return Attempt(outcome.ok, outcome.retry_after)
```

- [ ] **Step 4: `app.py` — one resolver**

Change the flask import (:42) to `from flask import Flask, Response, g, redirect, request, session, url_for`, add `from collections.abc import Mapping` beside the other stdlib imports, and add `from . import principals` beside `from . import login_limiter` (:50).

Replace `_session_authenticated` (:146-149) with:

```python
_PRINCIPAL_G = "v207_principal"
_UNRESOLVED = object()


def _admin_principal() -> dict:
    return {"role": "admin", "username": ADMIN_USERNAME, "user_id": None}


def _admin_session_valid(data: Mapping) -> bool:
    return data.get("admin_authed") is True and hmac.compare_digest(
        str(data.get("pw_hash", "")), _password_hash()
    )


def principal_from_session(data: Mapping) -> dict | None:
    """Who a session's fields name, re-checked against today's credentials.

    v207. Admin: `admin_authed` + the current `_password_hash()`; a session
    with no `role` key was issued before v207 and is the admin. Viewer: the
    `admin_users` row must exist, be enabled and carry the same
    `credential_version` (principals.viewer_principal), so disable, reset and
    delete end the session on its next request. A viewer session is never
    checked as the admin, whatever else it carries. Needs no request context:
    the SSE stream calls it on a snapshot (events/stream.py)."""
    role = data.get("role", "admin")
    if role == "admin":
        return _admin_principal() if _admin_session_valid(data) else None
    if role == "viewer":
        return principals.viewer_principal(data.get("user_id"),
                                           data.get("credential_version"))
    return None


def resolve_principal() -> dict | None:
    """The request's principal, or None. The one place every auth path asks:
    `_session_authenticated`, `/session`, the api_v1 access hook, `/events`.
    Cached on `flask.g`: a viewer costs one row read per request, not one per
    caller."""
    cached = g.get(_PRINCIPAL_G, _UNRESOLVED)
    if cached is _UNRESOLVED:
        cached = principal_from_session(session)
        setattr(g, _PRINCIPAL_G, cached)
    return cached


def forget_principal() -> None:
    """Drop the cached principal after the session changed in this request."""
    g.pop(_PRINCIPAL_G, None)


def _session_authenticated() -> bool:
    return resolve_principal() is not None
```

Add directly after `credentials_match` (which stays unchanged):

```python
def login_session_fields(username: str, password: str) -> dict | None:
    """The session fields a successful sign-in stores, or None (v207).

    The `.env` admin is tried first with the constant-time `credentials_match`
    and never touches `admin_users`, so the admin can sign in even before the
    table exists. Then the table: principals.authenticate_viewer runs exactly
    one hash check for unknown, disabled and wrong-password cases alike."""
    if credentials_match(username, password):
        return {"admin_authed": True, "pw_hash": _password_hash(), "role": "admin"}
    row = principals.authenticate_viewer(username, password)
    if row is None:
        return None
    return {"role": "viewer", "user_id": row["id"],
            "credential_version": row["credential_version"], "username": row["username"]}
```

Leave the legacy `require_auth` (:165-200) untouched; it already calls `_session_authenticated()`.

- [ ] **Step 5: Run the tests to see them pass**

Run: `cd "<wt>" && python scripts/dev/testrun.py file tests/admin/test_viewer_login.py`
Expected: PASS.

Run: `cd "<wt>" && python scripts/dev/testrun.py file tests/admin/test_api_v1_session.py`
Expected: PASS unchanged (the password-rotation test now runs through `resolve_principal`; `/session` bodies do not change until V207-4b).

Run: `cd "<wt>" && python scripts/dev/testrun.py file tests/admin/test_login_limiter.py`
Expected: PASS unchanged (`attempt` keeps its contract).

Run: `cd "<wt>" && python scripts/dev/testrun.py file tests/admin/test_api_v1_risk.py`
Expected: PASS (its `_session_authenticated` monkeypatch still applies).

- [ ] **Step 6: Complexity gate**

Run: `cd "<wt>" && python scripts/dev/complexity_gate.py`
Expected: exit 0. `principal_from_session` 4, `resolve_principal` 2, `login_session_fields` 3, `attempt_login` 4 — within the auth cap of 12; legacy `app.require_auth` unchanged.

- [ ] **Step 7: Commit**

```bash
git -C "<wt>" add swingbot/admin/app.py swingbot/admin/login_limiter.py tests/admin/test_viewer_login.py
git -C "<wt>" commit -m "feat(v207): one principal resolver and the principal-returning login check (V207-4)"
```

