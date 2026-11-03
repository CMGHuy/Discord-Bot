"""v201: the refresher's four stores -- quote currencies, the refresh queue,
in-flight marks and the heartbeat.

Writers: the refresher process writes currencies, marks and the heartbeat;
the request door (admin API) writes the queue, the refresher takes from it.
None of the tables raises an SSE event. Every ``updated_at`` is
``clock_timestamp()`` so a cursor read from it orders writes even inside one
transaction. Times are tz-aware UTC.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import (market_refresh_marks, market_refresh_queue,
                                     quote_currencies, refresher_heartbeat)

#: Restated so core/db imports nothing from core/marketdata (V201-5 pins equality).
HEARTBEAT_KEY = "refresher"
_STAMP = sa.func.clock_timestamp()


class QuoteCurrencyRepository(Repository):
    def __init__(self):
        super().__init__(quote_currencies, key="symbol")

    def put(self, symbol: str, code: str | None, outcome: str, *, checked_at: datetime,
            retry_after: datetime | None = None, conn=None) -> None:
        values = {"symbol": symbol.upper(), "code": code, "outcome": outcome,
                  "checked_at": checked_at, "retry_after": retry_after, "updated_at": _STAMP}
        ins = pg_insert(self.table).values(**values)
        stmt = ins.on_conflict_do_update(
            index_elements=[self.table.c.symbol],
            set_={k: v for k, v in values.items() if k != "symbol"})
        with self._tx(conn) as c:
            c.execute(stmt)

    def get_many(self, symbols, *, conn=None) -> dict[str, dict]:
        t = self.table
        wanted = [s.upper() for s in symbols]
        stmt = sa.select(t.c.symbol, t.c.code, t.c.outcome, t.c.checked_at,
                         t.c.retry_after).where(t.c.symbol.in_(wanted))
        with self._tx(conn) as c:
            return {r.symbol: dict(r._mapping) for r in c.execute(stmt)}

    def due(self, symbols, now: datetime, *, conn=None) -> list[str]:
        """Symbols (upper-cased, input order) with no row or an unknown past its backoff."""
        wanted = list(dict.fromkeys(s.upper() for s in symbols))
        t = self.table
        stmt = sa.select(t.c.symbol).where(
            t.c.symbol.in_(wanted),
            sa.not_(sa.and_(t.c.outcome == "unknown", t.c.retry_after <= now)))
        with self._tx(conn) as c:
            settled = {r.symbol for r in c.execute(stmt)}
        return [s for s in wanted if s not in settled]


class RefreshQueueRepository(Repository):
    def __init__(self):
        super().__init__(market_refresh_queue, key="id")

    def enqueue(self, kind: str, keys, *, priority: int, conn=None) -> int:
        """Rows inserted. A pending (kind, key) is kept; a lower priority number replaces its own."""
        keys = list(dict.fromkeys(keys))
        if not keys:
            return 0
        t = self.table
        ins = pg_insert(t).values([{"kind": kind, "key": k, "priority": int(priority),
                                    "updated_at": _STAMP} for k in keys])
        stmt = ins.on_conflict_do_update(
            index_elements=[t.c.kind, t.c.key], index_where=t.c.taken_at.is_(None),
            set_={"priority": sa.func.least(t.c.priority, ins.excluded.priority),
                  "updated_at": _STAMP},
        ).returning(sa.literal_column("(xmax = 0)").label("inserted"))
        with self._tx(conn) as c:
            return sum(1 for row in c.execute(stmt) if row.inserted)

    def take(self, limit: int, *, conn=None) -> list[dict]:
        t = self.table
        pick = (sa.select(t.c.id).where(t.c.taken_at.is_(None))
                .order_by(t.c.priority, t.c.requested_at).limit(int(limit))
                .with_for_update(skip_locked=True))
        stmt = (sa.update(t).where(t.c.id.in_(pick.scalar_subquery()))
                .values(taken_at=_STAMP, updated_at=_STAMP)
                .returning(t.c.kind, t.c.key, t.c.priority, t.c.requested_at, t.c.id))
        with self._tx(conn) as c:
            rows = sorted(c.execute(stmt), key=lambda r: (r.priority, r.requested_at, r.id))
        return [{"kind": r.kind, "key": r.key, "priority": int(r.priority)} for r in rows]

    def prune(self, older_than: datetime, *, conn=None) -> int:
        stmt = sa.delete(self.table).where(self.table.c.requested_at < older_than)
        with self._tx(conn) as c:
            return c.execute(stmt).rowcount


class RefreshMarkRepository(Repository):
    def __init__(self):
        super().__init__(market_refresh_marks, key="key")

    def _upsert(self, keys, values: dict, *, conn) -> None:
        keys = list(dict.fromkeys(keys))
        if not keys:
            return
        ins = pg_insert(self.table).values([{"key": k, **values, "updated_at": _STAMP}
                                            for k in keys])
        stmt = ins.on_conflict_do_update(
            index_elements=[self.table.c.key],
            set_={**{k: getattr(ins.excluded, k) for k in values}, "updated_at": _STAMP})
        with self._tx(conn) as c:
            c.execute(stmt)

    def mark(self, keys, *, timeout_s: float, now: datetime, conn=None) -> None:
        self._upsert(keys, {"started_at": now, "expires_at": now + timedelta(seconds=timeout_s),
                            "error": None, "error_at": None}, conn=conn)

    def clear(self, keys, *, error: str | None = None, now: datetime, conn=None) -> None:
        self._upsert(keys, {"started_at": now, "expires_at": now, "error": error,
                            "error_at": now if error else None}, conn=conn)

    def active(self, keys, *, now: datetime, conn=None) -> set[str]:
        t = self.table
        stmt = sa.select(t.c.key).where(t.c.key.in_(list(keys)), t.c.expires_at > now)
        with self._tx(conn) as c:
            return {r.key for r in c.execute(stmt)}

    def errors(self, keys, *, conn=None) -> dict[str, str]:
        t = self.table
        stmt = sa.select(t.c.key, t.c.error).where(t.c.key.in_(list(keys)),
                                                   t.c.error.is_not(None))
        with self._tx(conn) as c:
            return {r.key: r.error for r in c.execute(stmt)}

    def changed_since(self, since: datetime, *, now: datetime | None = None,
                      conn=None) -> list[dict]:
        t = self.table
        stamp = sa.func.now() if now is None else now
        stmt = (sa.select(t.c.key, (t.c.expires_at > stamp).label("in_flight"),
                          t.c.error, t.c.updated_at)
                .where(t.c.updated_at > since).order_by(t.c.updated_at))
        with self._tx(conn) as c:
            return [dict(r._mapping) for r in c.execute(stmt)]


class RefresherHeartbeatRepository(Repository):
    def __init__(self):
        super().__init__(refresher_heartbeat, key="key")

    def beat(self, *, cadence_s: float, session: str, cycle_ms: int | None,
             last_error: str | None, now: datetime, conn=None) -> None:
        values = {"beat_at": now, "cadence_s": float(cadence_s), "session": session,
                  "cycle_ms": cycle_ms, "last_error": last_error, "updated_at": _STAMP}
        ins = pg_insert(self.table).values(key=HEARTBEAT_KEY, **values)
        stmt = ins.on_conflict_do_update(index_elements=[self.table.c.key], set_=values)
        with self._tx(conn) as c:
            c.execute(stmt)

    def read(self, *, conn=None) -> dict | None:
        t = self.table
        stmt = sa.select(t.c.beat_at, t.c.cadence_s, t.c.session, t.c.cycle_ms,
                         t.c.last_error).where(t.c.key == HEARTBEAT_KEY)
        with self._tx(conn) as c:
            row = c.execute(stmt).first()
        return None if row is None else dict(row._mapping)


_repos: dict[str, Repository] = {}


def _singleton(cls):
    if cls.__name__ not in _repos:
        _repos[cls.__name__] = cls()
    return _repos[cls.__name__]


def quote_currency_repo() -> QuoteCurrencyRepository:
    return _singleton(QuoteCurrencyRepository)


def refresh_queue_repo() -> RefreshQueueRepository:
    return _singleton(RefreshQueueRepository)


def refresh_mark_repo() -> RefreshMarkRepository:
    return _singleton(RefreshMarkRepository)


def refresher_heartbeat_repo() -> RefresherHeartbeatRepository:
    return _singleton(RefresherHeartbeatRepository)
