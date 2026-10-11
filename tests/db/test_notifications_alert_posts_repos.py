"""v152: plan_notifications claims/retry state and alert_posts (real Postgres, rolled back)."""
import datetime as dt

import pytest
import sqlalchemy as sa

from swingbot.core.db import schema
from swingbot.core.db.repositories.alert_posts import (
    ALERT_OUTCOMES, AlertPostsRepository, alert_posts_repo)
from swingbot.core.db.repositories.notifications import (
    MAX_ATTEMPTS, NotificationsRepository, notifications_repo)
from swingbot.core.db.repositories.plans import PlanRepository

UTC = dt.timezone.utc
T0 = dt.datetime(2026, 1, 2, 14, 0, tzinfo=UTC)   # well before any clock_timestamp() a run sees
DOC = {"transition": "tp1_partial", "detail": {"exit_price": 190.0, "r": 1.0}}


def _plan(db_conn, plan_id="P1"):
    PlanRepository().insert({"plan_id": plan_id, "ticker": "AAPL", "strategy": "RSI",
                             "horizon_key": "2w", "status": "ACTIVE",
                             "created_at": "2026-10-10T13:00:00+00:00"}, conn=db_conn)


def _age_all_claims(db_conn, at: dt.datetime) -> None:
    db_conn.execute(sa.update(schema.plan_notifications).values(updated_at=at))


def test_constants_and_singletons():
    assert MAX_ATTEMPTS == 5
    assert ALERT_OUTCOMES == ("posted", "suppressed")
    assert notifications_repo() is notifications_repo()
    assert alert_posts_repo() is alert_posts_repo()


def test_the_first_claim_wins_and_a_second_is_refused(db_conn):
    _plan(db_conn)
    repo = NotificationsRepository()
    assert repo.claim("P1", "tp1", DOC, conn=db_conn) is True
    assert repo.claim("P1", "tp1", {"transition": "closed", "detail": {}}, conn=db_conn) is False
    assert repo.claim("P1", "stopped", DOC, conn=db_conn) is True
    rows = {row["event"]: row for row in repo.list_all(conn=db_conn)}
    assert rows["tp1"]["state"] == "pending"
    assert rows["tp1"]["attempts"] == 0
    assert rows["tp1"]["transition"] == "tp1_partial"      # the first claim's doc is kept
    assert rows["tp1"]["detail"] == {"exit_price": 190.0, "r": 1.0}


def test_a_claim_for_a_missing_plan_is_rejected(db_conn):
    with pytest.raises(sa.exc.IntegrityError):
        NotificationsRepository().claim("GHOST", "tp1", DOC, conn=db_conn)


def test_claimed_keys_cover_every_state(db_conn):
    _plan(db_conn)
    repo = NotificationsRepository()
    repo.claim("P1", "tp1", DOC, conn=db_conn)
    repo.claim("P1", "near_stop", DOC, conn=db_conn)
    repo.mark_sent("P1", "tp1", conn=db_conn)
    assert repo.claimed_keys(conn=db_conn) == {("P1", "tp1"), ("P1", "near_stop")}


def test_pending_older_than_returns_old_pending_rows_only(db_conn):
    _plan(db_conn)
    repo = NotificationsRepository()
    repo.claim("P1", "tp1", DOC, conn=db_conn)
    repo.claim("P1", "near_stop", DOC, conn=db_conn)
    _age_all_claims(db_conn, T0)
    repo.mark_sent("P1", "near_stop", conn=db_conn)
    assert repo.pending_older_than(T0 - dt.timedelta(seconds=1), conn=db_conn) == []
    (row,) = repo.pending_older_than(T0 + dt.timedelta(seconds=60), conn=db_conn)
    assert (row["plan_id"], row["event"], row["state"]) == ("P1", "tp1", "pending")
    assert row["transition"] == "tp1_partial" and row["attempts"] == 0


def test_record_failure_counts_attempts_and_fails_at_the_limit(db_conn):
    _plan(db_conn)
    repo = NotificationsRepository()
    repo.claim("P1", "tp1", DOC, conn=db_conn)
    states = [repo.record_failure("P1", "tp1", conn=db_conn) for _ in range(MAX_ATTEMPTS)]
    assert states == ["pending"] * (MAX_ATTEMPTS - 1) + ["failed"]
    (row,) = repo.list_all(conn=db_conn)
    assert (row["state"], row["attempts"]) == ("failed", MAX_ATTEMPTS)
    assert row["transition"] == "tp1_partial"                # the doc merge keeps the detail
    assert repo.record_failure("P1", "tp1", conn=db_conn) == "failed"
    (row,) = repo.list_all(conn=db_conn)
    assert row["attempts"] == MAX_ATTEMPTS                   # a failed row is never bumped


