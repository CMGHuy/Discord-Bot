"""v227: the simple-channel post log the admin site speaks from, append-only.

One row per simple-channel post Discord accepted: promoted posted_at / kind /
ticker / headline, ``doc`` always ``{}``. Written synchronously by the bot
process only (swingbot.core.infra.feed_posts.record_feed_post), so id order is
commit order and ``after(id)`` paging never skips a row. Read by
``GET /api/v1/feed-posts``. Pruned after a week by the recorder.

The table's NOTIFY trigger is statement-level: every INSERT/UPDATE/DELETE,
even one touching zero rows, raises the ``feed`` SSE event. ``prune``
therefore looks for an old row first and only then deletes.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import sqlalchemy as sa

from swingbot.core.db import engine as db_engine
from swingbot.core.db.schema import feed_posts

_COLUMNS = ("id", "posted_at", "kind", "ticker", "headline")


class FeedPostsRepository:
    def __init__(self):
        self.table = feed_posts

    @contextmanager
    def _tx(self, conn: sa.Connection | None) -> Iterator[sa.Connection]:
        if conn is not None:
            yield conn
            return
        # Through the module attribute, never a name bound at import: the test
        # conftest swaps engine.get_engine for this worker's database.
        with db_engine.get_engine().begin() as owned:
            yield owned

    def insert(self, kind: str, ticker: str | None, headline: str, *,
               conn: sa.Connection) -> int:
        statement = (sa.insert(self.table)
                     .values(kind=kind, ticker=ticker, headline=headline, doc={})
                     .returning(self.table.c.id))
        return int(conn.execute(statement).scalar_one())

    def after(self, after_id: int, limit: int, *,
              conn: sa.Connection | None = None) -> list[dict]:
        c = self.table.c
        statement = (sa.select(*(c[name] for name in _COLUMNS))
                     .where(c.id > after_id).order_by(c.id).limit(limit))
        with self._tx(conn) as connection:
            return [dict(row._mapping) for row in connection.execute(statement)]

    def latest_id(self, *, conn: sa.Connection | None = None) -> int:
        statement = sa.select(sa.func.coalesce(sa.func.max(self.table.c.id), 0))
        with self._tx(conn) as connection:
            return int(connection.execute(statement).scalar_one())

    def prune(self, days: int, *, conn: sa.Connection) -> int:
        cutoff = sa.func.now() - sa.literal_column(f"interval '{int(days)} days'")
        old = self.table.c.posted_at < cutoff
        found = conn.execute(sa.select(sa.literal(1)).where(old).limit(1)).first()
        if found is None:
            return 0    # no DELETE: the statement trigger would raise an empty `feed` event
        return conn.execute(sa.delete(self.table).where(old)).rowcount


_repo: FeedPostsRepository | None = None


def feed_posts_repo() -> FeedPostsRepository:
    global _repo
    if _repo is None:
        _repo = FeedPostsRepository()
    return _repo
