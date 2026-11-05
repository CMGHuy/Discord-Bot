"""v201: the refresher's stores -- quote currencies, queue, marks, heartbeat."""
from datetime import datetime, timedelta, timezone

import sqlalchemy as sa

from swingbot.core.db.repositories import market_refresh as mr

UTC = timezone.utc
T0 = datetime(2026, 10, 28, 15, 0, tzinfo=UTC)
EPOCH = datetime(2000, 1, 1, tzinfo=UTC)


def test_quote_currency_due_honours_the_unknown_backoff(db_conn):
    repo = mr.QuoteCurrencyRepository()
    repo.put("aapl", "USD", "known", checked_at=T0, conn=db_conn)
    repo.put("ZZZ", None, "unknown", checked_at=T0, retry_after=T0 + timedelta(hours=6), conn=db_conn)
    assert repo.due(["AAPL", "ZZZ", "NEW"], T0 + timedelta(hours=1), conn=db_conn) == ["NEW"]
    assert repo.due(["AAPL", "zzz", "NEW"], T0 + timedelta(hours=6), conn=db_conn) == ["ZZZ", "NEW"]
    got = repo.get_many(["AAPL", "ZZZ", "NOPE"], conn=db_conn)
    assert got["AAPL"]["code"] == "USD" and got["AAPL"]["outcome"] == "known"
    assert got["ZZZ"]["code"] is None and got["ZZZ"]["retry_after"] == T0 + timedelta(hours=6)
    assert "NOPE" not in got


def test_enqueue_dedupes_pending_and_only_raises_urgency(db_conn):
    q = mr.RefreshQueueRepository()
    assert q.enqueue("quote", ["AAPL", "MSFT"], priority=2, conn=db_conn) == 2
    assert q.enqueue("quote", ["AAPL"], priority=2, conn=db_conn) == 0
    assert q.enqueue("quote", ["AAPL"], priority=0, conn=db_conn) == 0
    assert q.enqueue("quote", ["AAPL"], priority=1, conn=db_conn) == 0
    assert q.enqueue("snapshot", ["AAPL"], priority=2, conn=db_conn) == 1   # other kind
    taken = q.take(10, conn=db_conn)
    assert [(t["kind"], t["key"], t["priority"]) for t in taken] == [
        ("quote", "AAPL", 0), ("quote", "MSFT", 2), ("snapshot", "AAPL", 2)]
    assert q.take(10, conn=db_conn) == []
    assert q.enqueue("quote", ["AAPL"], priority=2, conn=db_conn) == 1      # taken row no longer blocks
    assert q.enqueue("quote", [], priority=2, conn=db_conn) == 0


def test_take_respects_the_limit_and_prune_drops_old_rows(db_conn):
    q = mr.RefreshQueueRepository()
    q.enqueue("quote", ["A", "B", "C"], priority=2, conn=db_conn)
    assert len(q.take(2, conn=db_conn)) == 2
    assert q.prune(EPOCH, conn=db_conn) == 0
    assert q.prune(datetime.now(UTC) + timedelta(seconds=5), conn=db_conn) == 3


def test_marks_expire_after_timeout(db_conn):
    m = mr.RefreshMarkRepository()
    m.mark(["quote:AAPL", "quote:MSFT"], timeout_s=120, now=T0, conn=db_conn)
    keys = ["quote:AAPL", "quote:MSFT", "quote:X"]
    assert m.active(keys, now=T0 + timedelta(seconds=119), conn=db_conn) == {"quote:AAPL", "quote:MSFT"}
    assert m.active(keys, now=T0 + timedelta(seconds=121), conn=db_conn) == set()


def test_clear_keeps_the_row_with_its_error_until_the_next_mark(db_conn):
    m = mr.RefreshMarkRepository()
    m.mark(["quote:AAPL"], timeout_s=120, now=T0, conn=db_conn)
    m.clear(["quote:AAPL"], error="no quote", now=T0 + timedelta(seconds=5), conn=db_conn)
    assert m.active(["quote:AAPL"], now=T0 + timedelta(seconds=6), conn=db_conn) == set()
    assert m.errors(["quote:AAPL", "quote:X"], conn=db_conn) == {"quote:AAPL": "no quote"}
    [row] = m.changed_since(EPOCH, now=T0 + timedelta(seconds=6), conn=db_conn)
    assert (row["key"], row["in_flight"], row["error"]) == ("quote:AAPL", False, "no quote")
    m.mark(["quote:AAPL"], timeout_s=120, now=T0 + timedelta(seconds=10), conn=db_conn)
    assert m.errors(["quote:AAPL"], conn=db_conn) == {}
    [row] = m.changed_since(EPOCH, now=T0 + timedelta(seconds=11), conn=db_conn)
    assert row["in_flight"] is True


def test_heartbeat_is_one_upserted_row(db_conn):
    h = mr.RefresherHeartbeatRepository()
    assert h.read(conn=db_conn) is None
    h.beat(cadence_s=30, session="regular", cycle_ms=850, last_error=None, now=T0, conn=db_conn)
    h.beat(cadence_s=300, session="extended", cycle_ms=None, last_error="boom",
           now=T0 + timedelta(seconds=30), conn=db_conn)
    assert h.read(conn=db_conn) == {"beat_at": T0 + timedelta(seconds=30), "cadence_s": 300.0,
                                    "session": "extended", "cycle_ms": None, "last_error": "boom"}
    assert db_conn.execute(sa.text("select count(*) from refresher_heartbeat")).scalar() == 1


def test_accessors_are_singletons():
    for accessor in (mr.quote_currency_repo, mr.refresh_queue_repo,
                     mr.refresh_mark_repo, mr.refresher_heartbeat_repo):
        assert accessor() is accessor()
