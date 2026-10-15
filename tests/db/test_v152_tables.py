"""v152: plan_followers, plan_notifications, notify_prefs, alert_posts, revision v152_001.

Followers and notification claims cascade with their plan (spec § Schema); the
user ids are Discord snowflakes, which overflow a 32-bit integer."""
import pathlib

import pytest
import sqlalchemy as sa
from alembic.command import downgrade, upgrade
from alembic.config import Config
from alembic.script import ScriptDirectory

from swingbot.core.db import schema
from swingbot.core.db.repositories.base import Repository
from swingbot.core.db.repositories.plans import PlanRepository

REPO = pathlib.Path(__file__).resolve().parents[2]
TS = "2026-10-10T14:00:00+00:00"
SNOWFLAKE = 123456789012345678
V152_TABLES = ("plan_followers", "plan_notifications", "notify_prefs", "alert_posts")
EXPECTED_PROMOTED = {
    "plan_followers": ("plan_id", "user_id", "kind"),
    "plan_notifications": ("plan_id", "event", "state"),
    "notify_prefs": ("user_id",),
    "alert_posts": ("ticker", "at", "outcome"),
}


def _plan(plan_id="P1"):
    return {"plan_id": plan_id, "ticker": "AAPL", "strategy": "RSI", "horizon_key": "2w",
            "status": "PENDING", "created_at": TS}


def _generic(name):
    return Repository(schema.METADATA.tables[name], key="id")


def _index_columns(name):
    return {index.name: [column.name for column in index.columns]
            for index in schema.METADATA.tables[name].indexes}


def _unique_constraints(name):
    return {constraint.name: [column.name for column in constraint.columns]
            for constraint in schema.METADATA.tables[name].constraints
            if isinstance(constraint, sa.UniqueConstraint)}


@pytest.mark.parametrize("name", V152_TABLES)
def test_each_table_is_registered_with_its_promoted_columns_and_reasons(name):
    table = schema.METADATA.tables[name]
    assert schema.promoted_for(name) == EXPECTED_PROMOTED[name]
    assert set(schema.PROMOTION_REASONS[name]) == set(EXPECTED_PROMOTED[name])
    assert schema.contract_violations(table) == []
    for column in EXPECTED_PROMOTED[name]:
        assert table.c[column].nullable is False, (name, column)


def test_the_natural_keys_and_indexes_are_declared():
    assert _unique_constraints("plan_followers")["plan_followers_row_uq"] == [
        "plan_id", "user_id", "kind"]
    assert _index_columns("plan_followers")["plan_followers_plan_idx"] == ["plan_id"]
    assert _unique_constraints("plan_notifications")["plan_notifications_claim_uq"] == [
        "plan_id", "event"]
    assert _index_columns("plan_notifications")["plan_notifications_state_idx"] == ["state"]
    assert schema.notify_prefs.c.user_id.unique is True
    assert _index_columns("alert_posts") == {"alert_posts_ticker_at_idx": ["ticker", "at"]}
    assert schema.alert_posts.c.at.type.timezone is True


def test_discord_user_ids_are_bigint():
    assert isinstance(schema.plan_followers.c.user_id.type, sa.BigInteger)
    assert isinstance(schema.notify_prefs.c.user_id.type, sa.BigInteger)


@pytest.mark.parametrize("name", ["plan_followers", "plan_notifications"])
def test_the_plan_id_foreign_key_cascades(name):
    (fk,) = schema.METADATA.tables[name].c.plan_id.foreign_keys
    assert fk.target_fullname == "plans.plan_id"
    assert fk.ondelete == "CASCADE"


def test_followers_and_claims_go_with_their_plan(db_conn):
    PlanRepository().insert(_plan(), conn=db_conn)
    _generic("plan_followers").insert(
        {"plan_id": "P1", "user_id": SNOWFLAKE, "kind": "taken"}, conn=db_conn)
    _generic("plan_notifications").insert(
        {"plan_id": "P1", "event": "tp1", "state": "pending"}, conn=db_conn)
    PlanRepository().delete("P1", conn=db_conn)
    assert _generic("plan_followers").count(conn=db_conn) == 0
    assert _generic("plan_notifications").count(conn=db_conn) == 0


def test_a_follower_of_a_missing_plan_is_rejected(db_conn):
    with pytest.raises(sa.exc.IntegrityError):
        _generic("plan_followers").insert(
            {"plan_id": "GHOST", "user_id": SNOWFLAKE, "kind": "watch"}, conn=db_conn)


def test_one_claim_per_plan_and_event(db_conn):
    PlanRepository().insert(_plan(), conn=db_conn)
    claims = _generic("plan_notifications")
    claims.insert({"plan_id": "P1", "event": "tp1", "state": "pending"}, conn=db_conn)
    with pytest.raises(sa.exc.IntegrityError):
        claims.insert({"plan_id": "P1", "event": "tp1", "state": "sent"}, conn=db_conn)


def test_an_alert_post_row_round_trips_its_doc(db_conn):
    posts = _generic("alert_posts")
    posts.insert({"ticker": "AAPL", "at": TS, "outcome": "posted", "direction": "bullish",
                  "horizon_key": "2w", "plan_id": "P1"}, conn=db_conn)
    (row,) = posts.list_all(conn=db_conn)
    assert (row["ticker"], row["outcome"], row["direction"], row["horizon_key"]) == (
        "AAPL", "posted", "bullish", "2w")


def test_v152_001_sits_on_the_single_linear_chain():
    s = ScriptDirectory.from_config(Config(str(REPO / "alembic.ini")))
    rev = s.get_revision("v152_001")
    assert s.get_revision(rev.down_revision) is not None
    (head,) = s.get_heads()
    assert "v152_001" in {r.revision for r in s.iterate_revisions(head, rev.down_revision)}


def _tables(connection) -> set[str]:
    return set(sa.inspect(connection).get_table_names())


def test_v152_001_downgrade_drops_the_four_tables_and_upgrade_restores_them(db_engine_empty):
    cfg = Config(str(REPO / "alembic.ini"))
    with db_engine_empty.begin() as connection:
        cfg.attributes["connection"] = connection
        upgrade(cfg, "head")
        assert set(V152_TABLES) <= _tables(connection)
        down = ScriptDirectory.from_config(cfg).get_revision("v152_001").down_revision
        downgrade(cfg, down)    # also reverts any revision stacked above v152_001
        remaining = _tables(connection)
        assert not set(V152_TABLES) & remaining
        assert "plans" in remaining and "starred_plans" in remaining
        upgrade(cfg, "head")    # leave the shared empty-schema engine at head
        assert set(V152_TABLES) <= _tables(connection)