def test_record_failure_refreshes_the_retry_age(db_conn):
    _plan(db_conn)
    repo = NotificationsRepository()
    repo.claim("P1", "tp1", DOC, conn=db_conn)
    _age_all_claims(db_conn, T0)
    repo.record_failure("P1", "tp1", conn=db_conn)
    assert repo.pending_older_than(T0 + dt.timedelta(seconds=60), conn=db_conn) == []


def test_record_failure_on_a_sent_or_missing_row_reports_failed(db_conn):
    _plan(db_conn)
    repo = NotificationsRepository()
    repo.claim("P1", "tp1", DOC, conn=db_conn)
    repo.mark_sent("P1", "tp1", conn=db_conn)
    assert repo.record_failure("P1", "tp1", conn=db_conn) == "failed"
    assert repo.record_failure("P1", "tp2", conn=db_conn) == "failed"
    (row,) = repo.list_all(conn=db_conn)
    assert row["state"] == "sent"


def test_record_failure_honours_a_custom_limit(db_conn):
    _plan(db_conn)
    repo = NotificationsRepository()
    repo.claim("P1", "tp1", DOC, conn=db_conn)
    assert repo.record_failure("P1", "tp1", max_attempts=1, conn=db_conn) == "failed"


def _post(repo, db_conn, at, *, ticker="AAPL", direction="bullish", horizon="2w",
          outcome="posted"):
    repo.add(ticker, at, outcome, direction=direction, horizon_key=horizon,
             plan_id=f"{ticker}-{at:%H%M}", conn=db_conn)


def test_posted_since_matches_the_full_key_inside_the_window(db_conn):
    repo = AlertPostsRepository()
    _post(repo, db_conn, T0)
    since = T0 - dt.timedelta(hours=24)
    assert repo.posted_since("AAPL", "bullish", "2w", since, conn=db_conn) is True
    assert repo.posted_since("AAPL", "bearish", "2w", since, conn=db_conn) is False
    assert repo.posted_since("AAPL", "bullish", "4w", since, conn=db_conn) is False
    assert repo.posted_since("MSFT", "bullish", "2w", since, conn=db_conn) is False
    assert repo.posted_since("AAPL", "bullish", "2w", T0 + dt.timedelta(seconds=1),
                             conn=db_conn) is False


def test_a_suppressed_row_never_opens_a_window(db_conn):
    repo = AlertPostsRepository()
    _post(repo, db_conn, T0, outcome="suppressed")
    assert repo.posted_since("AAPL", "bullish", "2w", T0 - dt.timedelta(hours=1),
                             conn=db_conn) is False


def test_count_since_counts_one_outcome(db_conn):
    repo = AlertPostsRepository()
    _post(repo, db_conn, T0 - dt.timedelta(days=2), outcome="suppressed")
    _post(repo, db_conn, T0, outcome="suppressed")
    _post(repo, db_conn, T0, ticker="MSFT", outcome="suppressed")
    _post(repo, db_conn, T0)
    since = T0 - dt.timedelta(hours=1)
    assert repo.count_since("suppressed", since, conn=db_conn) == 2
    assert repo.count_since("posted", since, conn=db_conn) == 1


def test_prune_before_deletes_only_older_rows(db_conn):
    repo = AlertPostsRepository()
    _post(repo, db_conn, T0 - dt.timedelta(days=8))
    _post(repo, db_conn, T0 - dt.timedelta(days=6), ticker="MSFT")
    assert repo.prune_before(T0 - dt.timedelta(days=7), conn=db_conn) == 1
    assert [row["ticker"] for row in repo.list_all(conn=db_conn)] == ["MSFT"]


def test_add_rejects_an_unknown_outcome_and_a_naive_time():
    repo = AlertPostsRepository()
    with pytest.raises(ValueError, match="held"):
        repo.add("AAPL", T0, "held", direction="bullish", horizon_key="2w", plan_id=None)
    with pytest.raises(ValueError, match="timezone"):
        repo.add("AAPL", T0.replace(tzinfo=None), "posted", direction="bullish",
                 horizon_key="2w", plan_id=None)
