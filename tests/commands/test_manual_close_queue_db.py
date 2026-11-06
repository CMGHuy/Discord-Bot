from datetime import datetime, timedelta, timezone

from swingbot.core.db.repositories.notify_queue import NotifyQueueRepository
from swingbot.core.infra.lifecycle_events import make_event

AT = datetime(2026, 10, 28, 12, tzinfo=timezone.utc)


def event(transition="transition-1", at=AT):
    payload = dict(ticker="NVDA", direction="bullish", plan_id="P1", trade_id=None,
                   prior_status="PENDING", new_status="CANCELLED", reason="manual",
                   occurred_at=at.isoformat())
    return make_event(transition_id=transition, kind="plan_transition", target_channel_id="5",
                      occurred_at=at.isoformat(), payload=payload)


def test_empty_queue_has_nothing_to_claim(db_conn):
    repo = NotifyQueueRepository()
    assert repo.claim_one("worker", now=AT, conn=db_conn) is None
    assert repo.pending(conn=db_conn) == 0
    assert not hasattr(repo, "drain")


def test_claim_retains_pending_until_acknowledged(db_conn):
    repo = NotifyQueueRepository()
    notice = event()
    repo.enqueue(notice, conn=db_conn)
    claimed = repo.claim_one("worker", now=AT, conn=db_conn)
    assert claimed["event_id"] == notice["event_id"]
    assert repo.pending(conn=db_conn) == 1
    assert repo.claim_one("another", now=AT, conn=db_conn) is None
    assert repo.acknowledge(claimed["event_id"], claimed["lease_token"], "42",
                            now=AT + timedelta(seconds=1), conn=db_conn)
    assert repo.pending(conn=db_conn) == 0
    assert repo.count(conn=db_conn) == 1  # retained receipt, not DELETE-on-send


def test_same_transition_deduplicates_distinct_transitions_do_not(db_conn):
    repo = NotifyQueueRepository()
    repo.enqueue(event(), conn=db_conn)
    repo.enqueue(event(), conn=db_conn)
    assert repo.pending(conn=db_conn) == 1
    repo.enqueue(event("transition-2"), conn=db_conn)
    assert repo.pending(conn=db_conn) == 2


def test_due_events_are_claimed_oldest_first(db_conn):
    repo = NotifyQueueRepository()
    newest = event("new", AT + timedelta(seconds=1))
    oldest = event("old", AT)
    repo.enqueue(newest, conn=db_conn)
    repo.enqueue(oldest, conn=db_conn)
    first = repo.claim_one("worker", now=AT + timedelta(seconds=2), conn=db_conn)
    second = repo.claim_one("worker", now=AT + timedelta(seconds=2), conn=db_conn)
    assert [first["event_id"], second["event_id"]] == [oldest["event_id"], newest["event_id"]]
    assert repo.pending(conn=db_conn) == 2
