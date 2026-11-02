from datetime import datetime, timedelta, timezone
from uuid import uuid4
import pytest
import sqlalchemy as sa
from swingbot.core.db.repositories.notify_queue import NotifyQueueRepository
from swingbot.core.db.schema import manual_close_notify as queue
from swingbot.core.infra.lifecycle_events import make_event

NOW = datetime(2026, 10, 28, 12, tzinfo=timezone.utc)


def fresh(identity=None, channel="5"):
    stamp = NOW.isoformat()
    return make_event(transition_id=identity or str(uuid4()), kind="plan_transition",
        target_channel_id=channel, occurred_at=stamp,
        payload=dict(ticker="AAPL", direction="bullish", plan_id="P1", trade_id=None,
                     prior_status="PENDING", new_status="CANCELLED", reason="manual",
                     occurred_at=stamp))


def record(repo, conn, event):
    return repo.list_all(conn=conn, where=queue.c.event_id == event["event_id"])[0]


def test_enqueue_uses_outer_transaction_and_rejects_conflicting_identity(db_conn):
    repo = NotifyQueueRepository()
    event = fresh()
    nested = db_conn.begin_nested()
    repo.enqueue(event, conn=db_conn)
    repo.enqueue(event, conn=db_conn)
    assert repo.pending(conn=db_conn) == 1
    conflicting = {**event, "payload": {**event["payload"], "reason": "different"}}
    with pytest.raises(ValueError, match="conflicting_event"):
        repo.enqueue(conflicting, conn=db_conn)
    nested.rollback()
    assert repo.pending(conn=db_conn) == 0


def test_claim_expiry_stale_ack_and_acknowledgement(db_conn):
    repo = NotifyQueueRepository()
    event = fresh()
    repo.enqueue(event, conn=db_conn)
    first = repo.claim_one("worker-a", now=NOW, conn=db_conn)
    assert first["attempt_count"] == 1
    assert repo.claim_one("worker-b", now=NOW, conn=db_conn) is None
    later = NOW + timedelta(seconds=121)
    second = repo.claim_one("worker-b", now=later, conn=db_conn)
    assert second["lease_token"] != first["lease_token"]
    assert second["event_id"] == first["event_id"]
    assert not repo.acknowledge(event["event_id"], first["lease_token"], "111",
                                now=later, conn=db_conn)
    assert not repo.reschedule(event["event_id"], first["lease_token"], now=later,
                               delay_s=5, error_code="timeout", blocked=False, conn=db_conn)
    assert repo.acknowledge(event["event_id"], second["lease_token"], "222",
                            now=later, conn=db_conn)
    assert repo.pending(conn=db_conn) == 0
    assert record(repo, db_conn, event)["delivered_message_id"] == "222"


def test_retry_and_blocked_are_pending_with_no_destination_rerouting(db_conn, caplog):
    repo = NotifyQueueRepository()
    event = fresh()
    repo.enqueue(event, conn=db_conn)
    claim = repo.claim_one("w", now=NOW, conn=db_conn)
    with caplog.at_level("ERROR"):
        assert repo.reschedule(event["event_id"], claim["lease_token"], now=NOW,
            delay_s=900, error_code="permission_denied", blocked=True, conn=db_conn)
    assert event["event_id"] in caplog.text
    assert "permission_denied" in caplog.text
    assert repo.claim_one("w", now=NOW + timedelta(seconds=899), conn=db_conn) is None
    assert record(repo, db_conn, event)["target_channel_id"] == "5"


def test_failed_ack_rolls_back_but_intent_survives(db_conn, monkeypatch):
    repo = NotifyQueueRepository()
    event = fresh()
    repo.enqueue(event, conn=db_conn)
    claim = repo.claim_one("w", now=NOW, conn=db_conn)
    original = repo._write
    def fail_after_write(conn, value):
        original(conn, value)
        raise RuntimeError("injected persistence failure")
    monkeypatch.setattr(repo, "_write", fail_after_write)
    with pytest.raises(RuntimeError), db_conn.begin_nested():
        repo.acknowledge(event["event_id"], claim["lease_token"], "123", now=NOW, conn=db_conn)
    assert repo.pending(conn=db_conn) == 1
    assert record(repo, db_conn, event)["delivered_message_id"] is None


@pytest.fixture
def committed_queue(db_engine, monkeypatch):
    monkeypatch.setattr("swingbot.core.db.repositories.base.get_engine", lambda: db_engine)
    repo = NotifyQueueRepository()
    events = [fresh(), fresh()]
    for event in events:
        repo.enqueue(event)  # internally committed, visible to both connections
    yield repo, db_engine, events
    with db_engine.begin() as conn:
        conn.execute(queue.delete().where(queue.c.event_id.in_([e["event_id"] for e in events])))


def test_concurrent_claim_skips_locked_row(committed_queue):
    repo, engine, events = committed_queue
    with engine.connect() as one, engine.connect() as two:
        with one.begin(), two.begin():
            first = repo.claim_one("one", now=NOW, conn=one)
            second = repo.claim_one("two", now=NOW, conn=two)
            assert first["event_id"] != second["event_id"]
            assert {first["event_id"], second["event_id"]} == {e["event_id"] for e in events}
    assert repo.claim_one("three", now=NOW) is None


