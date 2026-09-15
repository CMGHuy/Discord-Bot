"""The schema registry keeps Core tables and codec promotion in lockstep."""
import pytest
import sqlalchemy as sa

from swingbot.core.db import schema
from swingbot.core.db.codec import RESERVED_KEYS


def test_every_registered_table_has_standard_columns_and_a_promoted_entry():
    assert set(schema.METADATA.tables) == set(schema.PROMOTED)
    for name, table in schema.METADATA.tables.items():
        assert table.c.doc.nullable is False, name
        assert table.c.updated_at.nullable is False, name


def test_promoted_fields_are_real_non_infrastructure_columns():
    for name, promoted in schema.PROMOTED.items():
        assert set(promoted) <= set(schema.METADATA.tables[name].c.keys())
        assert not RESERVED_KEYS.intersection(promoted)


def test_register_rejects_a_missing_or_reserved_promoted_column():
    meta = sa.MetaData()
    table = sa.Table("bogus", meta, sa.Column("a", sa.Text), *schema.standard_columns())
    with pytest.raises(ValueError, match="not a column"):
        schema.register(table, ("a", "nope"))
    with pytest.raises(ValueError, match="infrastructure"):
        schema.register(table, ("doc",))


def test_trades_table_has_the_hot_query_contract():
    table = schema.trades
    assert table.c.trade_id.unique is True
    for name in ("trade_id", "ticker", "strategy", "horizon", "direction", "status", "opened_at"):
        assert table.c[name].nullable is False
    assert table.c.closed_at.nullable is True
    assert schema.promoted_for("trades") == (
        "trade_id", "ticker", "strategy", "horizon", "direction", "status",
        "opened_at", "closed_at", "entry", "stop_loss",
    )
