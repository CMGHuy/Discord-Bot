"""v239: MarketRegimeRepository -- write once per session; the notice only from the
winning insert, in its transaction."""
import threading
from datetime import date, datetime, timedelta, timezone

import pytest
import sqlalchemy as sa

from swingbot.core.db.repositories import market_regime as mr
from swingbot.core.db.repositories.notify_queue import NotifyQueueRepository
from swingbot.core.infra.lifecycle_events import make_event

T0 = datetime(2026, 11, 18, 21, 5, tzinfo=timezone.utc)
D0 = date(2026, 11, 19)


def _row(day=D0, state="CORRECTION", **over) -> dict:
    base = dict(session_date=day, last_bar_date=day - timedelta(days=1), state=state,
                stress=True, pullback_trigger=False, pullback_reason=None, spy_close=650.0,
                sma50=700.0, sma200=690.0, sma50_lag5=705.0, sma200_lag20=680.0,
                spy_high_prev=655.0, vix_close=30.5, vix_max5=33.0, spy_provider="alpaca",
                vix_provider="yfinance", computed_at=T0, doc={"unknown_reason": None})
    return {**base, **over}


def _notice(transition="t-1", at=T0):
    payload = {"ticker": "AAPL", "direction": "bullish", "prior_status": "PENDING",
               "new_status": "CANCELLED", "reason": "probe", "occurred_at": at.isoformat(),
               "plan_id": "P-1"}
    return make_event(transition_id=transition, kind="plan_transition",
                      target_channel_id="123", occurred_at=at.isoformat(), payload=payload)


@pytest.fixture
def repo():
    return mr.MarketRegimeRepository()


def test_the_singleton_is_reused():
    assert mr.market_regime_repo() is mr.market_regime_repo()


def test_columns_and_states_are_the_classifier_row():
    assert mr.STATES == ("BEAR", "CORRECTION", "NORMAL", "UNKNOWN")
    assert len(mr.COLUMNS) == 16 and mr.COLUMNS[:3] == ("session_date", "last_bar_date", "state")


def test_an_empty_table_reads_as_nothing(repo, db_conn):
    assert repo.day(D0, conn=db_conn) is None
    assert repo.latest(conn=db_conn) is None
    assert repo.recent(conn=db_conn) == []


def test_a_row_round_trips(repo, db_conn):
    assert repo.insert_once(_row(), conn=db_conn) is True
    got = repo.day(D0, conn=db_conn)
    assert {k: got[k] for k in mr.COLUMNS} == {k: _row()[k] for k in mr.COLUMNS}
    assert got["computed_at"] == T0 and got["doc"] == {"unknown_reason": None}


def test_an_unknown_row_keeps_its_nulls_and_reason(repo, db_conn):
    row = {name: None for name in mr.COLUMNS} | dict(
        session_date=D0, state="UNKNOWN", pullback_trigger=False, computed_at=T0,
        doc={"unknown_reason": "short_history"})
    repo.insert_once(row, conn=db_conn)
    got = repo.day(D0, conn=db_conn)
    assert got["state"] == "UNKNOWN" and got["stress"] is None and got["spy_close"] is None
    assert got["last_bar_date"] is None and got["doc"] == {"unknown_reason": "short_history"}


def test_iso_strings_are_accepted(repo, db_conn):
    row = _row(session_date="2026-11-19", last_bar_date="2026-11-18",
               computed_at=T0.isoformat())
    repo.insert_once(row, conn=db_conn)
    got = repo.day(D0, conn=db_conn)
    assert got["last_bar_date"] == date(2026, 11, 18) and got["computed_at"] == T0


@pytest.mark.parametrize("over, error", [
    ({"computed_at": None}, "computed_at_required"),
    ({"computed_at": datetime(2026, 11, 18, 21, 5)}, "timezone_required"),
    ({"state": "SHOCK"}, "unknown regime state"),
    ({"session_date": None}, "session_date_required"),
])
def test_a_bad_row_is_refused_before_the_database(repo, over, error):
    with pytest.raises(ValueError, match=error):
        repo.insert_once(_row(**over), conn=object())   # never reached: not a connection


def test_a_second_insert_for_the_session_is_refused_and_changes_nothing(repo, db_conn):
    assert repo.insert_once(_row(), conn=db_conn) is True
    assert repo.insert_once(_row(spy_close=1.0, state="BEAR"), conn=db_conn) is False
    got = repo.day(D0, conn=db_conn)
    assert (got["state"], got["spy_close"]) == ("CORRECTION", 650.0)


def test_only_the_winning_insert_enqueues_its_notice(repo, db_conn):
    queue = NotifyQueueRepository()
    before = queue.count(conn=db_conn)
    assert repo.insert_once(_row(), notice_event=_notice("t-a"), conn=db_conn) is True
    assert repo.insert_once(_row(), notice_event=_notice("t-b"), conn=db_conn) is False
    assert queue.count(conn=db_conn) == before + 1


def test_a_notice_that_fails_rolls_the_row_back_with_it(repo, db_conn):
    bad = {**_notice(), "event_id": "not-the-identity"}
    with pytest.raises(ValueError):
        repo.insert_once(_row(), notice_event=bad, conn=db_conn)
    assert repo.day(D0, conn=db_conn) is None


def test_latest_and_recent_read_by_session(repo, db_conn):
    days = [D0 - timedelta(days=n) for n in (3, 0, 1, 2)]
    for day in days:
        repo.insert_once(_row(day), conn=db_conn)
    assert repo.latest(conn=db_conn)["session_date"] == D0
    assert repo.latest(before=D0, conn=db_conn)["session_date"] == D0 - timedelta(days=1)
    assert repo.latest(before=D0 - timedelta(days=3), conn=db_conn) is None
    assert [r["session_date"] for r in repo.recent(conn=db_conn)] == sorted(days)
    assert [r["session_date"] for r in repo.recent(2, conn=db_conn)] == sorted(days)[-2:]


def test_two_concurrent_writers_insert_once_and_enqueue_one_notice(db_engine, db_committed):
    repo, barrier, results = mr.MarketRegimeRepository(), threading.Barrier(2), {}

    def writer(name, spy_close):
        with db_engine.connect() as connection:
            barrier.wait(timeout=10)
            with connection.begin():
                results[name] = repo.insert_once(_row(spy_close=spy_close),
                                                 notice_event=_notice(f"t-{name}"),
                                                 conn=connection)

    threads = [threading.Thread(target=writer, args=args) for args in (("a", 650.0), ("b", 651.0))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert sorted(results.values()) == [False, True]
    winner = "a" if results["a"] else "b"
    assert repo.day(D0, conn=db_committed)["spy_close"] == {"a": 650.0, "b": 651.0}[winner]
    assert NotifyQueueRepository().count(conn=db_committed) == 1
    assert db_committed.execute(sa.text("SELECT count(*) FROM market_regime_days")).scalar() == 1
