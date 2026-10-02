"""The hybrid-schema contract every table keeps (v116 Phase 2).

`doc JSONB NOT NULL DEFAULT '{}'` is what makes "add a field" a code-only
change; `updated_at TIMESTAMPTZ` is what parity, PITR checks and the listener
lean on. A promoted column costs a migration forever after, so each one must
say why it exists. A new table without `doc` fails here."""
import pathlib

import sqlalchemy as sa
from alembic.command import upgrade
from alembic.config import Config
from sqlalchemy.dialects.postgresql import JSONB

from swingbot.core.db import schema

REPO = pathlib.Path(__file__).resolve().parents[2]


def _reflected_columns(engine) -> dict[str, dict[str, dict]]:
    cfg = Config(str(REPO / "alembic.ini"))
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        upgrade(cfg, "head")
        inspector = sa.inspect(connection)
        return {name: {col["name"]: col for col in inspector.get_columns(name)}
                for name in schema.METADATA.tables}


def test_every_declared_table_keeps_the_contract():
    problems = [p for table in schema.METADATA.tables.values()
                for p in schema.contract_violations(table)]
    assert problems == []


def test_a_table_without_doc_or_updated_at_fails_the_contract():
    bad = sa.Table("bad", sa.MetaData(), sa.Column("id", sa.Integer, primary_key=True))
    assert schema.contract_violations(bad) == ["bad: no doc column", "bad: no updated_at column"]


def test_a_nullable_doc_or_naive_updated_at_fails_the_contract():
    bad = sa.Table("bad2", sa.MetaData(), sa.Column("id", sa.Integer, primary_key=True),
                   sa.Column("doc", JSONB, nullable=True),
                   sa.Column("updated_at", sa.TIMESTAMP(timezone=False), nullable=False))
    assert schema.contract_violations(bad) == [
        "bad2: doc must be JSONB NOT NULL DEFAULT '{}'",
        "bad2: updated_at must be TIMESTAMPTZ NOT NULL",
    ]


def test_the_migrated_database_keeps_the_contract(db_engine_empty):
    """Reflects what the Alembic chain actually built, not what schema.py claims."""
    for name, columns in _reflected_columns(db_engine_empty).items():
        doc = columns.get("doc")
        assert doc is not None, f"{name}: no doc column in the database"
        assert isinstance(doc["type"], JSONB), f"{name}.doc is {doc['type']}"
        assert doc["nullable"] is False, f"{name}.doc is nullable"
        assert "'{}'::jsonb" in str(doc["default"]), f"{name}.doc default is {doc['default']}"
        updated = columns.get("updated_at")
        assert updated is not None, f"{name}: no updated_at column in the database"
        assert getattr(updated["type"], "timezone", False), f"{name}.updated_at is not TIMESTAMPTZ"


def test_every_promoted_column_has_exactly_one_one_line_reason():
    expected = {(t, c) for t, cols in schema.PROMOTED.items() for c in cols}
    given = {(t, c) for t, cols in schema.PROMOTION_REASONS.items() for c in cols}
    assert given == expected, {"missing": expected - given, "stale": given - expected}
    for table, reasons in schema.PROMOTION_REASONS.items():
        for column, reason in reasons.items():
            assert reason.strip() and "\n" not in reason and len(reason) <= 100, (table, column)
