"""Live TradePlanV2 lifecycle queries."""
from __future__ import annotations

import sqlalchemy as sa

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import plans


class PlanRepository(Repository):
    def __init__(self):
        super().__init__(plans, key="plan_id")

    @property
    def OPEN_STATUSES(self) -> tuple[str, ...]:
        """Use PlanStore's canonical open-status definition."""
        from swingbot.core.planning.plan_store import _OPEN_STATUSES
        return tuple(_OPEN_STATUSES)

    def open_plans(self, *, conn=None) -> list[dict]:
        return self.list_all(conn=conn, where=plans.c.status.in_(self.OPEN_STATUSES),
                             order_by=plans.c.created_at.desc())

    def by_ticker(self, ticker: str, *, conn=None) -> list[dict]:
        return self.list_all(conn=conn,
                             where=sa.func.upper(plans.c.ticker) == (ticker or "").upper(),
                             order_by=plans.c.created_at.desc())

    def for_session(self, valid_session: str, *, conn=None) -> list[dict]:
        """v144: every plan whose valid_session is this ISO date, oldest first."""
        return self.list_all(conn=conn, where=plans.c.valid_session == valid_session,
                             order_by=plans.c.created_at.asc())

    def version(self, *, conn=None) -> tuple[int, str | None]:
        """(row count, newest updated_at) -- moves on any insert, update or delete."""
        statement = sa.select(sa.func.count(), sa.func.max(plans.c.updated_at))
        with self._tx(conn) as connection:
            count, newest = connection.execute(statement).one()
        return int(count), None if newest is None else newest.isoformat()


_repo: PlanRepository | None = None


def plans_repo() -> PlanRepository:
    global _repo
    if _repo is None:
        _repo = PlanRepository()
    return _repo
