"""v147: the append-only live gate-counterfactual store (`gate_rejections`).

Writer: `scanning.rejection_recorder.record_rejection` (`insert_ignore`; fail-open there).
Resolver: `backtesting.gate_resolver.resolve_due` (`pending` -> `resolve`, once).
Report and progress cron: `list_since`. The table raises no SSE event.
"""
from __future__ import annotations

import datetime as dt

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, insert as pg_insert

from swingbot.core.db.codec import split_doc
from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import gate_rejections

#: gate_counterfactual.CF_STATUSES, restated so the db layer never imports backtesting (pinned by a test).
CF_STATUSES = ("pending", "filled", "no-fill", "no-plan", "no-data")
KEY_CONSTRAINT = "gate_rejections_key_uq"


def _check_status(status) -> None:
    if status not in CF_STATUSES:
        raise ValueError(f"cf_status {status!r} is not one of {CF_STATUSES}")


def _as_utc(value) -> dt.datetime | None:
    """A timestamptz bound from a datetime or ISO string; a naive value is taken as UTC."""
    if value is None:
        return None
    stamp = value if isinstance(value, dt.datetime) else dt.datetime.fromisoformat(str(value))
    return stamp if stamp.tzinfo is not None else stamp.replace(tzinfo=dt.timezone.utc)


class GateRejectionRepository(Repository):
    def __init__(self):
        super().__init__(gate_rejections, key="id")

    def _with_id(self, row) -> dict:
        return {**self._record(row), "id": row.id}

    def insert_ignore(self, record: dict, *, conn=None) -> bool:
        """Insert one rejection; False, and nothing written, when its dedupe key already exists."""
        _check_status(record.get("cf_status"))
        statement = (pg_insert(self.table).values(**self._values(record))
                     .on_conflict_do_nothing(constraint=KEY_CONSTRAINT)
                     .returning(self.table.c.id))
        with self._tx(conn) as connection:
            return connection.execute(statement).first() is not None

    def pending(self, *, limit: int, conn=None) -> list[dict]:
        """Up to `limit` pending rows, oldest first, each with its `id`."""
        statement = (sa.select(self.table).where(self.table.c.cf_status == "pending")
                     .order_by(self.table.c.created_at, self.table.c.id).limit(limit))
        with self._tx(conn) as connection:
            rows = connection.execute(statement).all()
        return [self._with_id(row) for row in rows]

    def resolve(self, row_id: int, *, cf_status: str, resolved_at, outcome: dict, conn=None) -> bool:
        """Write one pending row's status and merge `outcome` into its doc -- only while it is pending,
        so a resolved row is never resolved again (False). `cf_status="pending"` with
        `resolved_at=None` is the grace-counter bump. `outcome` may not name a promoted column."""
        _check_status(cf_status)
        columns, document = split_doc(outcome, self.promoted)
        if columns:
            raise ValueError(f"outcome may not set promoted columns: {sorted(columns)}")
        values = {"cf_status": cf_status, "resolved_at": _as_utc(resolved_at),
                  "updated_at": sa.func.clock_timestamp()}
        if document:
            values["doc"] = self.table.c.doc.op("||")(sa.cast(sa.literal(document, type_=sa.JSON), JSONB))
        statement = (sa.update(self.table)
                     .where(self.table.c.id == row_id, self.table.c.cf_status == "pending")
                     .values(**values))
        with self._tx(conn) as connection:
            return connection.execute(statement).rowcount > 0

    def list_since(self, since: str | None = None, *, conn=None) -> list[dict]:
        """Every row created at or after `since` (ISO date or timestamp; None = all), oldest first."""
        statement = sa.select(self.table).order_by(self.table.c.created_at, self.table.c.id)
        if since is not None:
            statement = statement.where(self.table.c.created_at >= _as_utc(since))
        with self._tx(conn) as connection:
            rows = connection.execute(statement).all()
        return [self._with_id(row) for row in rows]


_repo: GateRejectionRepository | None = None


def gate_rejections_repo() -> GateRejectionRepository:
    global _repo
    if _repo is None:
        _repo = GateRejectionRepository()
    return _repo
