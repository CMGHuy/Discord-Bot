"""v171 D1/D6/D9: shared cache rows, leases, the shared token bucket and breaker, counts."""
from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa

from swingbot.core.db import events, schema
from swingbot.core.db.repositories import market_shared as store
from swingbot.core.db.repositories.market_shared import MarketSharedRepository

T0 = datetime(2026, 10, 16, 14, 0, tzinfo=timezone.utc)


@pytest.fixture
def repo():
    return MarketSharedRepository()


def _row(key="quote:AAPL:", value=None):
    return {"key": key, "kind": "quote", "symbol": key.split(":")[1], "fetched_at": T0,
            "source": "alpaca", "value": value if value is not None else {"price": 1.5}}


def test_write_then_read_many_keys_in_one_statement(repo, db_conn):
    repo.write_entries([_row(), _row("quote:MSFT:", {"price": 2.0})], conn=db_conn)
    got = repo.read_entries(["quote:AAPL:", "quote:MSFT:", "quote:NOPE:"], conn=db_conn)
    assert set(got) == {"quote:AAPL:", "quote:MSFT:"}
    assert got["quote:MSFT:"]["value"] == {"price": 2.0}
    assert got["quote:AAPL:"]["fetched_at"] == T0
    assert repo.read_entries([], conn=db_conn) == {}


def test_lease_is_exclusive_until_released_or_expired(repo, db_conn):
    assert repo.try_lease("quote:AAPL:", "A", 30, kind="quote", symbol="AAPL", conn=db_conn)
    assert not repo.try_lease("quote:AAPL:", "B", 30, kind="quote", symbol="AAPL", conn=db_conn)
    assert repo.try_lease("quote:AAPL:", "A", 30, kind="quote", symbol="AAPL", conn=db_conn)
    repo.release_lease("quote:AAPL:", "B", conn=db_conn)          # not B's: no effect
    assert not repo.try_lease("quote:AAPL:", "B", 30, kind="quote", symbol="AAPL", conn=db_conn)
    repo.release_lease("quote:AAPL:", "A", conn=db_conn)
    assert repo.try_lease("quote:AAPL:", "B", 30, kind="quote", symbol="AAPL", conn=db_conn)


def test_an_expired_lease_is_taken_by_the_next_asker(repo, db_conn):
    assert repo.try_lease("quote:AAPL:", "dead", 0.01, kind="quote", symbol="AAPL", conn=db_conn)
    db_conn.execute(sa.text("select pg_sleep(0.05)"))
    assert repo.try_lease("quote:AAPL:", "B", 30, kind="quote", symbol="AAPL", conn=db_conn)


def test_writing_a_value_clears_the_lease(repo, db_conn):
    repo.try_lease("quote:AAPL:", "A", 30, kind="quote", symbol="AAPL", conn=db_conn)
    repo.write_entries([_row()], conn=db_conn)
    row = repo.read_entries(["quote:AAPL:"], conn=db_conn)["quote:AAPL:"]
    assert row["lease_holder"] is None and row["lease_until"] is None


def test_take_token_respects_capacity_and_reserve(repo, db_conn):
    takes = [repo.take_token("alpaca", 3, 0, 0, conn=db_conn) for _ in range(4)]
    assert takes == [True, True, True, False]
    reserved = [repo.take_token("yfinance", 4, 0, 2, conn=db_conn) for _ in range(3)]
    assert reserved == [True, True, False]           # 4->3->2, a third would leave 1 < 2
    assert repo.take_token("yfinance", 4, 0, 0, conn=db_conn) is True    # tier 1-3: reserve 0


def test_take_token_refills_with_elapsed_time(repo, db_conn):
    assert [repo.take_token("alpaca", 1, 60, 0, conn=db_conn) for _ in range(2)] == [True, False]
    db_conn.execute(sa.text(
        "update provider_budget set stamp = stamp - interval '2 seconds' where provider='alpaca'"))
    assert repo.take_token("alpaca", 1, 60, 0, conn=db_conn) is True


def test_breaker_opens_after_n_failures_and_success_resets_the_count(repo, db_conn):
    assert repo.breaker_state("alpaca", conn=db_conn) == (0, None)
    for _ in range(2):
        repo.breaker_record("alpaca", False, 3, 300, conn=db_conn)
    assert repo.breaker_state("alpaca", conn=db_conn)[1] is None
    repo.breaker_record("alpaca", False, 3, 300, conn=db_conn)
    fails, open_until = repo.breaker_state("alpaca", conn=db_conn)
    assert fails == 3 and open_until > datetime.now(timezone.utc) + timedelta(seconds=290)
    repo.breaker_record("alpaca", True, 3, 300, conn=db_conn)
    assert repo.breaker_state("alpaca", conn=db_conn)[0] == 0


def test_a_breaker_row_created_first_leaves_the_bucket_full(repo, db_conn):
    repo.breaker_record("alpaca", False, 3, 300, conn=db_conn)
    assert repo.take_token("alpaca", 5, 5, 0, conn=db_conn) is True


def test_counts_increment_per_hour_and_key(repo, db_conn):
    row = (T0, "alpaca", "quote", "scan", "hit", 2)
    repo.add_counts([row], conn=db_conn)
    repo.add_counts([row, (T0, "alpaca", "quote", "scan", "fetched", 1)], conn=db_conn)
    got = repo.count_rows(T0, T0 + timedelta(hours=1), conn=db_conn)
    assert {(r["outcome"], r["n"]) for r in got} == {("hit", 4), ("fetched", 1)}
    assert repo.count_rows(T0 + timedelta(hours=1), T0 + timedelta(hours=2), conn=db_conn) == []


def test_tables_stream_no_sse_and_the_accessor_is_a_singleton():
    for name in ("market_cache", "provider_budget", "market_fetch_counts"):
        assert name in schema.METADATA.tables and name not in events.TABLE_CHANNELS
    assert store.market_shared_repo() is store.market_shared_repo()
