"""v204: revision v204_001 -- admin_snapshots, one row per key, newer computed_at wins."""
import math
import pathlib
from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa
from alembic.command import downgrade, upgrade
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.dialects import postgresql

from swingbot.core.db import events, schema
from swingbot.core.db.repositories import admin_snapshots as snaps

REPO = pathlib.Path(__file__).resolve().parents[2]
UTC = timezone.utc
T0 = datetime(2026, 10, 28, 15, 0, tzinfo=UTC)
EPOCH = datetime(2000, 1, 1, tzinfo=UTC)
PROMOTED = ("key", "computed_at", "stale_inputs", "inputs")


def test_registered_with_reasons_contract_and_no_sse():
    table = schema.METADATA.tables["admin_snapshots"]
    assert schema.promoted_for("admin_snapshots") == PROMOTED
    assert set(schema.PROMOTION_REASONS["admin_snapshots"]) == set(PROMOTED)
    assert schema.contract_violations(table) == []
    assert all(table.c[c].nullable is False for c in PROMOTED)
    assert "admin_snapshots" not in events.TABLE_CHANNELS


def test_column_types_and_index():
    t = schema.admin_snapshots
    assert t.c.key.primary_key and isinstance(t.c.key.type, sa.Text)
    assert t.c.computed_at.type.timezone is True
    assert isinstance(t.c.stale_inputs.type, sa.Boolean)
    assert "false" in str(t.c.stale_inputs.server_default.arg).lower()
    assert isinstance(t.c.inputs.type, postgresql.JSONB)
    assert {i.name: [c.name for c in i.columns] for i in t.indexes} == {
        "admin_snapshots_updated_idx": ["updated_at"]}


def test_v204_001_sits_on_the_single_prior_head():
    scripts = ScriptDirectory.from_config(Config(str(REPO / "alembic.ini")))
    revision = scripts.get_revision("v204_001")
    assert scripts.get_revision(revision.down_revision) is not None
    heads = scripts.get_heads()
    assert len(heads) == 1
    assert "v204_001" in {r.revision for r in scripts.iterate_revisions(heads[0], "base")}


def test_downgrade_drops_the_table_and_upgrade_restores_it(db_engine_empty):
    cfg = Config(str(REPO / "alembic.ini"))
    with db_engine_empty.begin() as connection:
        cfg.attributes["connection"] = connection
        upgrade(cfg, "head")
        assert "admin_snapshots" in sa.inspect(connection).get_table_names()
        downgrade(cfg, ScriptDirectory.from_config(cfg).get_revision("v204_001").down_revision)
        remaining = set(sa.inspect(connection).get_table_names())
        assert "admin_snapshots" not in remaining and "market_refresh_marks" in remaining
        upgrade(cfg, "head")    # leave the shared empty-schema engine at head
        assert "admin_snapshots" in sa.inspect(connection).get_table_names()


DOC = {"heat": {"open_pct": 1.25, "cap_pct": 6.0}, "positions": [], "correlation": {"values": None}}
INPUTS = {"computed_at": T0.isoformat(), "missing": {"bars": {"XAUUSD": "spot_metal"}}}


def test_put_inserts_and_read_returns_the_row(db_conn):
    repo = snaps.AdminSnapshotRepository()
    assert repo.put("risk", DOC, INPUTS, computed_at=T0, stale_inputs=True, conn=db_conn) is True
    row = repo.read("risk", conn=db_conn)
    assert (row["key"], row["doc"], row["inputs"], row["computed_at"], row["stale_inputs"]) == (
        "risk", DOC, INPUTS, T0, True)
    assert row["updated_at"].tzinfo is not None
    assert repo.read("calendar.pnl:2026-10", conn=db_conn) is None


def test_put_newer_computed_at_replaces(db_conn):
    repo = snaps.AdminSnapshotRepository()
    repo.put("risk", DOC, INPUTS, computed_at=T0, stale_inputs=True, conn=db_conn)
    newer = {**DOC, "positions": [{"ticker": "AAPL"}]}
    assert repo.put("risk", newer, {}, computed_at=T0 + timedelta(seconds=1),
                    stale_inputs=False, conn=db_conn) is True
    row = repo.read("risk", conn=db_conn)
    assert (row["doc"], row["inputs"], row["stale_inputs"]) == (newer, {}, False)


