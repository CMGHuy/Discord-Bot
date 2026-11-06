import importlib.util
from pathlib import Path
import pytest
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from alembic.migration import MigrationContext
from alembic.operations import Operations

FILE = (Path(__file__).resolve().parents[2] / "swingbot/core/db/migrations/versions"
        / "v197_001_lifecycle_notifications.py")
AT = "2026-10-28T12:00:00+00:00"


def revision():
    spec = importlib.util.spec_from_file_location("v197_migration", FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def legacy(db_conn):
    db_conn.execute(sa.text("""
        CREATE TEMP TABLE manual_close_notify (
          id BIGSERIAL PRIMARY KEY, queued_at TIMESTAMPTZ NOT NULL,
          doc JSONB NOT NULL DEFAULT '{}',
          updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        ) ON COMMIT DROP
    """))
    db_conn.execute(sa.text("""
        CREATE INDEX manual_close_notify_queued_idx
        ON manual_close_notify(queued_at)
    """))
    return db_conn


def insert(conn, document):
    table = sa.table("manual_close_notify", sa.column("queued_at", sa.DateTime(True)),
                     sa.column("doc", JSONB))
    conn.execute(table.insert().values(queued_at=AT, doc=document))


def rows(conn):
    return conn.execute(sa.text("SELECT * FROM manual_close_notify ORDER BY id")).mappings().all()


def run(conn, fn):
    with Operations.context(MigrationContext.configure(conn)):
        fn()


def test_upgrade_preserves_legacy_rows_and_marks_unknown_plan_blocked(legacy, monkeypatch):
    mig = revision()
    monkeypatch.setattr(mig, "_destination", lambda: "5")
    trade = dict(trade_id="T1", ticker="AAPL", direction="bullish", status="closed",
                 entry=100, exit_price=102, closed_at=AT, close_reason="manual")
    plan = dict(kind="plan_transition", plan_id="P1", ticker="MSFT", status="CANCELLED")
    insert(legacy, trade)
    insert(legacy, plan)
    run(legacy, mig.upgrade)
    first, second = rows(legacy)
    assert first["doc"]["kind"] == "trade_closed"
    assert first["doc"]["payload"]["trade"]["exit_price"] == 102
    assert first["doc"]["legacy_payload"] == trade
    assert second["doc"]["kind"] == "plan_transition"
    assert second["doc"]["payload"]["new_status"] == "CANCELLED"
    assert second["doc"]["blocked"] is True
    assert second["doc"]["last_error"] == "legacy_snapshot_incomplete"
    assert second["doc"]["legacy_payload"] == plan
    assert "trade" not in second["doc"]["payload"]
    assert first["event_id"] != second["event_id"]


def test_downgrade_reupgrade_preserves_identity_payload_and_pending(legacy, monkeypatch):
    mig = revision()
    monkeypatch.setattr(mig, "_destination", lambda: None)
    insert(legacy, dict(kind="plan_transition", plan_id="P1", status="CLOSED"))
    run(legacy, mig.upgrade)
    before = dict(rows(legacy)[0])
    run(legacy, mig.downgrade)
    down = rows(legacy)[0]
    assert down["doc"]["event_id"] == before["event_id"]
    assert down["doc"]["payload"] == before["doc"]["payload"]
    assert down["doc"]["delivered_at"] is None
    monkeypatch.setattr(mig, "_destination", lambda: "99")
    run(legacy, mig.upgrade)
    after = rows(legacy)[0]
    assert after["event_id"] == before["event_id"]
    assert after["doc"] == before["doc"]  # no implicit destination reassignment


def test_downgrade_copies_current_columns_over_stale_doc(legacy, monkeypatch):
    mig = revision()
    monkeypatch.setattr(mig, "_destination", lambda: None)
    insert(legacy, dict(trade_id="T1", ticker="AAPL", status="closed"))
    run(legacy, mig.upgrade)
    legacy.execute(sa.text("""UPDATE manual_close_notify SET
        lease_token = 'token', lease_until = queued_at + interval '120 seconds',
        next_attempt_at = queued_at + interval '900 seconds'"""))
    run(legacy, mig.downgrade)
    doc = rows(legacy)[0]["doc"]
    assert doc["lease_token"] == "token"
    assert doc["lease_until"] is not None
    assert doc["next_attempt_at"] != doc["queued_at"]
