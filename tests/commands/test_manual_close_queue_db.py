"""A queue the admin writes and the bot drains, exactly once."""
import pytest

from swingbot.core.db.repositories.notify_queue import NotifyQueueRepository


@pytest.fixture
def repo():
    return NotifyQueueRepository()


def test_an_empty_queue_drains_to_nothing(repo, db_conn):
    assert repo.drain(conn=db_conn) == []


def test_enqueue_then_drain(repo, db_conn):
    repo.enqueue({"trade_id": "T1", "reason": "manual"}, conn=db_conn)
    assert [row["trade_id"] for row in repo.drain(conn=db_conn)] == ["T1"]


def test_draining_removes_the_entries(repo, db_conn):
    repo.enqueue({"trade_id": "T1"}, conn=db_conn)
    repo.drain(conn=db_conn)
    assert repo.drain(conn=db_conn) == []


def test_the_same_trade_can_be_queued_twice(repo, db_conn):
    repo.enqueue({"trade_id": "T1"}, conn=db_conn)
    repo.enqueue({"trade_id": "T1"}, conn=db_conn)
    assert len(repo.drain(conn=db_conn)) == 2


def test_drain_is_oldest_first(repo, db_conn):
    for index in range(3):
        repo.enqueue({"trade_id": f"T{index}"}, conn=db_conn)
    assert [row["trade_id"] for row in repo.drain(conn=db_conn)] == ["T0", "T1", "T2"]


def test_pending_counts_without_draining(repo, db_conn):
    repo.enqueue({"trade_id": "T1"}, conn=db_conn)
    assert repo.pending(conn=db_conn) == 1
    assert repo.pending(conn=db_conn) == 1