@pytest.mark.parametrize("delta", [timedelta(0), timedelta(seconds=-90)])
def test_put_older_computed_at_is_rejected(db_conn, delta):
    repo = snaps.AdminSnapshotRepository()
    repo.put("risk", DOC, INPUTS, computed_at=T0, stale_inputs=False, conn=db_conn)
    late = {"heat": {"open_pct": 99.0}}
    assert repo.put("risk", late, {}, computed_at=T0 + delta, stale_inputs=True, conn=db_conn) is False
    row = repo.read("risk", conn=db_conn)
    assert (row["doc"], row["computed_at"], row["stale_inputs"]) == (DOC, T0, False)


def test_put_refuses_naive_times_and_non_finite_numbers(db_conn):
    repo = snaps.AdminSnapshotRepository()
    with pytest.raises(ValueError):
        repo.put("risk", DOC, {}, computed_at=T0.replace(tzinfo=None), stale_inputs=False, conn=db_conn)
    with pytest.raises(ValueError):
        repo.put("risk", {"beta": math.nan}, {}, computed_at=T0, stale_inputs=False, conn=db_conn)
    with pytest.raises(ValueError):
        repo.put("risk", DOC, {"rate": math.inf}, computed_at=T0, stale_inputs=False, conn=db_conn)
    assert repo.read("risk", conn=db_conn) is None


def test_read_many_returns_only_present_keys(db_conn):
    repo = snaps.AdminSnapshotRepository()
    repo.put("risk", DOC, {}, computed_at=T0, stale_inputs=False, conn=db_conn)
    repo.put("analytics.snapshot", {"overall": {}}, {}, computed_at=T0, stale_inputs=False, conn=db_conn)
    got = repo.read_many(["risk", "analytics.snapshot", "calendar.pnl:2026-10"], conn=db_conn)
    assert set(got) == {"risk", "analytics.snapshot"} and got["risk"]["doc"] == DOC
    assert repo.read_many([], conn=db_conn) == {}


def test_changed_since_sees_writes_after_the_cursor(db_conn):
    repo = snaps.AdminSnapshotRepository()
    cursor = db_conn.execute(sa.text("select clock_timestamp()")).scalar()
    repo.put("risk", DOC, {}, computed_at=T0, stale_inputs=True, conn=db_conn)
    [row] = repo.changed_since(cursor, conn=db_conn)
    assert (row["key"], row["computed_at"], row["stale_inputs"]) == ("risk", T0, True)
    assert set(row) == {"key", "computed_at", "stale_inputs", "updated_at"}
    assert repo.changed_since(row["updated_at"], conn=db_conn) == []
    repo.put("risk", DOC, {}, computed_at=T0 - timedelta(seconds=5), stale_inputs=False, conn=db_conn)
    assert repo.changed_since(row["updated_at"], conn=db_conn) == []      # a rejected put is no change


def test_prune_deletes_old_months_only(db_conn):
    repo = snaps.AdminSnapshotRepository()
    for key in ("risk", "calendar.pnl:2026-08", "calendar.pnl:2026-09", "calendar.pnl:2026-10"):
        repo.put(key, {}, {}, computed_at=T0, stale_inputs=False, conn=db_conn)
    assert repo.prune("calendar_pnl:", [], conn=db_conn) == 0            # "_" is not a LIKE wildcard here
    assert repo.prune("calendar.pnl:", ["calendar.pnl:2026-10", "calendar.pnl:2026-09"], conn=db_conn) == 1
    assert set(repo.read_many(["risk", "calendar.pnl:2026-08", "calendar.pnl:2026-09",
                               "calendar.pnl:2026-10"], conn=db_conn)) == {
        "risk", "calendar.pnl:2026-09", "calendar.pnl:2026-10"}


def test_accessor_is_a_singleton():
    assert snaps.admin_snapshot_repo() is snaps.admin_snapshot_repo()
