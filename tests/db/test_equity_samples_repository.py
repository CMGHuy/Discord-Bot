"""v172: EquitySampleRepository -- money rounded once at the write, the
(at, source, kind) key, backfill replace in one transaction, NY session dates."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
import sqlalchemy as sa

from swingbot.core.db.repositories.equity_samples import (
    EquitySampleRepository, equity_samples_repo, round_money)
from swingbot.core.db.schema import equity_samples

UTC = timezone.utc
OPEN = datetime(2026, 10, 15, 13, 30, tzinfo=UTC)     # 09:30 New York (EDT)
CLOSE = datetime(2026, 10, 15, 20, 0, tzinfo=UTC)     # 16:00 New York


@pytest.fixture
def repo():
    return EquitySampleRepository()


def _row(at, *, source="live", kind="point", equity=Decimal("10100.005"), run=None, skipped=0):
    return {"at": at, "realized_balance": Decimal("10000"), "unrealized_pnl": equity - 10000,
            "equity": equity, "open_n": 2, "skipped_n": skipped, "source": source, "kind": kind,
            "backfill_run": run}


def test_round_money_is_half_up_from_the_decimal_string():
    assert round_money(Decimal("1.005")) == 1.01
    assert round_money(2.675) == 2.68          # float round() would give 2.67
    assert round_money(Decimal("-1.005")) == -1.01
    assert isinstance(round_money(Decimal("3")), float)


def test_insert_sample_rounds_money_once_and_returns_the_id(repo, db_conn):
    sample_id = repo.insert_sample(_row(OPEN), conn=db_conn)
    assert sample_id > 0
    (row,) = repo.list_rows(conn=db_conn)
    assert row["id"] == sample_id
    assert (row["equity"], row["unrealized_pnl"], row["realized_balance"]) == (10100.01, 100.01, 10000.0)
    assert row["at"] == OPEN and row["at"].utcoffset() == timedelta(0)
    assert (row["open_n"], row["skipped_n"], row["source"], row["kind"]) == (2, 0, "live", "point")


def test_a_second_sample_on_the_same_key_writes_nothing(repo, db_conn):
    assert repo.insert_sample(_row(OPEN), conn=db_conn) > 0
    assert repo.insert_sample(_row(OPEN, equity=Decimal("1")), conn=db_conn) == 0
    (row,) = repo.list_rows(conn=db_conn)
    assert row["equity"] == 10100.01


@pytest.mark.parametrize("field, value", [("source", "guess"), ("kind", "close")])
def test_an_unknown_source_or_kind_is_refused(repo, db_conn, field, value):
    with pytest.raises(ValueError):
        repo.insert_sample({**_row(OPEN), field: value}, conn=db_conn)


def test_upsert_many_updates_on_the_unique_key(repo, db_conn):
    first = [_row(OPEN, source="backfill", run="r1"),
             _row(OPEN, source="backfill", kind="day_high", equity=Decimal("10300"), run="r1")]
    assert repo.upsert_many(first, conn=db_conn) == 2
    assert repo.upsert_many([_row(OPEN, source="backfill", equity=Decimal("9990"), run="r2")],
                            conn=db_conn) == 1
    rows = {row["kind"]: row for row in repo.list_rows(conn=db_conn)}
    assert (rows["point"]["equity"], rows["point"]["backfill_run"]) == (9990.0, "r2")
    assert rows["day_high"]["backfill_run"] == "r1"
    assert repo.upsert_many([], conn=db_conn) == 0


def test_replace_backfill_drops_every_backfill_row_and_keeps_live(repo, db_conn):
    repo.insert_sample(_row(CLOSE + timedelta(days=1)), conn=db_conn)
    repo.upsert_many([_row(OPEN, source="backfill", run="old"),
                      _row(CLOSE, source="backfill", run="old")], conn=db_conn)
    assert repo.replace_backfill([_row(CLOSE, source="backfill", run="new")], conn=db_conn) == 1
    rows = repo.list_rows(conn=db_conn)
    assert [(r["source"], r.get("backfill_run")) for r in rows] == [("backfill", "new"), ("live", None)]   # a NULL column reads back absent


def test_replace_backfill_refuses_a_live_row(repo, db_conn):
    with pytest.raises(ValueError):
        repo.replace_backfill([_row(OPEN)], conn=db_conn)


def test_latest_and_earliest_are_per_source(repo, db_conn):
    assert repo.latest_at("live", conn=db_conn) is None
    assert repo.earliest_at("live", conn=db_conn) is None
    repo.insert_sample(_row(OPEN), conn=db_conn)
    repo.insert_sample(_row(CLOSE), conn=db_conn)
    repo.upsert_many([_row(OPEN - timedelta(days=3), source="backfill")], conn=db_conn)
    assert repo.earliest_at("live", conn=db_conn) == OPEN
    assert repo.latest_at("live", conn=db_conn) == CLOSE
    assert repo.earliest_at("backfill", conn=db_conn) == OPEN - timedelta(days=3)


def test_list_rows_filters_by_source_and_since_in_time_order(repo, db_conn):
    repo.insert_sample(_row(CLOSE), conn=db_conn)
    repo.insert_sample(_row(OPEN), conn=db_conn)
    repo.upsert_many([_row(OPEN - timedelta(days=1), source="backfill")], conn=db_conn)
    assert [r["at"] for r in repo.list_rows(conn=db_conn)] == [OPEN - timedelta(days=1), OPEN, CLOSE]
    assert [r["at"] for r in repo.list_rows(sources=("live",), conn=db_conn)] == [OPEN, CLOSE]
    assert [r["at"] for r in repo.list_rows(since=CLOSE, conn=db_conn)] == [CLOSE]


def test_backfill_session_dates_are_new_york_dates(repo, db_conn):
    late = datetime(2026, 10, 17, 2, 0, tzinfo=UTC)          # 22:00 New York on the 16th
    repo.upsert_many([_row(OPEN, source="backfill"), _row(late, source="backfill")], conn=db_conn)
    repo.insert_sample(_row(datetime(2026, 10, 20, 14, 0, tzinfo=UTC)), conn=db_conn)
    assert repo.backfill_session_dates(conn=db_conn) == {date(2026, 10, 15), date(2026, 10, 16)}


def test_update_realized_rewrites_only_the_realized_columns(repo, db_conn):
    sample_id = repo.insert_sample(_row(OPEN), conn=db_conn)
    repo.update_realized(sample_id, Decimal("9000.004"), Decimal("9100.015"), conn=db_conn)
    (row,) = repo.list_rows(conn=db_conn)
    assert (row["realized_balance"], row["equity"], row["unrealized_pnl"]) == (9000.0, 9100.02, 100.01)


def test_the_accessor_is_a_singleton():
    assert equity_samples_repo() is equity_samples_repo()


def _columns(db_conn, sample_id):
    table = equity_samples
    return db_conn.execute(sa.select(table.c.open_notional, table.c.open_notional_approx,
                                     table.c.doc).where(table.c.id == sample_id)).one()


def test_open_notional_is_rounded_once_and_lands_in_its_own_column(repo, db_conn):
    sample_id = repo.insert_sample({**_row(OPEN), "open_notional": Decimal("2040.005"),
                                    "open_notional_approx": False}, conn=db_conn)
    stored = _columns(db_conn, sample_id)
    assert (stored.open_notional, stored.open_notional_approx) == (2040.01, False)
    assert "open_notional" not in stored.doc and "open_notional_approx" not in stored.doc
    (row,) = repo.list_rows(conn=db_conn)
    assert (row["open_notional"], row["open_notional_approx"]) == (2040.01, False)


def test_a_row_written_without_open_notional_reads_back_without_it(repo, db_conn):
    sample_id = repo.insert_sample(_row(OPEN), conn=db_conn)
    stored = _columns(db_conn, sample_id)
    assert (stored.open_notional, stored.open_notional_approx) == (None, None)
    (row,) = repo.list_rows(conn=db_conn)
    assert row.get("open_notional") is None and row.get("open_notional_approx") is None


def test_update_open_notional_touches_only_the_two_new_columns(repo, db_conn):
    sample_id = repo.insert_sample(_row(CLOSE), conn=db_conn)
    (before,) = repo.list_rows(conn=db_conn)
    repo.update_open_notional(sample_id, Decimal("975.004"), True, conn=db_conn)
    (after,) = repo.list_rows(conn=db_conn)
    assert (after["open_notional"], after["open_notional_approx"]) == (975.0, True)
    keep = ("realized_balance", "unrealized_pnl", "equity", "open_n", "skipped_n",
            "source", "kind", "at")
    assert {k: after[k] for k in keep} == {k: before[k] for k in keep}
    repo.update_open_notional(sample_id, None, None, conn=db_conn)       # the rollback shape
    (reset,) = repo.list_rows(conn=db_conn)
    assert reset.get("open_notional") is None and reset.get("open_notional_approx") is None