def test_ack_failure_owned_transaction_preserves_committed_claim(committed_queue, monkeypatch):
    repo, engine, events = committed_queue
    claim = repo.claim_one("one", now=NOW)
    original = repo._write
    def fail_after_write(conn, value):
        original(conn, value)
        raise RuntimeError("ack connection lost")
    monkeypatch.setattr(repo, "_write", fail_after_write)
    with pytest.raises(RuntimeError):
        repo.acknowledge(claim["event_id"], claim["lease_token"], "999", now=NOW)
    with engine.connect() as conn:
        saved = record(repo, conn, claim)
    assert saved["lease_token"] == claim["lease_token"]
    assert saved["delivered_at"] is None


def test_expired_token_cannot_complete_without_a_new_claim(db_conn):
    repo = NotifyQueueRepository()
    event = fresh()
    repo.enqueue(event, conn=db_conn)
    claim = repo.claim_one("w", now=NOW, conn=db_conn)
    expiry = NOW + timedelta(seconds=120)
    assert not repo.acknowledge(event["event_id"], claim["lease_token"], "42",
                                now=expiry, conn=db_conn)
    assert repo.pending(conn=db_conn) == 1


def test_blocked_log_only_on_state_or_cause_change(db_conn, caplog):
    repo = NotifyQueueRepository()
    event = fresh()
    repo.enqueue(event, conn=db_conn)
    with caplog.at_level("ERROR"):
        for offset in (0, 900):
            tick = NOW + timedelta(seconds=offset)
            claim = repo.claim_one("w", now=tick, conn=db_conn)
            assert repo.reschedule(event["event_id"], claim["lease_token"], now=tick,
                delay_s=900, error_code="permission_denied", blocked=True, conn=db_conn)
    assert len([r for r in caplog.records if "lifecycle blocked" in r.message]) == 1


def test_retarget_audits_and_refuses_live_lease_or_delivered(db_conn):
    repo = NotifyQueueRepository()
    event = fresh(channel=None)
    repo.enqueue(event, conn=db_conn)
    assert repo.retarget(event["event_id"], "9", actor="operator", reason="channel repair",
                         now=NOW, conn=db_conn)
    changed = record(repo, db_conn, event)
    assert changed["payload"] == event["payload"]
    assert changed["event_id"] == event["event_id"]
    assert changed["target_channel_id"] == "9"
    assert changed["retarget_history"][0]["from_channel_id"] is None
    assert changed["retarget_history"][0]["actor"] == "operator"
    claim = repo.claim_one("w", now=NOW, conn=db_conn)
    assert not repo.retarget(event["event_id"], "10", actor="operator", reason="repair",
                             now=NOW, conn=db_conn)
    repo.acknowledge(event["event_id"], claim["lease_token"], "123", now=NOW, conn=db_conn)
    assert not repo.retarget(event["event_id"], "10", actor="operator", reason="repair",
                             now=NOW, conn=db_conn)


def test_empty_health_is_known_zero_but_age_unknown(db_conn):
    assert NotifyQueueRepository().health(now=NOW, conn=db_conn) == dict(
        pending_count=0, oldest_pending_age_seconds=None, blocked_count=0)


def test_retarget_does_not_clear_malformed_payload_block(db_conn):
    repo = NotifyQueueRepository()
    event = fresh()
    event.update(blocked=True, last_error="legacy_snapshot_incomplete")
    repo.insert(event, conn=db_conn)  # migration-shaped blocked record
    assert repo.retarget(event["event_id"], "8", actor="operator", reason="repair",
                         now=NOW, conn=db_conn)
    saved = record(repo, db_conn, event)
    assert saved["blocked"] is True
    assert saved["last_error"] == "legacy_snapshot_incomplete"


def test_missing_message_id_is_never_pruned(db_conn):
    repo = NotifyQueueRepository()
    event = fresh()
    event["delivered_at"] = NOW.isoformat()
    repo.insert(event, conn=db_conn)  # damaged acknowledgement retains evidence
    assert repo.prune_delivered(now=NOW + timedelta(days=8), conn=db_conn) == 0


def test_health_includes_blocked_and_leased_but_excludes_acknowledged(db_conn):
    repo = NotifyQueueRepository()
    event = fresh()
    repo.enqueue(event, conn=db_conn)
    claim = repo.claim_one("w", now=NOW, conn=db_conn)
    assert repo.health(now=NOW, conn=db_conn)["pending_count"] == 1
    repo.reschedule(event["event_id"], claim["lease_token"], now=NOW,
                    delay_s=900, error_code="permission_denied", blocked=True, conn=db_conn)
    assert repo.health(now=NOW + timedelta(seconds=901), conn=db_conn) == dict(
        pending_count=1, oldest_pending_age_seconds=901.0, blocked_count=1)
    assert repo.prune_delivered(now=NOW + timedelta(days=100), conn=db_conn) == 0
    later = NOW + timedelta(seconds=901)
    claim = repo.claim_one("w", now=later, conn=db_conn)
    repo.acknowledge(event["event_id"], claim["lease_token"], "222", now=later, conn=db_conn)
    assert repo.health(now=later, conn=db_conn) == dict(
        pending_count=0, oldest_pending_age_seconds=None, blocked_count=0)
    assert repo.prune_delivered(now=later + timedelta(days=6), conn=db_conn) == 0
    assert repo.prune_delivered(now=later + timedelta(days=8), conn=db_conn) == 1
