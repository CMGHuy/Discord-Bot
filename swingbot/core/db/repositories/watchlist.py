"""The scanned ticker universe."""
from __future__ import annotations

import datetime as dt

import sqlalchemy as sa

from swingbot.core.db.engine import transaction
from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import watchlist


class WatchlistRepository(Repository):
    def __init__(self):
        super().__init__(watchlist, key="ticker")

    def tickers(self, *, conn=None) -> list[str]:
        return sorted(row["ticker"] for row in self.list_all(conn=conn))

    def add(self, ticker: str, *, conn=None) -> list[str]:
        self.upsert({"ticker": ticker.upper(), "added_at": dt.datetime.now(dt.timezone.utc)}, conn=conn)
        return self.tickers(conn=conn)

    def remove(self, ticker: str, *, conn=None) -> list[str]:
        self.delete(ticker.upper(), conn=conn)
        return self.tickers(conn=conn)

    def replace(self, tickers: list[str], *, conn=None) -> list[str]:
        with transaction(conn) as connection:
            self.clear(conn=connection)
            for ticker in sorted(set(t.upper() for t in tickers)):
                self.add(ticker, conn=connection)
            return self.tickers(conn=connection)

    def clear(self, *, conn=None) -> list[str]:
        with self._tx(conn) as connection:
            connection.execute(sa.delete(watchlist))
        return []


_repo: WatchlistRepository | None = None


def watchlist_repo() -> WatchlistRepository:
    global _repo
    if _repo is None:
        _repo = WatchlistRepository()
    return _repo
