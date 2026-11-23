"""v239: revision v239_001 -- market_regime_days, one write-once row per session."""
import pathlib

import sqlalchemy as sa
from alembic.command import downgrade, upgrade
from alembic.config import Config
from alembic.script import ScriptDirectory

from swingbot.core.db import events, schema

REPO = pathlib.Path(__file__).resolve().parents[2]
NAME = "market_regime_days"
PREVIOUS = "v228_001"   # = python -m alembic heads before this revision
FLOATS = ("spy_close", "sma50", "sma200", "sma50_lag5", "sma200_lag20", "spy_high_prev",
          "vix_close", "vix_max5")
PROMOTED = ("last_bar_date", "state", "stress", "pullback_trigger", "pullback_reason",
            *FLOATS, "spy_provider", "vix_provider", "computed_at")


def test_registered_with_reasons_contract_and_no_sse():
    table = schema.METADATA.tables[NAME]
    assert schema.promoted_for(NAME) == PROMOTED
    assert set(schema.PROMOTION_REASONS[NAME]) == set(PROMOTED)
    assert all(len(reason) <= 100 for reason in schema.PROMOTION_REASONS[NAME].values())
    assert schema.contract_violations(table) == []
    assert NAME not in events.TABLE_CHANNELS


def test_columns_key_and_state_check():
    t = schema.market_regime_days
    assert [c.name for c in t.primary_key.columns] == ["session_date"]
    assert isinstance(t.c.session_date.type, sa.Date)
    assert isinstance(t.c.last_bar_date.type, sa.Date) and t.c.last_bar_date.nullable is True
    for name in ("state", "pullback_trigger", "computed_at"):
        assert t.c[name].nullable is False, name
    for name in FLOATS:
        assert t.c[name].nullable is True and isinstance(t.c[name].type, sa.Float), name
    for name in ("stress", "pullback_reason", "spy_provider", "vix_provider"):
        assert t.c[name].nullable is True, name
    assert isinstance(t.c.stress.type, sa.Boolean)
    assert t.c.computed_at.type.timezone is True
    checks = {c.name: str(c.sqltext) for c in t.constraints if isinstance(c, sa.CheckConstraint)}
    assert checks == {"market_regime_days_state":
                      "state IN ('BEAR', 'CORRECTION', 'NORMAL', 'UNKNOWN')"}
    assert list(t.indexes) == []


def test_v239_001_sits_on_the_previous_head_and_keeps_one_head():
    scripts = ScriptDirectory.from_config(Config(str(REPO / "alembic.ini")))
    assert scripts.get_revision("v239_001").down_revision == PREVIOUS
    heads = scripts.get_heads()
    assert len(heads) == 1
    assert "v239_001" in {r.revision for r in scripts.iterate_revisions(heads[0], "base")}


def test_downgrade_drops_the_table_and_upgrade_restores_it(db_engine_empty):
    cfg = Config(str(REPO / "alembic.ini"))
    with db_engine_empty.begin() as connection:
        cfg.attributes["connection"] = connection
        upgrade(cfg, "head")
        downgrade(cfg, PREVIOUS)
        remaining = set(sa.inspect(connection).get_table_names())
        assert NAME not in remaining
        assert "manual_close_notify" in remaining
        upgrade(cfg, "head")    # leave the shared empty-schema engine at head
        assert NAME in set(sa.inspect(connection).get_table_names())
