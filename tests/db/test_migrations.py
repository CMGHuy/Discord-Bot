"""The Alembic revision graph must remain a single, named chain."""
import pathlib
import re

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

REPO = pathlib.Path(__file__).resolve().parents[2]
ID_RE = re.compile(r"^p[1-6]_\d{3}$")


@pytest.fixture(scope="module")
def scripts():
    cfg = Config(str(REPO / "alembic.ini"))
    return ScriptDirectory.from_config(cfg)


def test_exactly_one_head(scripts):
    heads = scripts.get_heads()
    assert len(heads) == 1, f"multiple Alembic heads: {heads}"


def test_every_revision_id_is_part_prefixed(scripts):
    bad = [revision.revision for revision in scripts.walk_revisions()
           if not ID_RE.match(revision.revision)]
    assert not bad, f"non-prefixed revision ids: {bad}"


def test_the_graph_roots_at_the_baseline(scripts):
    roots = [revision.revision for revision in scripts.walk_revisions()
             if revision.down_revision is None]
    assert roots == ["p1_001"]


def test_migrations_produce_exactly_the_declared_schema(db_engine_empty, monkeypatch):
    """Catch a schema.py edit that lacks its matching Alembic revision."""
    from alembic.autogenerate import compare_metadata
    from alembic.command import upgrade
    from alembic.migration import MigrationContext

    from swingbot.core.db.schema import METADATA

    cfg = Config(str(REPO / "alembic.ini"))
    with db_engine_empty.begin() as connection:
        # The supplied connection keeps migration DDL inside this test's
        # explicitly isolated test database, not the app's Compose hostname.
        cfg.attributes["connection"] = connection
        upgrade(cfg, "head")
        diff = compare_metadata(MigrationContext.configure(connection), METADATA)
    real = [item for item in diff if not (
        isinstance(item, tuple) and str(item[0]).endswith("_index")
        and "opened_idx" in str(item)
    )]
    assert real == [], f"schema.py and migrations disagree: {real}"
