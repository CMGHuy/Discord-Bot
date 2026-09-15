"""Generic PostgreSQL repository with safe partial JSON-document updates."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, insert as pg_insert

from swingbot.core.db.codec import merge_doc, split_doc
from swingbot.core.db.engine import get_engine
from swingbot.core.db.schema import promoted_for


class Repository:
    """CRUD over one hybrid-schema table, with flat dicts at its boundary."""

    def __init__(self, table: sa.Table, key: str):
        if key not in table.c:
            raise ValueError(f"{table.name}: {key!r} is not a table column")
        self.table = table
        self.key = key
        self.promoted = promoted_for(table.name)
        self.key_col = table.c[key]

    @contextmanager
    def _tx(self, conn: sa.Connection | None) -> Iterator[sa.Connection]:
        if conn is not None:
            yield conn
            return
        with get_engine().begin() as owned:
            yield owned

    def _record(self, row) -> dict:
        return merge_doc(row._mapping, self.promoted)

    def _values(self, record: dict) -> dict:
        columns, document = split_doc(record, self.promoted)
        return {**columns, "doc": document}

    def get(self, key_value: Any, *, conn: sa.Connection | None = None) -> dict | None:
        statement = sa.select(self.table).where(self.key_col == key_value)
        with self._tx(conn) as connection:
            row = connection.execute(statement).one_or_none()
        return None if row is None else self._record(row)

    def list_all(self, *, conn: sa.Connection | None = None, where=None,
                 order_by=None, limit: int | None = None) -> list[dict]:
        statement = sa.select(self.table)
        if where is not None:
            statement = statement.where(where)
        if order_by is not None:
            statement = statement.order_by(order_by)
        if limit is not None:
            statement = statement.limit(limit)
        with self._tx(conn) as connection:
            rows = connection.execute(statement).all()
        return [self._record(row) for row in rows]

    def count(self, *, conn: sa.Connection | None = None, where=None) -> int:
        statement = sa.select(sa.func.count()).select_from(self.table)
        if where is not None:
            statement = statement.where(where)
        with self._tx(conn) as connection:
            return int(connection.execute(statement).scalar_one())

    def insert(self, record: dict, *, conn: sa.Connection | None = None) -> dict:
        statement = sa.insert(self.table).values(**self._values(record)).returning(self.table)
        with self._tx(conn) as connection:
            row = connection.execute(statement).one()
        return self._record(row)

    def upsert(self, record: dict, *, conn: sa.Connection | None = None) -> dict:
        values = self._values(record)
        statement = pg_insert(self.table).values(**values)
        updates = {name: value for name, value in values.items() if name != self.key}
        updates["updated_at"] = sa.func.clock_timestamp()
        statement = statement.on_conflict_do_update(
            index_elements=[self.key_col], set_=updates
        ).returning(self.table)
        with self._tx(conn) as connection:
            row = connection.execute(statement).one()
        return self._record(row)

    def patch(self, key_value: Any, changes: dict, *,
              conn: sa.Connection | None = None) -> dict | None:
        """Patch named fields only, composing JSONB changes in the database."""
        columns, document_patch = split_doc(changes, self.promoted)
        values: dict[str, Any] = {**columns, "updated_at": sa.func.clock_timestamp()}
        if document_patch:
            values["doc"] = self.table.c.doc.op("||")(
                sa.cast(sa.literal(document_patch, type_=sa.JSON), JSONB)
            )
        statement = (sa.update(self.table).where(self.key_col == key_value)
                     .values(**values).returning(self.table))
        with self._tx(conn) as connection:
            row = connection.execute(statement).one_or_none()
        return None if row is None else self._record(row)

    def delete(self, key_value: Any, *, conn: sa.Connection | None = None) -> bool:
        statement = sa.delete(self.table).where(self.key_col == key_value)
        with self._tx(conn) as connection:
            return connection.execute(statement).rowcount > 0
