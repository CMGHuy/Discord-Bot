"""v227: FeedPostsRepository -- the simple-channel post log the site speaks from."""
from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa

from swingbot.core.db import schema
from swingbot.core.db.repositories import feed_posts as fp


@pytest.fixture
def repo():
    return fp.FeedPostsRepository()


def _age(conn, row_id: int, days: float) -> None:
    conn.execute(sa.update(schema.feed_posts).where(schema.feed_posts.c.id == row_id)
                 .values(posted_at=sa.func.now() - timedelta(days=days)))


def test_insert_returns_the_new_id_and_stores_the_promoted_fields(repo, db_conn):
    first = repo.insert("FILLED", "MSFT", "Order filled, MSFT", conn=db_conn)
    second = repo.insert("CANCEL", None, "Order cancelled", conn=db_conn)
    assert second > first
    row = db_conn.execute(sa.select(schema.feed_posts).where(
        schema.feed_posts.c.id == first)).one()._mapping
    assert (row["kind"], row["ticker"], row["headline"]) == ("FILLED", "MSFT", "Order filled, MSFT")
    assert row["doc"] == {}
    assert row["posted_at"].tzinfo is not None


def test_after_pages_oldest_first_and_honours_the_limit(repo, db_conn):
    ids = [repo.insert("FILLED", t, f"Order filled, {t}", conn=db_conn) for t in ("A", "B", "C")]
    page = repo.after(ids[0], 10, conn=db_conn)
    assert [r["id"] for r in page] == ids[1:]
    assert set(page[0]) == {"id", "posted_at", "kind", "ticker", "headline"}
    assert isinstance(page[0]["posted_at"], datetime) and page[0]["posted_at"].tzinfo is not None
    assert [r["ticker"] for r in repo.after(0, 2, conn=db_conn)] == ["A", "B"]


def test_after_the_newest_id_is_empty(repo, db_conn):
    newest = repo.insert("FILLED", "A", "Order filled, A", conn=db_conn)
    assert repo.after(newest, 20, conn=db_conn) == []


def test_latest_id_is_zero_on_an_empty_table_then_the_newest_id(repo, db_conn):
    assert repo.latest_id(conn=db_conn) == 0
    repo.insert("FILLED", "A", "Order filled, A", conn=db_conn)
    newest = repo.insert("WIN", "B", "Winner, B", conn=db_conn)
    assert repo.latest_id(conn=db_conn) == newest


def test_prune_removes_only_rows_older_than_the_window(repo, db_conn):
    old = repo.insert("FILLED", "OLD", "Order filled, OLD", conn=db_conn)
    edge = repo.insert("FILLED", "EDGE", "Order filled, EDGE", conn=db_conn)
    fresh = repo.insert("FILLED", "NEW", "Order filled, NEW", conn=db_conn)
    _age(db_conn, old, 8)
    _age(db_conn, edge, 6.9)
    assert repo.prune(7, conn=db_conn) == 1
    assert [r["id"] for r in repo.after(0, 50, conn=db_conn)] == [edge, fresh]


class _Statements:
    """Every SQL statement the connection's engine runs while installed."""

    def __init__(self, conn):
        self.engine, self.seen = conn.engine, []

    def __enter__(self):
        sa.event.listen(self.engine, "before_cursor_execute", self._record)
        return self.seen

    def __exit__(self, *exc):
        sa.event.remove(self.engine, "before_cursor_execute", self._record)

    def _record(self, conn, cursor, statement, parameters, context, executemany):
        self.seen.append(statement.strip().upper())


def test_prune_with_nothing_old_issues_no_delete(repo, db_conn):
    repo.insert("FILLED", "NEW", "Order filled, NEW", conn=db_conn)
    with _Statements(db_conn) as seen:
        assert repo.prune(7, conn=db_conn) == 0
    assert seen and not any(s.startswith("DELETE") for s in seen)


def test_prune_on_an_empty_table_issues_no_delete(repo, db_conn):
    with _Statements(db_conn) as seen:
        assert repo.prune(7, conn=db_conn) == 0
    assert not any(s.startswith("DELETE") for s in seen)


def test_prune_with_an_old_row_issues_exactly_one_delete(repo, db_conn):
    _age(db_conn, repo.insert("FILLED", "OLD", "Order filled, OLD", conn=db_conn), 30)
    with _Statements(db_conn) as seen:
        assert repo.prune(7, conn=db_conn) == 1
    assert sum(s.startswith("DELETE") for s in seen) == 1


def test_reads_without_a_connection_use_the_store_engine(repo, db_engine):
    # conn=None goes through swingbot.core.db.engine.get_engine, which the
    # autouse _store_database fixture points at this worker's test database.
    assert repo.latest_id() == 0
    assert repo.after(0, 5) == []


def test_the_module_singleton_is_one_instance():
    assert fp.feed_posts_repo() is fp.feed_posts_repo()
    assert isinstance(fp.feed_posts_repo(), fp.FeedPostsRepository)
