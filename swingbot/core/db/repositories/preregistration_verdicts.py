"""v173: frozen pre-registration verdicts (`preregistration_verdicts`).

Writer: analytics/override_io.run_daily_check (`insert_once`, the only write,
inside the transaction that checked no row exists). Readers: override_io
(`recorded`), and through it the report script and the admin API. A verdict is
never updated or deleted: `upsert`/`insert` are refused, and a second insert on
the same ledger_id writes nothing (the primary key is the idempotency authority).
The table raises no SSE event.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy.dialects.postgresql import insert as pg_insert

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import preregistration_verdicts

_WRITE_ONCE = "a verdict is written once: use insert_once"


def _recorded_on(value) -> dt.date:
    """A date from a date or a strict YYYY-MM-DD string; anything else is refused."""
    if isinstance(value, dt.date) and not isinstance(value, dt.datetime):
        return value
    if isinstance(value, str):
        try:
            parsed = dt.date.fromisoformat(value)
        except ValueError:
            parsed = None
        if parsed is not None and parsed.isoformat() == value:
            return parsed
    raise ValueError("recorded_on must be a date or YYYY-MM-DD")


def _prepared(record: dict) -> dict:
    """`record` checked for a write, with `recorded_on` as a date."""
    if not record.get("ledger_id") or not record.get("verdict"):
        raise ValueError("a verdict record needs a ledger_id and a verdict")
    return {**record, "recorded_on": _recorded_on(record.get("recorded_on"))}


class PreregistrationVerdictRepository(Repository):
    def __init__(self):
        super().__init__(preregistration_verdicts, key="ledger_id")

    def insert_once(self, record: dict, *, conn=None) -> bool:
        """Write `record` unless its ledger_id already has a row; True when written."""
        statement = (pg_insert(self.table).values(**self._values(_prepared(record)))
                     .on_conflict_do_nothing(index_elements=["ledger_id"])
                     .returning(self.table.c.ledger_id))
        with self._tx(conn) as connection:
            inserted = connection.execute(statement).first()
        return inserted is not None

    def recorded(self, ledger_id: str, *, conn=None) -> dict | None:
        """The stored record, recorded_on as ISO text; None when absent."""
        record = self.get(ledger_id, conn=conn)
        if record is None:
            return None
        return {**record, "recorded_on": record["recorded_on"].isoformat()}

    def upsert(self, record: dict, *, conn=None) -> dict:
        raise TypeError(_WRITE_ONCE)

    def insert(self, record: dict, *, conn=None) -> dict:
        raise TypeError(_WRITE_ONCE)


_repo: PreregistrationVerdictRepository | None = None


def verdict_repo() -> PreregistrationVerdictRepository:
    global _repo
    if _repo is None:
        _repo = PreregistrationVerdictRepository()
    return _repo
