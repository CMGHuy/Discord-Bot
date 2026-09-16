"""Manual-close notifications: an append-only queue the bot drains."""
from __future__ import annotations

import datetime as dt

import sqlalchemy as sa

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import manual_close_notify


class NotifyQueueRepository(Repository):
    def __init__(self):
        super().__init__(manual_close_notify, key="id")

    def enqueue(self, payload: dict, *, conn=None) -> None:
        self.insert({"queued_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                     **payload}, conn=conn)

    def pending(self, *, conn=None) -> int:
        return self.count(conn=conn)

    def drain(self, *, conn=None) -> list[dict]:
        """Atomically remove and return the queue's current contents."""
        stmt = sa.delete(manual_close_notify).returning(manual_close_notify)
        with self._tx(conn) as connection:
            rows = connection.execute(stmt).all()
        records = [self._record(row) for row in rows]
        records.sort(key=lambda record: record.get("queued_at") or "")
        for record in records:
            record.pop("queued_at", None)
        return records


_repo: NotifyQueueRepository | None = None


def notify_queue_repo() -> NotifyQueueRepository:
    global _repo
    if _repo is None:
        _repo = NotifyQueueRepository()
    return _repo
