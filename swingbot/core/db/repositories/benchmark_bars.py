"""Benchmark session bars and refresh marks.

The refresher's benchmarks step (swingbot/refresher/benchmarks.py) writes both
tables, and admin/api_v1/benchmark.py reads the bars. Writes emit no SSE event
and stamp updated_at with clock_timestamp().
"""
from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timezone

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import benchmark_bars, benchmark_refresh

BAR_KEYS = ("symbol", "session", "close", "adj_close", "day_pct", "source_symbol", "final", "as_of")
_LEVELS = ("close", "adj_close", "day_pct")


def _as_date(value) -> date:
    if isinstance(value, str):
        return date.fromisoformat(value)
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    raise ValueError("session must be a date or an ISO date string")


def _as_utc(value) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError("as_of must be a timezone-aware datetime")
    return value.astimezone(timezone.utc)


def _prepared(row: dict) -> dict:
    for key in ("symbol", "source_symbol"):
        value = row.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{key} must be a non-empty string")
    if not isinstance(row.get("final"), bool):
        raise ValueError("final must be a bool")
    return {
        **row,
        **{key: row.get(key) for key in _LEVELS},
        "session": _as_date(row.get("session")),
        "as_of": _as_utc(row.get("as_of")),
    }


def _replace_statement(table: sa.Table, values: list[dict], keys: tuple[str, ...]):
    stamp = sa.func.clock_timestamp()
    statement = pg_insert(table).values([{**row, "updated_at": stamp} for row in values])
    updates = {name: statement.excluded[name] for name in values[0] if name not in keys}
    return statement.on_conflict_do_update(index_elements=keys, set_={**updates, "updated_at": stamp})


class BenchmarkBarRepository(Repository):
    """Store one benchmark bar per symbol and NYSE session."""

    def __init__(self):
        super().__init__(benchmark_bars, key="session")

    def _bar(self, row) -> dict:
        bar = {**self._record(row), **{key: row._mapping[key] for key in BAR_KEYS}}
        bar["as_of"] = _as_utc(bar["as_of"])
        bar["updated_at"] = _as_utc(row._mapping["updated_at"])
        return bar

    def upsert_bars(self, rows: list[dict], conn=None) -> int:
        if not rows:
            return 0
        deduped = {}
        for row in rows:
            prepared = _prepared(row)
            deduped[prepared["symbol"], prepared["session"]] = prepared
        values = [self._values(row) for row in deduped.values()]
        statement = _replace_statement(self.table, values, ("symbol", "session"))
        with self._tx(conn) as connection:
            connection.execute(statement)
        return len(values)

    def upsert(self, record: dict, *, conn=None) -> dict:
        with self._tx(conn) as connection:
            self.upsert_bars([record], conn=connection)
            session = _as_date(record["session"])
            (stored,) = self.list_range([record["symbol"]], session, session, conn=connection)
        return stored

    def list_range(self, symbols: Sequence[str], start: date, end: date, conn=None) -> list[dict]:
        if not symbols:
            return []
        table = self.table
        statement = (sa.select(table)
                     .where(table.c.symbol.in_(symbols), table.c.session.between(start, end))
                     .order_by(table.c.symbol, table.c.session))
        with self._tx(conn) as connection:
            return [self._bar(row) for row in connection.execute(statement)]

    def last_session(self, symbol: str, conn=None) -> date | None:
        table = self.table
        statement = sa.select(sa.func.max(table.c.session)).where(
            table.c.symbol == symbol, table.c.final.is_(True))
        with self._tx(conn) as connection:
            return connection.execute(statement).scalar_one()


class BenchmarkRefreshRepository(Repository):
    """Record the most recent full-refresh day for each benchmark."""

    def __init__(self):
        super().__init__(benchmark_refresh, key="symbol")

    def upsert(self, record: dict, *, conn=None) -> dict:
        values = self._values(record)
        statement = _replace_statement(self.table, [values], (self.key,)).returning(self.table)
        with self._tx(conn) as connection:
            return self._record(connection.execute(statement).one())

    def full_refreshed_on(self, symbol: str, conn=None) -> date | None:
        record = self.get(symbol, conn=conn)
        return None if record is None else record["full_refreshed_on"]

    def mark_full_refresh(self, symbol: str, day: date, conn=None) -> None:
        self.upsert({"symbol": symbol, "full_refreshed_on": day}, conn=conn)


_bars_repo = BenchmarkBarRepository()
_refresh_repo = BenchmarkRefreshRepository()


def benchmark_bars_repo() -> BenchmarkBarRepository:
    return _bars_repo


def benchmark_refresh_repo() -> BenchmarkRefreshRepository:
    return _refresh_repo
