"""v152 D1: each Discord user's /notify settings -- one flat doc per user.

The doc holds one boolean per notify event the user toggled, plus
`watch_mode` ("mention" | "silent"); a missing key means "use the default"
(follow_notify owns the defaults and the valid names). Writes merge with
JSONB `||` inside one upsert, so two toggles never race a read-modify-write."""
from __future__ import annotations

from typing import Iterable

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert

from swingbot.core.db.codec import RESERVED_KEYS
from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import notify_prefs

_FORBIDDEN_KEYS = RESERVED_KEYS | {"user_id"}


class NotifyPrefsRepository(Repository):
    def __init__(self):
        super().__init__(notify_prefs, key="id")

    def prefs(self, user_id: int, *, conn=None) -> dict:
        return self.prefs_many([user_id], conn=conn)[int(user_id)]

    def prefs_many(self, user_ids: Iterable[int], *, conn=None) -> dict[int, dict]:
        ids = sorted({int(user_id) for user_id in user_ids})
        found: dict[int, dict] = {user_id: {} for user_id in ids}
        if not ids:
            return found
        c = self.table.c
        statement = sa.select(c.user_id, c.doc).where(c.user_id.in_(ids))
        with self._tx(conn) as connection:
            for user_id, doc in connection.execute(statement).all():
                found[int(user_id)] = dict(doc or {})
        return found

    def set_pref(self, user_id: int, key: str, value: bool | str, *, conn=None) -> None:
        if not key or key in _FORBIDDEN_KEYS:
            raise ValueError(f"not a preference key: {key!r}")
        if not isinstance(value, (bool, str)):
            raise TypeError(f"preference {key!r} must be bool or str, got {type(value).__name__}")
        statement = pg_insert(self.table).values(user_id=int(user_id), doc={key: value})
        statement = statement.on_conflict_do_update(
            index_elements=[self.table.c.user_id],
            set_={"doc": self.table.c.doc.op("||")(statement.excluded.doc),
                  "updated_at": sa.func.clock_timestamp()},
        )
        with self._tx(conn) as connection:
            connection.execute(statement)


_repo: NotifyPrefsRepository | None = None


def notify_prefs_repo() -> NotifyPrefsRepository:
    global _repo
    if _repo is None:
        _repo = NotifyPrefsRepository()
    return _repo
