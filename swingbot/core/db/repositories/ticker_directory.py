"""The NASDAQ/NYSE symbol directory. Regenerable, so reads may fall back."""
from __future__ import annotations

import sqlalchemy as sa

from swingbot.core.db.engine import transaction
from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import ticker_directory


class TickerDirectoryRepository(Repository):
    def __init__(self):
        super().__init__(ticker_directory, key="symbol")

    def replace(self, rows: list[dict], *, conn=None) -> None:
        """Swap the whole directory in one transaction.

        A weekly refresh drops delisted symbols, so this is a replace rather
        than an upsert sweep -- and it is one transaction so a concurrent
        lookup never sees an empty directory.
        """
        with transaction(conn) as c:
            c.execute(sa.delete(ticker_directory))
            for row in rows:
                self.insert(row, conn=c)

    def all_rows(self, *, conn=None) -> list[dict]:
        return self.list_all(conn=conn, order_by=ticker_directory.c.symbol.asc())

    def loaded_at(self, *, conn=None) -> float:
        """Newest updated_at as a unix timestamp, or 0.0 when empty --
        the shape _ensure_loaded's staleness check already expects."""
        stmt = sa.select(sa.func.max(ticker_directory.c.updated_at))
        with self._tx(conn) as c:
            newest = c.execute(stmt).scalar_one_or_none()
        return newest.timestamp() if newest is not None else 0.0

    def search(self, query: str, limit: int = 15, *, conn=None) -> list[dict]:
        """Symbol-prefix matches first, then a substring of symbol or name --
        the ordering the in-memory search_tickers() produces."""
        q = (query or "").strip()
        if not q:
            return []
        pattern = f"{q}%"
        contains = f"%{q}%"
        return self.list_all(
            conn=conn,
            where=sa.or_(ticker_directory.c.symbol.ilike(contains),
                         ticker_directory.c.name.ilike(contains)),
            order_by=(sa.case((ticker_directory.c.symbol.ilike(pattern), 0),
                              else_=1),
                      ticker_directory.c.symbol.asc()),
            limit=limit,
        )


_repo: TickerDirectoryRepository | None = None


def ticker_directory_repo() -> TickerDirectoryRepository:
    global _repo
    if _repo is None:
        _repo = TickerDirectoryRepository()
    return _repo
