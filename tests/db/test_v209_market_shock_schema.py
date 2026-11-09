"""v209: revision v209_001 -- market_shock_readings and market_shock_state."""
import pathlib

import pytest
import sqlalchemy as sa
from alembic.command import downgrade, upgrade
from alembic.config import Config
from alembic.script import ScriptDirectory

from swingbot.core.db import events, schema

REPO = pathlib.Path(__file__).resolve().parents[2]
READING = ("as_of", "session_date", "state_after", "breadth_frac", "breadth_speed",
           "spy_atr_move", "qqq_atr_move", "vix_level", "vix_chg_pct", "vix_off_high_pct",
           "sectors_down", "sectors_total", "n_names", "insufficient")
STATE = ("label", "since", "session_date", "vix_session_high", "last_reading_id",
         "last_notice_at")


def test_both_tables_registered_with_reasons_contract_and_no_sse():
    for name, promoted in (("market_shock_readings", READING), ("market_shock_state", STATE)):
        table = schema.METADATA.tables[name]
        assert schema.promoted_for(name) == promoted
        assert set(schema.PROMOTION_REASONS[name]) == set(promoted)
        assert schema.contract_violations(table) == []
        assert name not in events.TABLE_CHANNELS


def test_reading_columns_and_index():
    t = schema.market_shock_readings
    assert [c.name for c in t.primary_key.columns] == ["id"]
    assert isinstance(t.c.id.type, sa.BigInteger)
    for name in ("as_of", "session_date", "state_after", "sectors_down", "sectors_total",
                 "n_names", "insufficient"):
        assert t.c[name].nullable is False
    for name in ("breadth_frac", "breadth_speed", "spy_atr_move", "qqq_atr_move",
                 "vix_level", "vix_chg_pct", "vix_off_high_pct"):
        assert t.c[name].nullable is True and isinstance(t.c[name].type, sa.Float)
    assert t.c.as_of.type.timezone is True
    assert [(i.name, [c.name for c in i.columns]) for i in t.indexes] == [
        ("market_shock_readings_as_of_idx", ["as_of"])]


def test_state_is_one_row_pointing_at_its_last_reading():
    t = schema.market_shock_state
    assert [c.name for c in t.primary_key.columns] == ["id"]
    assert isinstance(t.c.id.type, sa.SmallInteger) and t.c.id.autoincrement is False
    (fk,) = t.c.last_reading_id.foreign_keys
    assert fk.target_fullname == "market_shock_readings.id" and fk.ondelete == "SET NULL"
    assert t.c.label.nullable is False
    checks = {c.name: str(c.sqltext) for c in t.constraints
              if isinstance(c, sa.CheckConstraint)}
    assert checks == {"market_shock_state_single_row": "id = 1"}


def test_v209_001_sits_on_v204_001_and_keeps_one_head():
    scripts = ScriptDirectory.from_config(Config(str(REPO / "alembic.ini")))
    assert scripts.get_revision("v209_001").down_revision == "v204_001"
    heads = scripts.get_heads()
    assert len(heads) == 1
    assert "v209_001" in {r.revision for r in scripts.iterate_revisions(heads[0], "base")}


def test_downgrade_drops_both_and_upgrade_restores_them(db_engine_empty):
    cfg = Config(str(REPO / "alembic.ini"))
    with db_engine_empty.begin() as connection:
        cfg.attributes["connection"] = connection
        upgrade(cfg, "head")
        downgrade(cfg, "v204_001")
        remaining = set(sa.inspect(connection).get_table_names())
        assert not {"market_shock_readings", "market_shock_state"} & remaining
        assert "manual_close_notify" in remaining
        upgrade(cfg, "head")    # leave the shared empty-schema engine at head
        assert {"market_shock_readings", "market_shock_state"} <= set(
            sa.inspect(connection).get_table_names())


def test_the_single_row_check_refuses_a_second_state_row(db_engine_empty):
    cfg = Config(str(REPO / "alembic.ini"))
    with db_engine_empty.begin() as connection:
        cfg.attributes["connection"] = connection
        upgrade(cfg, "head")
        nested = connection.begin_nested()
        with pytest.raises(sa.exc.IntegrityError):
            connection.execute(sa.text(
                "INSERT INTO market_shock_state (id, label) VALUES (2, 'NORMAL')"))
        nested.rollback()
