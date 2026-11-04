"""v201: revision v201_001 -- the admin refresher's four stores and the
market_cache (kind, updated_at) index behind GET /market/updates."""
import pathlib

import pytest
import sqlalchemy as sa
from alembic.command import downgrade, upgrade
from alembic.config import Config
from alembic.script import ScriptDirectory

from swingbot.core.db import events, schema

REPO = pathlib.Path(__file__).resolve().parents[2]
TABLES = {
    "quote_currencies": ("symbol", "code", "outcome", "checked_at", "retry_after"),
    "market_refresh_queue": ("kind", "key", "priority", "requested_at", "taken_at"),
    "market_refresh_marks": ("key", "started_at", "expires_at", "error", "error_at"),
    "refresher_heartbeat": ("key", "beat_at", "cadence_s", "session", "cycle_ms", "last_error"),
}
NULLABLE = {"code", "retry_after", "taken_at", "error", "error_at", "cycle_ms", "last_error"}


@pytest.mark.parametrize("name", sorted(TABLES))
def test_registered_with_reasons_contract_and_no_sse(name):
    table = schema.METADATA.tables[name]
    assert schema.promoted_for(name) == TABLES[name]
    assert set(schema.PROMOTION_REASONS[name]) == set(TABLES[name])
    assert schema.contract_violations(table) == []
    for column in TABLES[name]:
        assert table.c[column].nullable is (column in NULLABLE), (name, column)
    assert name not in events.TABLE_CHANNELS


def _indexes(table):
    return {i.name: ([c.name for c in i.columns], i.unique) for i in table.indexes}


def test_indexes_and_the_pending_queue_uniqueness():
    assert _indexes(schema.market_refresh_marks) == {
        "market_refresh_marks_updated_idx": (["updated_at"], False)}
    queue = _indexes(schema.market_refresh_queue)
    assert queue["market_refresh_queue_pending_uq"] == (["kind", "key"], True)
    assert queue["market_refresh_queue_take_idx"] == (["taken_at", "priority", "requested_at"], False)
    pending = next(i for i in schema.market_refresh_queue.indexes
                   if i.name == "market_refresh_queue_pending_uq")
    assert "taken_at IS NULL" in str(pending.dialect_options["postgresql"]["where"])
    assert _indexes(schema.market_cache)["market_cache_kind_updated_idx"] == (
        ["kind", "updated_at"], False)


def test_column_types():
    assert isinstance(schema.market_refresh_queue.c.id.type, sa.BigInteger)
    assert isinstance(schema.market_refresh_queue.c.priority.type, sa.SmallInteger)
    assert isinstance(schema.refresher_heartbeat.c.cadence_s.type, sa.Float)
    for table, col in (("quote_currencies", "checked_at"),
                       ("market_refresh_marks", "expires_at"), ("refresher_heartbeat", "beat_at")):
        assert schema.METADATA.tables[table].c[col].type.timezone is True


def test_v201_001_sits_on_the_single_prior_head():
    scripts = ScriptDirectory.from_config(Config(str(REPO / "alembic.ini")))
    revision = scripts.get_revision("v201_001")
    assert scripts.get_revision(revision.down_revision) is not None
    heads = scripts.get_heads()
    assert len(heads) == 1      # later revisions may stack on v201_001; never branch
    assert "v201_001" in {r.revision for r in scripts.iterate_revisions(heads[0], "base")}


def _tables(connection) -> set[str]:
    return set(sa.inspect(connection).get_table_names())


def test_downgrade_drops_the_four_and_upgrade_restores_them(db_engine_empty):
    cfg = Config(str(REPO / "alembic.ini"))
    with db_engine_empty.begin() as connection:
        cfg.attributes["connection"] = connection
        upgrade(cfg, "head")
        assert set(TABLES) <= _tables(connection)
        downgrade(cfg, ScriptDirectory.from_config(cfg).get_revision("v201_001").down_revision)
        remaining = _tables(connection)
        assert not set(TABLES) & remaining
        assert "market_cache" in remaining
        idx = {i["name"] for i in sa.inspect(connection).get_indexes("market_cache")}
        assert "market_cache_kind_updated_idx" not in idx
        upgrade(cfg, "head")    # leave the shared empty-schema engine at head
        assert set(TABLES) <= _tables(connection)
