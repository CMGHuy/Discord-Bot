"""v152 D2: who follows a plan -- one row per (plan_id, user_id, kind).

`watch` is the per-user Watch button; `taken` is the Following button, which
records intent to follow the plan, never a fill. The natural key is composite,
so the writes are their own SQL rather than the single-key Repository.upsert.
Callers on the Discord event loop wrap every method in asyncio.to_thread."""
from __future__ import annotations

import datetime as dt
from typing import Iterable

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import plan_followers

FOLLOW_KINDS = ("watch", "taken")


def _check_kind(kind: str) -> str:
    if kind not in FOLLOW_KINDS:
        raise ValueError(f"unknown follower kind {kind!r}; expected one of {FOLLOW_KINDS}")
    return kind


class FollowersRepository(Repository):
    def __init__(self):
        super().__init__(plan_followers, key="id")

    def _row(self, plan_id: str, user_id: int, kind: str):
        c = self.table.c
        return sa.and_(c.plan_id == plan_id, c.user_id == int(user_id),
                       c.kind == _check_kind(kind))

    def add(self, plan_id: str, user_id: int, kind: str, *, status_at_press: str,
            conn=None) -> bool:
        record = {"plan_id": plan_id, "user_id": int(user_id), "kind": _check_kind(kind),
                  "at": dt.datetime.now(dt.timezone.utc).isoformat(),
                  "status_at_press": status_at_press}
        statement = (pg_insert(self.table).values(**self._values(record))
                     .on_conflict_do_nothing(constraint="plan_followers_row_uq")
                     .returning(self.table.c.id))
        with self._tx(conn) as connection:
            # RETURNING yields a row only for an actual insert; rowcount is not
            # reliable on an INSERT whose primary key SQLAlchemy returns itself.
            return connection.execute(statement).first() is not None

    def remove(self, plan_id: str, user_id: int, kind: str, *, conn=None) -> bool:
        statement = sa.delete(self.table).where(self._row(plan_id, user_id, kind))
        with self._tx(conn) as connection:
            return connection.execute(statement).rowcount > 0

    def has(self, plan_id: str, user_id: int, kind: str, *, conn=None) -> bool:
        statement = (sa.select(self.table.c.id)
                     .where(self._row(plan_id, user_id, kind)).limit(1))
        with self._tx(conn) as connection:
            return connection.execute(statement).first() is not None

    def user_ids(self, plan_id: str, kinds: Iterable[str], *, conn=None) -> list[int]:
        wanted = tuple(_check_kind(kind) for kind in kinds)
        if not wanted:
            return []
        c = self.table.c
        statement = (sa.select(c.user_id).where(c.plan_id == plan_id, c.kind.in_(wanted))
                     .distinct().order_by(c.user_id))
        with self._tx(conn) as connection:
            return [int(user_id) for user_id in connection.execute(statement).scalars()]

    def followers(self, plan_id: str, *, conn=None) -> dict[int, frozenset[str]]:
        c = self.table.c
        statement = sa.select(c.user_id, c.kind).where(c.plan_id == plan_id)
        kinds: dict[int, set[str]] = {}
        with self._tx(conn) as connection:
            for user_id, kind in connection.execute(statement).all():
                kinds.setdefault(int(user_id), set()).add(kind)
        return {user_id: frozenset(held) for user_id, held in sorted(kinds.items())}


_repo: FollowersRepository | None = None


def followers_repo() -> FollowersRepository:
    global _repo
    if _repo is None:
        _repo = FollowersRepository()
    return _repo
