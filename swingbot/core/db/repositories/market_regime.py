"""v239: the bear-regime engine's day store (market_regime_days).

Writer: core/scanning/regime_scan.regime_for_pass, once per session D. The
first pass that finds no row computes the day and calls `insert_once`:
INSERT ... ON CONFLICT (session_date) DO NOTHING RETURNING, and the notice is
enqueued in the same transaction only when a row came back -- so of two
racing processes exactly one row and at most one notice survive, and a notice
never outlives a rolled-back row. A row is never updated. Readers: the pass
(`day`, `recent`), the admin API (`day`, `recent`) and parity exports.
"""
from __future__ import annotations

import datetime as dt

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert

from swingbot.core.db.codec import sanitise_non_finite
from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.repositories.notify_queue import NotifyQueueRepository
from swingbot.core.db.schema import market_regime_days as days

#: Restated from core/market/bear_regime (STATES, ROW_COLUMNS) so the db layer
#: imports nothing from core/market; tests/regime/test_regime_pass.py pins them equal.
STATES = ("BEAR", "CORRECTION", "NORMAL", "UNKNOWN")
COLUMNS = ("session_date", "last_bar_date", "state", "stress", "pullback_trigger",
           "pullback_reason", "spy_close", "sma50", "sma200", "sma50_lag5", "sma200_lag20",
           "spy_high_prev", "vix_close", "vix_max5", "spy_provider", "vix_provider")
_DATES = ("session_date", "last_bar_date")


def _day(value) -> dt.date | None:
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    return value if isinstance(value, dt.date) else dt.date.fromisoformat(value)


def _instant(value) -> dt.datetime:
    if value is None:
        raise ValueError("computed_at_required")
    stamp = value if isinstance(value, dt.datetime) else dt.datetime.fromisoformat(value)
    if stamp.tzinfo is None:
        raise ValueError("timezone_required")
    return stamp


def _values(row: dict) -> dict:
    if row.get("state") not in STATES:
        raise ValueError(f"unknown regime state {row.get('state')!r}")
    values = {name: row.get(name) for name in COLUMNS}
    for name in _DATES:
        values[name] = _day(values[name])
    if values["session_date"] is None:
        raise ValueError("session_date_required")
    values.update(pullback_trigger=bool(values["pullback_trigger"]),
                  computed_at=_instant(row.get("computed_at")),
                  doc=sanitise_non_finite(dict(row.get("doc") or {})),
                  updated_at=sa.func.clock_timestamp())
    return values


def _read(row) -> dict:
    mapping = row._mapping
    return {**{name: mapping[name] for name in COLUMNS},
            "computed_at": mapping["computed_at"], "doc": dict(mapping["doc"] or {})}


class MarketRegimeRepository(Repository):
    def __init__(self):
        super().__init__(days, key="session_date")
        self._queue = NotifyQueueRepository()

    def insert_once(self, row: dict, *, notice_event: dict | None = None, conn=None) -> bool:
        """Insert the day unless the session already has one; enqueue only on a win."""
        values = _values(row)
        statement = (pg_insert(days).values(**values)
                     .on_conflict_do_nothing(index_elements=[days.c.session_date])
                     .returning(days.c.session_date))
        # Preserve row/notice atomicity if a caller catches an enqueue error.
        with self._tx(conn) as connection, connection.begin_nested():
            won = connection.execute(statement).scalar_one_or_none() is not None
            if won and notice_event is not None:
                self._queue.enqueue(notice_event, conn=connection)
        return won

    def day(self, session_date: dt.date, *, conn=None) -> dict | None:
        statement = sa.select(days).where(days.c.session_date == _day(session_date))
        with self._tx(conn) as connection:
            row = connection.execute(statement).one_or_none()
        return None if row is None else _read(row)

    def latest(self, *, before: dt.date | None = None, conn=None) -> dict | None:
        statement = sa.select(days).order_by(days.c.session_date.desc()).limit(1)
        if before is not None:
            statement = statement.where(days.c.session_date < _day(before))
        with self._tx(conn) as connection:
            row = connection.execute(statement).one_or_none()
        return None if row is None else _read(row)

    def recent(self, limit: int = 60, *, conn=None) -> list[dict]:
        """The newest `limit` rows, oldest first."""
        statement = sa.select(days).order_by(days.c.session_date.desc()).limit(int(limit))
        with self._tx(conn) as connection:
            rows = connection.execute(statement).all()
        return [_read(row) for row in reversed(rows)]


_repo: MarketRegimeRepository | None = None


def market_regime_repo() -> MarketRegimeRepository:
    global _repo
    if _repo is None:
        _repo = MarketRegimeRepository()
    return _repo
