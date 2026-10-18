"""v172: equity_samples, revision v172_001 -- raw equity samples for the
Dashboard candle chart (live recorder rows and backfill rows)."""
import pathlib

import sqlalchemy as sa
from alembic.command import downgrade, upgrade
from alembic.config import Config
from alembic.script import ScriptDirectory

from swingbot.core.db import schema

REPO = pathlib.Path(__file__).resolve().parents[2]
PROMOTED = ("at", "realized_balance", "unrealized_pnl", "equity", "open_n", "skipped_n",
            "source", "kind", "backfill_run")


def test_the_table_is_registered_with_its_promoted_columns_and_reasons():
    table = schema.METADATA.tables["equity_samples"]
    assert schema.promoted_for("equity_samples") == PROMOTED
    assert set(schema.PROMOTION_REASONS["equity_samples"]) == set(PROMOTED)
    assert schema.contract_violations(table) == []
    for column in PROMOTED[:-1]:
        assert table.c[column].nullable is False, column
    assert table.c.backfill_run.nullable is True


def test_money_is_double_precision_and_at_is_timestamptz():
    table = schema.equity_samples
    for column in ("realized_balance", "unrealized_pnl", "equity"):
        assert isinstance(table.c[column].type, sa.Float), column
        assert table.c[column].type.precision == 53, column
    assert table.c.at.type.timezone is True
    assert isinstance(table.c.id.type, sa.BigInteger)


def test_the_unique_key_and_the_range_index_are_declared():
    table = schema.equity_samples
    uniques = {c.name: [col.name for col in c.columns] for c in table.constraints
               if isinstance(c, sa.UniqueConstraint)}
    assert uniques["equity_samples_at_source_kind_uq"] == ["at", "source", "kind"]
    indexes = {i.name: [col.name for col in i.columns] for i in table.indexes}
    assert indexes == {"equity_samples_source_at_idx": ["source", "at"]}


def test_v172_001_sits_on_the_single_prior_head():
    scripts = ScriptDirectory.from_config(Config(str(REPO / "alembic.ini")))
    revision = scripts.get_revision("v172_001")
    assert scripts.get_revision(revision.down_revision) is not None
    assert len(scripts.get_heads()) == 1


def _tables(connection) -> set[str]:
    return set(sa.inspect(connection).get_table_names())


def test_v172_001_downgrade_drops_the_table_and_upgrade_restores_it(db_engine_empty):
    cfg = Config(str(REPO / "alembic.ini"))
    with db_engine_empty.begin() as connection:
        cfg.attributes["connection"] = connection
        upgrade(cfg, "head")
        assert "equity_samples" in _tables(connection)
        downgrade(cfg, ScriptDirectory.from_config(cfg).get_revision("v172_001").down_revision)
        remaining = _tables(connection)
        assert "equity_samples" not in remaining
        assert "trades" in remaining and "gate_rejections" in remaining
        upgrade(cfg, "head")    # leave the shared empty-schema engine at head
        assert "equity_samples" in _tables(connection)
