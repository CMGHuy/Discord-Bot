"""Bot liveness: one singleton row keyed by ``bot``."""
from __future__ import annotations

import datetime as dt

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import bot_heartbeat


KEY = "bot"


class HeartbeatRepository(Repository):
    def __init__(self):
        super().__init__(bot_heartbeat, key="key")

    def beat(self, fields: dict, *, conn=None) -> None:
        self.upsert({
            "key": KEY,
            "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
            **fields,
        }, conn=conn)

    def last(self, *, conn=None) -> dict | None:
        row = self.get(KEY, conn=conn)
        if row is None:
            return None
        return {key: value for key, value in row.items() if key != "key"}


_repo: HeartbeatRepository | None = None


def heartbeat_repo() -> HeartbeatRepository:
    global _repo
    if _repo is None:
        _repo = HeartbeatRepository()
    return _repo
