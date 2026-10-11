"""v152 D3: the scheduled scan's alert-post record, append-only.

One row per alert the scheduled session scan posted or held: promoted
ticker/at/outcome (alert_posts_ticker_at_idx serves the per-ticker window),
doc {direction, horizon_key, plan_id}. No foreign key to plans: the record
outlives plan pruning. Tens of rows a day; cooldown.prune trims it nightly."""
from __future__ import annotations

import datetime as dt

import sqlalchemy as sa

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import alert_posts

ALERT_OUTCOMES = ("posted", "suppressed")


class AlertPostsRepository(Repository):
    def __init__(self):
        super().__init__(alert_posts, key="id")

    def add(self, ticker: str, at: dt.datetime, outcome: str, *, direction: str,
            horizon_key: str, plan_id: str | None, conn=None) -> None:
        if outcome not in ALERT_OUTCOMES:
            raise ValueError(f"unknown alert outcome {outcome!r}; expected one of {ALERT_OUTCOMES}")
        if at.tzinfo is None:
            raise ValueError("alert_posts.at needs a timezone-aware datetime")
        self.insert({"ticker": ticker, "at": at, "outcome": outcome, "direction": direction,
                     "horizon_key": horizon_key, "plan_id": plan_id}, conn=conn)

    def posted_since(self, ticker: str, direction: str, horizon_key: str,
                     since: dt.datetime, *, conn=None) -> bool:
        c = self.table.c
        statement = sa.select(c.id).where(
            c.outcome == "posted", c.ticker == ticker, c.at >= since,
            c.doc["direction"].astext == direction,
            c.doc["horizon_key"].astext == horizon_key,
        ).limit(1)
        with self._tx(conn) as connection:
            return connection.execute(statement).first() is not None

    def count_since(self, outcome: str, since: dt.datetime, *, conn=None) -> int:
        c = self.table.c
        return self.count(conn=conn, where=sa.and_(c.outcome == outcome, c.at >= since))

    def prune_before(self, cutoff: dt.datetime, *, conn=None) -> int:
        statement = sa.delete(self.table).where(self.table.c.at < cutoff)
        with self._tx(conn) as connection:
            return connection.execute(statement).rowcount


_repo: AlertPostsRepository | None = None


def alert_posts_repo() -> AlertPostsRepository:
    global _repo
    if _repo is None:
        _repo = AlertPostsRepository()
    return _repo
