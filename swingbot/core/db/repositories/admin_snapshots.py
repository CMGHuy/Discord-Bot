"""v204: stored admin snapshot payloads (`admin_snapshots`), one row per key.

Writer: the refresher's snapshot worker, and only it (`put`, `prune`).
Readers: the admin request door (`read`, `read_many`) and `/market/updates`
(`changed_since`, which reads the promoted columns without the payload).

Compare-and-set: `put` writes only when the row is absent or its stored
`computed_at` is strictly older. A build abandoned on a budget overrun may still
finish late; without this rule it would overwrite a newer snapshot. A rejected
put leaves `updated_at` untouched, so it is no change to `changed_since`.

`updated_at` is stamped with `clock_timestamp()` on every write, so a cursor read
inside one transaction still orders the writes. Keys are not validated here:
`core/db` imports nothing from `core/marketdata`; the worker and the door check
them with `is_snapshot_key`. The table raises no SSE event; the worker raises
`market` itself.
"""
from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert

from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.schema import admin_snapshots

_STAMP = sa.func.clock_timestamp()
_ROW_COLUMNS = ("key", "doc", "inputs", "computed_at", "stale_inputs", "updated_at")
_CHANGE_COLUMNS = ("key", "computed_at", "stale_inputs", "updated_at")


class AdminSnapshotRepository(Repository):
    def __init__(self) -> None:
        super().__init__(admin_snapshots, key="key")

    def _cols(self, names: tuple[str, ...]) -> list[sa.Column]:
        return [self.table.c[n] for n in names]

    def put(self, key: str, doc: dict, inputs: dict, *, computed_at: datetime,
            stale_inputs: bool, conn: sa.Connection | None = None) -> bool:
        """Write when the row is absent or older; True when a row was written."""
        if computed_at.tzinfo is None:
            raise ValueError("computed_at must be timezone-aware")
        json.dumps(doc, allow_nan=False)        # ValueError on NaN/Infinity: never store one
        json.dumps(inputs, allow_nan=False)
        t = self.table
        ins = pg_insert(t).values(key=key, doc=doc, inputs=inputs,
                                  computed_at=computed_at.astimezone(timezone.utc),
                                  stale_inputs=bool(stale_inputs), updated_at=_STAMP)
        stmt = ins.on_conflict_do_update(
            index_elements=[t.c.key],
            set_={"doc": ins.excluded.doc, "inputs": ins.excluded.inputs,
                  "computed_at": ins.excluded.computed_at,
                  "stale_inputs": ins.excluded.stale_inputs, "updated_at": _STAMP},
            where=t.c.computed_at < ins.excluded.computed_at,
        ).returning(t.c.key)
        with self._tx(conn) as c:
            return c.execute(stmt).first() is not None

    def read(self, key: str, *, conn: sa.Connection | None = None) -> dict | None:
        stmt = sa.select(*self._cols(_ROW_COLUMNS)).where(self.table.c.key == key)
        with self._tx(conn) as c:
            row = c.execute(stmt).mappings().first()
        return dict(row) if row is not None else None

    def read_many(self, keys: Iterable[str], *,
                  conn: sa.Connection | None = None) -> dict[str, dict]:
        wanted = list(keys)
        if not wanted:
            return {}
        stmt = sa.select(*self._cols(_ROW_COLUMNS)).where(self.table.c.key.in_(wanted))
        with self._tx(conn) as c:
            return {r["key"]: dict(r) for r in c.execute(stmt).mappings()}

    def changed_since(self, since: datetime, *,
                      conn: sa.Connection | None = None) -> list[dict]:
        t = self.table
        stmt = (sa.select(*self._cols(_CHANGE_COLUMNS))
                .where(t.c.updated_at > since).order_by(t.c.updated_at))
        with self._tx(conn) as c:
            return [dict(r) for r in c.execute(stmt).mappings()]

    def prune(self, prefix: str, keep: Iterable[str], *,
              conn: sa.Connection | None = None) -> int:
        """Delete rows whose key starts with `prefix` and is not in `keep`."""
        t = self.table
        kept = list(keep)
        stmt = sa.delete(t).where(t.c.key.startswith(prefix, autoescape=True))
        if kept:
            stmt = stmt.where(t.c.key.not_in(kept))
        with self._tx(conn) as c:
            return c.execute(stmt).rowcount


_repo: AdminSnapshotRepository | None = None


def admin_snapshot_repo() -> AdminSnapshotRepository:
    global _repo
    if _repo is None:
        _repo = AdminSnapshotRepository()
    return _repo
