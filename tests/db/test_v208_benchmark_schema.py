"""v208: revision v208_001 -- equity_samples.open_notional/_approx, benchmark_bars,
benchmark_refresh; every new column promoted (schema-evolution.md)."""
import pathlib
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic.command import downgrade, upgrade
from alembic.config import Config
from alembic.script import ScriptDirectory

from swingbot.core.db import events, schema

REPO = pathlib.Path(__file__).resolve().parents[2]
BARS = ("symbol", "session", "close", "adj_close", "day_pct", "source_symbol", "final", "as_of")
REFRESH = ("symbol", "full_refreshed_on")
EQUITY_NEW = ("open_notional", "open_notional_approx")


def _cfg():
    return Config(str(REPO / "alembic.ini"))


def test_equity_samples_promotes_both_new_columns_with_reasons():
    promoted = schema.promoted_for("equity_samples")
    assert promoted[-2:] == EQUITY_NEW
    assert set(EQUITY_NEW) <= set(schema.PROMOTION_REASONS["equity_samples"])
    table = schema.equity_samples
    assert isinstance(table.c.open_notional.type, sa.Float) and table.c.open_notional.nullable
    assert isinstance(table.c.open_notional_approx.type, sa.Boolean)
    assert table.c.open_notional_approx.nullable
    assert schema.contract_violations(table) == []


def test_benchmark_bars_is_registered_with_a_composite_key_and_reasons():
    table = schema.METADATA.tables["benchmark_bars"]
    assert schema.promoted_for("benchmark_bars") == BARS
    assert set(schema.PROMOTION_REASONS["benchmark_bars"]) == set(BARS)
    assert schema.contract_violations(table) == []
    assert [c.name for c in table.primary_key.columns] == ["symbol", "session"]
    assert {n for n in BARS if table.c[n].nullable} == {"close", "adj_close", "day_pct"}
    expected_types = {
        "session": sa.Date, "final": sa.Boolean, "close": sa.Float,
        "adj_close": sa.Float, "day_pct": sa.Float,
    }
    assert {name: type(table.c[name].type) for name in expected_types} == expected_types
    assert table.c.as_of.type.timezone is True
    assert list(table.indexes) == []
    assert "benchmark_bars" not in events.TABLE_CHANNELS


def test_benchmark_refresh_is_one_date_per_symbol():
    table = schema.METADATA.tables["benchmark_refresh"]
    assert schema.promoted_for("benchmark_refresh") == REFRESH
    assert set(schema.PROMOTION_REASONS["benchmark_refresh"]) == set(REFRESH)
    assert schema.contract_violations(table) == []
    assert [c.name for c in table.primary_key.columns] == ["symbol"]
    assert table.c.full_refreshed_on.nullable is False
    assert isinstance(table.c.full_refreshed_on.type, sa.Date)
    assert "benchmark_refresh" not in events.TABLE_CHANNELS


def test_v208_001_sits_on_the_single_prior_head():
    scripts = ScriptDirectory.from_config(_cfg())
    revision = scripts.get_revision("v208_001")
    assert scripts.get_revision(revision.down_revision) is not None
    heads = scripts.get_heads()
    assert len(heads) == 1
    assert "v208_001" in {r.revision for r in scripts.iterate_revisions(heads[0], "base")}


def test_upgrade_leaves_existing_rows_null_and_downgrade_removes_everything(db_engine_empty):
    cfg = _cfg()
    prior = ScriptDirectory.from_config(cfg).get_revision("v208_001").down_revision
    at = datetime(2026, 10, 15, 15, 0, tzinfo=timezone.utc)
    with db_engine_empty.begin() as connection:
        cfg.attributes["connection"] = connection
        upgrade(cfg, prior)
        connection.execute(sa.text(
            "INSERT INTO equity_samples (at, realized_balance, unrealized_pnl, equity, open_n, "
            "skipped_n, source, kind) VALUES (:at, 10000, 0, 10000, 0, 0, 'live', 'point')"),
            {"at": at})
        upgrade(cfg, "v208_001")
        row = connection.execute(sa.text(
            "SELECT open_notional, open_notional_approx FROM equity_samples")).one()
        assert (row.open_notional, row.open_notional_approx) == (None, None)
        assert {"benchmark_bars", "benchmark_refresh"} <= set(sa.inspect(connection).get_table_names())
        downgrade(cfg, prior)
        inspector = sa.inspect(connection)
        assert not {"benchmark_bars", "benchmark_refresh"} & set(inspector.get_table_names())
        assert not set(EQUITY_NEW) & {c["name"] for c in inspector.get_columns("equity_samples")}
        upgrade(cfg, "head")
