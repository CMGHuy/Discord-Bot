"""Rename and drop a `doc` field inside an Alembic data revision (v116 Phase 2).

    from swingbot.core.db.doc_fields import drop_doc_field, rename_doc_field, restore_doc_field

    def upgrade():   rename_doc_field("trades", "tp1_hit", "target1_hit")
    def downgrade(): rename_doc_field("trades", "target1_hit", "tp1_hit")

    def upgrade():   drop_doc_field("plans", "legacy_score")
    def downgrade(): restore_doc_field("plans", "legacy_score")

A shape change is applied once, by a revision: nothing upcasts at read time,
so there is one code path per field (docs/claude/schema-evolution.md).
Promoted columns are not doc fields; changing one is a normal DDL revision.
"""
from __future__ import annotations

import re

import sqlalchemy as sa

SIDE_TABLE = "dropped_doc_fields"
_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")


class DocFieldConflict(RuntimeError):
    """A rename would overwrite a value already stored under the new name."""


def _table(name: str) -> str:
    if not _IDENT.match(name or ""):
        raise ValueError(f"{name!r} is not a plain lowercase SQL identifier; "
                         "it is interpolated into SQL")
    return name


def _bind(conn):
    if conn is not None:
        return conn
    from alembic import op
    return op.get_bind()


def rename_doc_field(table: str, old: str, new: str, *, conn=None) -> int:
    """Move `old` to `new` in every row carrying it. Reversed by swapping names."""
    c, t = _bind(conn), _table(table)
    params = {"old": old, "new": new}
    clash = c.execute(sa.text(
        f"SELECT count(*) FROM {t} WHERE doc ? CAST(:old AS text) AND doc ? CAST(:new AS text)"),
        params).scalar_one()
    if clash:
        raise DocFieldConflict(f"{t}: {clash} row(s) carry both {old!r} and {new!r}; "
                               "resolve them in a revision before renaming")
    return c.execute(sa.text(
        f"UPDATE {t} SET doc = (doc - CAST(:old AS text)) "
        f"|| jsonb_build_object(CAST(:new AS text), doc -> CAST(:old AS text)) "
        f"WHERE doc ? CAST(:old AS text)"), params).rowcount


def drop_doc_field(table: str, name: str, *, conn=None) -> int:
    """Snapshot every present `name` value into the side table, then remove it."""
    c, t = _bind(conn), _table(table)
    params = {"t": t, "f": name}
    c.execute(sa.text(
        f"INSERT INTO {SIDE_TABLE} (table_name, field, row_id, doc) "
        f"SELECT :t, CAST(:f AS text), id, jsonb_build_object('value', doc -> CAST(:f AS text)) "
        f"FROM {t} WHERE doc ? CAST(:f AS text) "
        f"ON CONFLICT (table_name, field, row_id) "
        f"DO UPDATE SET doc = EXCLUDED.doc, updated_at = clock_timestamp()"), params)
    return c.execute(sa.text(
        f"UPDATE {t} SET doc = doc - CAST(:f AS text) WHERE doc ? CAST(:f AS text)"),
        params).rowcount


def restore_doc_field(table: str, name: str, *, conn=None) -> int:
    """The drop's downgrade: put every snapshotted value back, then forget it."""
    c, t = _bind(conn), _table(table)
    params = {"t": t, "f": name}
    restored = c.execute(sa.text(
        f"UPDATE {t} AS target "
        f"SET doc = target.doc || jsonb_build_object(CAST(:f AS text), side.doc -> 'value') "
        f"FROM {SIDE_TABLE} AS side WHERE side.table_name = :t "
        f"AND side.field = CAST(:f AS text) AND side.row_id = target.id"), params).rowcount
    c.execute(sa.text(
        f"DELETE FROM {SIDE_TABLE} WHERE table_name = :t AND field = CAST(:f AS text)"), params)
    return restored
