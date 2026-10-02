"""Rename and drop helpers for Alembic data revisions, up and down (v116)."""
import pathlib

import pytest
import sqlalchemy as sa
from alembic.command import upgrade
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations

from swingbot.core.db import doc_fields
from swingbot.core.db.repositories.plans import PlanRepository

REPO = pathlib.Path(__file__).resolve().parents[2]
TS = "2026-10-01T10:00:00+00:00"


def _plan(conn, plan_id, **doc):
    PlanRepository().upsert({"plan_id": plan_id, "ticker": "AAPL", "strategy": "RSI",
                             "horizon_key": "2w", "status": "pending", "created_at": TS,
                             **doc}, conn=conn)


def _get(conn, plan_id):
    return PlanRepository().get(plan_id, conn=conn)


def test_rename_moves_the_value_and_the_reverse_call_moves_it_back(db_conn):
    _plan(db_conn, "P1", old_name={"a": [1, 2]})
    _plan(db_conn, "P2")
    assert doc_fields.rename_doc_field("plans", "old_name", "new_name", conn=db_conn) == 1
    p1 = _get(db_conn, "P1")
    assert "old_name" not in p1 and p1["new_name"] == {"a": [1, 2]}
    assert "new_name" not in _get(db_conn, "P2")
    doc_fields.rename_doc_field("plans", "new_name", "old_name", conn=db_conn)
    assert _get(db_conn, "P1")["old_name"] == {"a": [1, 2]}


def test_rename_refuses_a_row_carrying_both_names_and_changes_nothing(db_conn):
    _plan(db_conn, "P1", old_name=1, new_name=2)
    with pytest.raises(doc_fields.DocFieldConflict, match="both"):
        doc_fields.rename_doc_field("plans", "old_name", "new_name", conn=db_conn)
    p1 = _get(db_conn, "P1")
    assert (p1["old_name"], p1["new_name"]) == (1, 2)


def test_drop_snapshots_first_and_restore_puts_every_value_back(db_conn):
    _plan(db_conn, "P1", legacy=3.5)
    _plan(db_conn, "P2", legacy=None)        # an explicit null is a value too
    _plan(db_conn, "P3")
    assert doc_fields.drop_doc_field("plans", "legacy", conn=db_conn) == 2
    assert all("legacy" not in _get(db_conn, p) for p in ("P1", "P2", "P3"))
    side = db_conn.execute(sa.text("SELECT count(*) FROM dropped_doc_fields")).scalar_one()
    assert side == 2
    assert doc_fields.restore_doc_field("plans", "legacy", conn=db_conn) == 2
    assert _get(db_conn, "P1")["legacy"] == 3.5
    raw = db_conn.execute(sa.text(
        "SELECT doc ? 'legacy' FROM plans WHERE plan_id = 'P2'")).scalar_one()
    assert raw is True
    assert "legacy" not in _get(db_conn, "P3")
    assert db_conn.execute(sa.text("SELECT count(*) FROM dropped_doc_fields")).scalar_one() == 0


def test_a_repeated_drop_overwrites_its_snapshot_instead_of_failing(db_conn):
    _plan(db_conn, "P1", legacy=1)
    doc_fields.drop_doc_field("plans", "legacy", conn=db_conn)
    _plan(db_conn, "P1", legacy=2)
    doc_fields.drop_doc_field("plans", "legacy", conn=db_conn)
    doc_fields.restore_doc_field("plans", "legacy", conn=db_conn)
    assert _get(db_conn, "P1")["legacy"] == 2


def test_the_table_name_is_validated_before_it_reaches_sql(db_conn):
    with pytest.raises(ValueError, match="identifier"):
        doc_fields.drop_doc_field("plans; DROP TABLE trades", "x", conn=db_conn)


def test_inside_a_revision_the_helpers_use_the_alembic_bind(db_engine_empty):
    cfg = Config(str(REPO / "alembic.ini"))
    with db_engine_empty.begin() as connection:
        cfg.attributes["connection"] = connection
        upgrade(cfg, "head")
        _plan(connection, "P-op", before=1)
        with Operations.context(MigrationContext.configure(connection)):
            assert doc_fields.rename_doc_field("plans", "before", "after") == 1
        assert _get(connection, "P-op")["after"] == 1
        connection.execute(sa.text("DELETE FROM plans WHERE plan_id = 'P-op'"))
