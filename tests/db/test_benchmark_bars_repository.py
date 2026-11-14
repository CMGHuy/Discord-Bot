"""v208: benchmark session bars and the once-per-session-day full-refresh guard."""
from datetime import date, datetime, timedelta, timezone

import pytest

from swingbot.core.db.repositories import benchmark_bars as bb

AS_OF = datetime(2026, 11, 4, 21, 5, tzinfo=timezone.utc)
MON, TUE, WED = date(2026, 11, 2), date(2026, 11, 3), date(2026, 11, 4)


def _bar(symbol, session, *, close=None, adj=None, pct=None, source=None, final=True, at=AS_OF):
    return {"symbol": symbol, "session": session, "close": close, "adj_close": adj,
            "day_pct": pct, "source_symbol": source or symbol, "final": final, "as_of": at}


@pytest.fixture
def bars():
    return bb.BenchmarkBarRepository()


def test_upsert_then_list_range_returns_every_key_nulls_included(bars, db_conn):
    assert bars.upsert_bars([_bar("SPY", TUE, close=580.0, adj=579.1, pct=0.004),
                             _bar("^DJI", TUE, pct=-0.002, source="DIA")], conn=db_conn) == 2
    rows = bars.list_range(["SPY", "^DJI"], MON, WED, conn=db_conn)
    assert [(r["symbol"], r["session"]) for r in rows] == [("SPY", TUE), ("^DJI", TUE)]
    assert all(set(bb.BAR_KEYS) <= set(r) for r in rows)
    dji = rows[1]
    assert (dji["close"], dji["adj_close"], dji["day_pct"], dji["source_symbol"]) == (
        None, None, -0.002, "DIA")
    assert rows[0]["as_of"] == AS_OF and rows[0]["as_of"].utcoffset() == timedelta(0)


def test_list_range_exposes_the_database_update_time(bars, db_conn):
    before = datetime.now(timezone.utc) - timedelta(seconds=1)
    bars.upsert_bars([_bar("SPY", TUE, close=580.0)], conn=db_conn)
    (row,) = bars.list_range(["SPY"], TUE, TUE, conn=db_conn)
    after = datetime.now(timezone.utc) + timedelta(seconds=1)
    assert before <= row["updated_at"] <= after
    assert row["updated_at"].utcoffset() == timedelta(0)


def test_a_proxy_day_overwrites_a_level_day_and_clears_its_close(bars, db_conn):
    bars.upsert_bars([_bar("^IXIC", WED, close=18500.0, pct=0.01, final=False)], conn=db_conn)
    bars.upsert_bars([_bar("^IXIC", WED, pct=0.009, source="ONEQ")], conn=db_conn)
    (row,) = bars.list_range(["^IXIC"], WED, WED, conn=db_conn)
    assert (row["close"], row["day_pct"], row["source_symbol"], row["final"]) == (
        None, 0.009, "ONEQ", True)


def test_a_duplicate_key_inside_one_batch_keeps_the_last_row(bars, db_conn):
    written = bars.upsert_bars([_bar("SPY", WED, adj=1.0, pct=0.001, final=False),
                                _bar("SPY", WED, adj=2.0, pct=0.002)], conn=db_conn)
    assert written == 1
    (row,) = bars.list_range(["SPY"], WED, WED, conn=db_conn)
    assert (row["adj_close"], row["day_pct"], row["final"]) == (2.0, 0.002, True)


def test_nothing_to_write_writes_nothing(bars, db_conn):
    assert bars.upsert_bars([], conn=db_conn) == 0
    assert bars.list_range([], MON, WED, conn=db_conn) == []


def test_list_range_is_inclusive_filtered_and_ordered(bars, db_conn):
    bars.upsert_bars([_bar("QQQ", WED, pct=0.0), _bar("QQQ", MON, pct=0.0),
                      _bar("SPY", TUE, pct=0.0), _bar("QQQ", TUE, pct=0.0)], conn=db_conn)
    rows = bars.list_range(["QQQ"], MON, TUE, conn=db_conn)
    assert [(r["symbol"], r["session"]) for r in rows] == [("QQQ", MON), ("QQQ", TUE)]


def test_last_session_counts_final_rows_of_that_symbol_only(bars, db_conn):
    assert bars.last_session("SPY", conn=db_conn) is None
    bars.upsert_bars([_bar("SPY", TUE, pct=0.0), _bar("SPY", WED, pct=0.0, final=False),
                      _bar("QQQ", WED, pct=0.0)], conn=db_conn)
    assert bars.last_session("SPY", conn=db_conn) == TUE


def test_iso_strings_are_accepted_for_session_and_as_of(bars, db_conn):
    bars.upsert_bars([_bar("SPY", "2026-11-04", pct=0.0, at="2026-11-04T22:05:00+01:00")],
                     conn=db_conn)
    (row,) = bars.list_range(["SPY"], WED, WED, conn=db_conn)
    assert (row["session"], row["as_of"]) == (WED, AS_OF)
    assert row["as_of"].utcoffset() == timedelta(0)


@pytest.mark.parametrize("bad", [{"source_symbol": ""}, {"symbol": None}, {"final": "yes"},
                                 {"as_of": datetime(2026, 11, 4, 21, 5)}, {"session": None}])
def test_a_bad_row_is_refused(bars, db_conn, bad):
    with pytest.raises(ValueError):
        bars.upsert_bars([{**_bar("SPY", WED, pct=0.0), **bad}], conn=db_conn)


def test_upsert_returns_the_stored_row(bars, db_conn):
    stored = bars.upsert({**_bar("SPY", WED, pct=0.003), "note": "x"}, conn=db_conn)
    assert (stored["session"], stored["day_pct"], stored["note"]) == (WED, 0.003, "x")


def test_the_refresh_guard_is_one_overwritable_date_per_symbol(db_conn):
    guard = bb.BenchmarkRefreshRepository()
    assert guard.full_refreshed_on("SPY", conn=db_conn) is None
    guard.mark_full_refresh("SPY", TUE, conn=db_conn)
    guard.mark_full_refresh("SPY", WED, conn=db_conn)
    assert guard.full_refreshed_on("SPY", conn=db_conn) == WED
    assert guard.full_refreshed_on("QQQ", conn=db_conn) is None


def test_the_accessors_are_singletons():
    assert bb.benchmark_bars_repo() is bb.benchmark_bars_repo()
    assert bb.benchmark_refresh_repo() is bb.benchmark_refresh_repo()
    assert isinstance(bb.benchmark_refresh_repo(), bb.BenchmarkRefreshRepository)
