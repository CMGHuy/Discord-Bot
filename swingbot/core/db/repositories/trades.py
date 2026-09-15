"""Trade-specific queries used by the future database-backed TradeLog."""
from __future__ import annotations

import sqlalchemy as sa

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import trades

OPEN_STATUS = "open"


class TradeRepository(Repository):
    """Queries over trades that retain the existing TradeLog semantics."""

    def __init__(self):
        super().__init__(trades, key="trade_id")

    def open_trades(self, *, conn=None) -> list[dict]:
        return self.list_all(conn=conn, where=trades.c.status == OPEN_STATUS,
                             order_by=trades.c.opened_at.desc())

    def closed_trades(self, *, conn=None, limit: int | None = None) -> list[dict]:
        return self.list_all(conn=conn, where=trades.c.status != OPEN_STATUS,
                             order_by=trades.c.closed_at.desc(), limit=limit)

    def by_ticker(self, ticker: str, *, conn=None) -> list[dict]:
        return self.list_all(
            conn=conn,
            where=sa.func.upper(trades.c.ticker) == (ticker or "").upper(),
            order_by=trades.c.opened_at.desc(),
        )

    def open_for_ticker(self, ticker: str, *, conn=None) -> dict | None:
        rows = self.list_all(
            conn=conn,
            where=sa.and_(sa.func.upper(trades.c.ticker) == (ticker or "").upper(),
                          trades.c.status == OPEN_STATUS),
            order_by=trades.c.opened_at.desc(), limit=1,
        )
        return rows[0] if rows else None

    def has_open(self, ticker: str, strategy: str, horizon: str,
                 direction: str, *, conn=None) -> bool:
        return self.count(conn=conn, where=sa.and_(
            sa.func.upper(trades.c.ticker) == (ticker or "").upper(),
            trades.c.strategy == strategy,
            trades.c.horizon == horizon,
            trades.c.direction == direction,
            trades.c.status == OPEN_STATUS,
        )) > 0

    def by_plan_id(self, plan_id: str, *, conn=None) -> dict | None:
        rows = self.list_all(conn=conn,
                             where=trades.c.doc["plan_id"].astext == plan_id,
                             limit=1)
        return rows[0] if rows else None

    def clear(self, *, status: str | None = None, conn=None) -> int:
        statement = sa.delete(trades)
        if status == "open":
            statement = statement.where(trades.c.status == OPEN_STATUS)
        elif status == "closed":
            statement = statement.where(trades.c.status != OPEN_STATUS)
        with self._tx(conn) as connection:
            return connection.execute(statement).rowcount


_repo: TradeRepository | None = None


def trades_repo() -> TradeRepository:
    """Return the process-local repository singleton."""
    global _repo
    if _repo is None:
        _repo = TradeRepository()
    return _repo
