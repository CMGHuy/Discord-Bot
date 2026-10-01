"""Every table that should raise an SSE event has a trigger that does."""
import pathlib

import sqlalchemy as sa
from alembic.command import upgrade
from alembic.config import Config

from swingbot.core.db import events, notify, schema

REPO = pathlib.Path(__file__).resolve().parents[2]


def _installed_triggers(connection) -> set[str]:
    return {row[0] for row in connection.execute(sa.text(
        "select tgname from pg_trigger where not tgisinternal"))}


def _missing_message(missing) -> str:
    return (f"tables with no NOTIFY trigger: {sorted(missing)}. Add them to "
            f"TABLE_CHANNELS and to a migration.")


def test_every_mapped_table_exists():
    unknown = set(events.TABLE_CHANNELS) - set(schema.METADATA.tables)
    assert not unknown, f"TABLE_CHANNELS names tables that do not exist: {unknown}"


def test_every_channel_is_a_known_channel():
    bad = set(events.TABLE_CHANNELS.values()) - set(notify.CHANNELS)
    assert not bad, f"unknown channels: {bad}"


def test_every_mapped_table_has_an_installed_trigger(db_conn):
    expected = {notify.trigger_name(t) for t in events.TABLE_CHANNELS}
    missing = expected - _installed_triggers(db_conn)
    assert not missing, _missing_message(missing)


def test_upgrade_head_installs_a_trigger_for_every_mapped_table(db_engine_empty):
    """Covers the migration itself, not just the fixture derived from the map."""
    cfg = Config(str(REPO / "alembic.ini"))
    with db_engine_empty.begin() as connection:
        cfg.attributes["connection"] = connection
        upgrade(cfg, "head")
        installed = _installed_triggers(connection)
    expected = {notify.trigger_name(t) for t in events.TABLE_CHANNELS}
    missing = expected - installed
    assert not missing, _missing_message(missing)
