"""v152 D1: the notify channel's one-message-per-(plan, event) claim.

A claim is inserted `pending` before the send (ON CONFLICT DO NOTHING: zero
rows = someone already claimed it), set `sent` only after Discord accepted
the message, and counted up by `record_failure` until MAX_ATTEMPTS makes it
`failed`. The attempts counter lives in `doc` and is bumped in SQL, so a
retry never reads-modifies-writes. Retries depend on this table alone."""
from __future__ import annotations

import datetime as dt

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import plan_notifications

MAX_ATTEMPTS = 5
STATES = ("pending", "sent", "failed")


class NotificationsRepository(Repository):
    def __init__(self):
        super().__init__(plan_notifications, key="id")

    def _key(self, plan_id: str, event: str):
        c = self.table.c
        return sa.and_(c.plan_id == plan_id, c.event == event)

    def claim(self, plan_id: str, event: str, doc: dict, *, conn=None) -> bool:
        record = {**doc, "plan_id": plan_id, "event": event, "state": "pending",
                  "attempts": 0}
        statement = (pg_insert(self.table).values(**self._values(record))
                     .on_conflict_do_nothing(constraint="plan_notifications_claim_uq")
                     .returning(self.table.c.id))
        with self._tx(conn) as connection:
            # RETURNING yields a row only for an actual insert (rowcount is not
            # reliable when SQLAlchemy returns the primary key itself).
            return connection.execute(statement).first() is not None

    def mark_sent(self, plan_id: str, event: str, *, conn=None) -> None:
        statement = (sa.update(self.table).where(self._key(plan_id, event))
                     .values(state="sent", updated_at=sa.func.clock_timestamp()))
        with self._tx(conn) as connection:
            connection.execute(statement)

    def record_failure(self, plan_id: str, event: str, *, max_attempts: int = MAX_ATTEMPTS,
                       conn=None) -> str:
        c = self.table.c
        attempts = sa.func.coalesce(c.doc["attempts"].astext.cast(sa.Integer), 0) + 1
        bumped = sa.func.jsonb_build_object(sa.cast(sa.literal("attempts"), sa.Text), attempts)
        statement = (
            sa.update(self.table)
            .where(self._key(plan_id, event), c.state == "pending")
            .values(doc=c.doc.op("||")(bumped),
                    state=sa.case((attempts >= max_attempts, "failed"), else_="pending"),
                    updated_at=sa.func.clock_timestamp())
            .returning(c.state)
        )
        with self._tx(conn) as connection:
            state = connection.execute(statement).scalar_one_or_none()
        return "failed" if state is None else state

    def pending_older_than(self, cutoff: dt.datetime, *, conn=None) -> list[dict]:
        c = self.table.c
        return self.list_all(conn=conn, where=sa.and_(c.state == "pending", c.updated_at < cutoff),
                             order_by=c.updated_at)

    def claimed_keys(self, *, conn=None) -> set[tuple[str, str]]:
        c = self.table.c
        with self._tx(conn) as connection:
            return {(plan_id, event) for plan_id, event
                    in connection.execute(sa.select(c.plan_id, c.event)).all()}


_repo: NotificationsRepository | None = None


def notifications_repo() -> NotificationsRepository:
    global _repo
    if _repo is None:
        _repo = NotificationsRepository()
    return _repo
