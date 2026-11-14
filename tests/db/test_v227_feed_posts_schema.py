"""v227: revision v227_001 -- feed_posts, the simple-channel post log behind the
site's voice notifications, and its `feed` NOTIFY channel."""
import pathlib
import sys

import sqlalchemy as sa
from alembic.command import downgrade, upgrade
from alembic.config import Config
from alembic.script import ScriptDirectory

from swingbot.core.db import events, notify, schema

REPO = pathlib.Path(__file__).resolve().parents[2]
REVISION = REPO / "swingbot" / "core" / "db" / "migrations" / "versions" / "v227_001_feed_posts.py"
PROMOTED = ("posted_at", "kind", "ticker", "headline")

sys.path.insert(0, str(REPO / "scripts" / "ops"))
import rollback_migrations as rm  # noqa: E402


def test_registered_with_reasons_and_contract():
    table = schema.METADATA.tables["feed_posts"]
    assert schema.promoted_for("feed_posts") == PROMOTED
    assert set(schema.PROMOTION_REASONS["feed_posts"]) == set(PROMOTED)
    assert all(len(reason) <= 100 for reason in schema.PROMOTION_REASONS["feed_posts"].values())
    assert schema.contract_violations(table) == []


def test_columns_and_index():
    t = schema.feed_posts
    assert [c.name for c in t.primary_key.columns] == ["id"]
    assert isinstance(t.c.id.type, sa.BigInteger)
    assert t.c.posted_at.nullable is False and t.c.posted_at.type.timezone is True
    assert t.c.posted_at.server_default is not None
    assert t.c.kind.nullable is False and t.c.headline.nullable is False
    assert t.c.ticker.nullable is True
    assert [(i.name, [c.name for c in i.columns]) for i in t.indexes] == [
        ("feed_posts_posted_at_idx", ["posted_at"])]


def test_feed_is_the_last_channel_and_feed_posts_raises_it():
    assert notify.CHANNELS[-1] == "feed"
    assert events.TABLE_CHANNELS["feed_posts"] == "feed"
    assert "feed" in events.SSE_EVENTS


def test_v227_001_sits_on_v209_001_and_keeps_one_head():
    scripts = ScriptDirectory.from_config(Config(str(REPO / "alembic.ini")))
    assert scripts.get_revision("v227_001").down_revision == "v209_001"
    heads = scripts.get_heads()
    assert len(heads) == 1
    assert "v227_001" in {r.revision for r in scripts.iterate_revisions(heads[0], "base")}


def test_the_revision_is_rollback_safe_by_its_stated_reason():
    verdict = rm.scan_upgrade(REVISION.read_text(encoding="utf-8"), revision="v227_001",
                              path=str(REVISION))
    assert verdict.safe is True
    assert verdict.override is not None and "feed_posts" in verdict.override


def test_the_revision_restates_its_channel_instead_of_importing_the_registry():
    source = REVISION.read_text(encoding="utf-8")
    assert "TABLE_CHANNELS" not in source
    assert '("feed_posts", "feed")' in source


def _trigger_names(connection) -> set[str]:
    return set(connection.execute(sa.text(
        "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal")).scalars())


def test_downgrade_drops_table_and_trigger_and_upgrade_restores_them(db_engine_empty):
    cfg = Config(str(REPO / "alembic.ini"))
    with db_engine_empty.begin() as connection:
        cfg.attributes["connection"] = connection
        upgrade(cfg, "head")
        assert "feed_posts" in sa.inspect(connection).get_table_names()
        assert notify.trigger_name("feed_posts") in _trigger_names(connection)
        downgrade(cfg, "v209_001")
        assert "feed_posts" not in sa.inspect(connection).get_table_names()
        assert notify.trigger_name("feed_posts") not in _trigger_names(connection)
        assert "market_shock_readings" in sa.inspect(connection).get_table_names()
        upgrade(cfg, "head")    # leave the shared empty-schema engine at head
        assert "feed_posts" in sa.inspect(connection).get_table_names()
        assert notify.trigger_name("feed_posts") in _trigger_names(connection)
