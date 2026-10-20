"""v173: preregistration_verdicts, revision v173_002 -- the frozen verdict of a
pre-registration, written once by the bot's daily check (V173-26), keyed by
ledger_id so a second insert is impossible."""
import pathlib

import sqlalchemy as sa
from alembic.command import downgrade, upgrade
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.dialects.postgresql import JSONB

from swingbot.core.db import events, schema

REPO = pathlib.Path(__file__).resolve().parents[2]
TABLE = "preregistration_verdicts"
PROMOTED = ("ledger_id", "verdict", "recorded_on")


def test_the_table_is_registered_with_its_promoted_columns_and_reasons():
    table = schema.METADATA.tables[TABLE]
    assert schema.promoted_for(TABLE) == PROMOTED
    assert set(schema.PROMOTION_REASONS[TABLE]) == set(PROMOTED)
    assert schema.contract_violations(table) == []
    assert set(table.c.keys()) == {*PROMOTED, "doc", "updated_at"}
    for column in PROMOTED:
        assert table.c[column].nullable is False, column


def test_ledger_id_is_the_text_primary_key_and_recorded_on_a_date():
    table = schema.preregistration_verdicts
    assert [column.name for column in table.primary_key.columns] == ["ledger_id"]
    assert isinstance(table.c.ledger_id.type, sa.Text)
    assert isinstance(table.c.verdict.type, sa.Text)
    assert isinstance(table.c.recorded_on.type, sa.Date)
    assert not isinstance(table.c.recorded_on.type, sa.DateTime)
    assert isinstance(table.c.doc.type, JSONB)
    assert list(table.indexes) == []
    assert not [c for c in table.constraints if isinstance(c, sa.UniqueConstraint)]


def test_the_table_raises_no_sse_event():
    assert TABLE not in events.TABLE_CHANNELS


def test_v173_002_sits_on_v173_001_and_is_the_single_head():
    scripts = ScriptDirectory.from_config(Config(str(REPO / "alembic.ini")))
    revision = scripts.get_revision("v173_002")
    assert revision.down_revision == "v173_001"
    assert scripts.get_heads() == ["v173_002"]


def _tables(connection) -> set[str]:
    return set(sa.inspect(connection).get_table_names())


def test_v173_002_downgrade_drops_only_the_table_and_upgrade_restores_it(db_engine_empty):
    cfg = Config(str(REPO / "alembic.ini"))
    with db_engine_empty.begin() as connection:
        cfg.attributes["connection"] = connection
        upgrade(cfg, "head")
        assert TABLE in _tables(connection)
        downgrade(cfg, "v173_001")
        remaining = _tables(connection)
        assert TABLE not in remaining
        assert {"plans", "trades", "equity_samples", "scheduled_jobs"} <= remaining
        upgrade(cfg, "head")    # leave the shared empty-schema engine at head
        assert TABLE in _tables(connection)
