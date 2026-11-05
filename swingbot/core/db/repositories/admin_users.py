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
