"""v184: MONITOR_SQL from heartbeat_watch.sh against a real Postgres.

The query is read out of the script, so this pins the exact string cron runs.
Each test writes the bot_heartbeat row inside a rolled-back transaction, and
computes every expected age from the transaction's own now(). Skips when the
test database is not up (docker compose --profile test up -d db-test)."""
import datetime as dt
import json
import math
import re
from zoneinfo import ZoneInfo

import sqlalchemy as sa

from tests.scripts.test_heartbeat_watch import SCRIPT

NY = ZoneInfo("America/New_York")
MONITOR_SQL = re.search(r'^MONITOR_SQL="(.*)"$', SCRIPT.read_text(encoding="utf-8"), re.M).group(1)


def _now(conn):
    return conn.execute(sa.text("SELECT now()")).scalar_one()


def _ago(now, seconds):
    """A whole-second instant `seconds` before now (the stamp writes whole seconds)."""
    return (now - dt.timedelta(seconds=seconds)).replace(microsecond=0)


def _iso(ts):
    return ts.astimezone(dt.timezone.utc).isoformat(timespec="seconds")


def _today_open(now):
    return dt.datetime.combine(now.astimezone(NY).date(), dt.time(9, 30), tzinfo=NY)


def _age(now, then):
    return math.floor((now - then).total_seconds())


def _monitor(now, **over):
    doc = {"started_at": _iso(_ago(now, 90000)), "tick_at": _iso(_ago(now, 42)),
           "outcome": "ok", "positions": ["AAPL", "MSFT", "NVDA"],
           "unquoted": ["AAPL", "MSFT"], "unquoted_count": 2, "fetch_failed": True,
           "check_errors": ["<plan manager>"], "priced_at": _iso(_ago(now, 700)),
           "market_open": True}
    doc.update(over)
    return doc


def _put(conn, doc):
    conn.execute(sa.text("DELETE FROM bot_heartbeat"))
    conn.execute(sa.text("INSERT INTO bot_heartbeat (key, ts, doc) "
                         "VALUES ('bot', now(), CAST(:doc AS jsonb))"), {"doc": json.dumps(doc)})


def _query(conn):
    return conn.exec_driver_sql(MONITOR_SQL).scalar_one_or_none()


def test_no_row_reads_as_nothing(db_conn):
    db_conn.execute(sa.text("DELETE FROM bot_heartbeat"))
    assert _query(db_conn) is None


def test_a_row_without_the_monitor_key_reads_absent(db_conn):
    _put(db_conn, {"timestamp": _iso(_now(db_conn))})
    assert _query(db_conn) == "absent"


def test_a_full_monitor_key_reads_as_one_row_of_eight_fields(db_conn):
    now = _now(db_conn)
    tick, priced = _ago(now, 42), _ago(now, 700)
    _put(db_conn, {"timestamp": _iso(now),
                   "monitor": _monitor(now, tick_at=_iso(tick), priced_at=_iso(priced))})
    fields = _query(db_conn).split("|")
    assert len(fields) == 8
    assert fields[0] == str(_age(now, tick))
    assert fields[1] == str(_age(now, max(priced, _today_open(now))))
    assert fields[2:] == ["true", "3", "2", "AAPL,MSFT", "true", "<plan manager>"]


def test_a_null_priced_at_counts_from_started_at(db_conn):
    now = _now(db_conn)
    started = _ago(now, 120)
    _put(db_conn, {"monitor": _monitor(now, priced_at=None, started_at=_iso(started))})
    fields = _query(db_conn).split("|")
    assert fields[1] == str(_age(now, max(started, _today_open(now))))


def test_yesterdays_priced_at_counts_from_todays_open(db_conn):
    now = _now(db_conn)
    priced = _ago(now, 2 * 86400)
    _put(db_conn, {"monitor": _monitor(now, priced_at=_iso(priced))})
    fields = _query(db_conn).split("|")
    assert fields[1] == str(_age(now, _today_open(now)))
    assert int(fields[1]) < _age(now, priced)


def test_unknown_positions_and_empty_lists(db_conn):
    now = _now(db_conn)
    _put(db_conn, {"monitor": _monitor(now, positions=None, unquoted=[], unquoted_count=0,
                                       fetch_failed=False, check_errors=[], market_open=False)})
    assert _query(db_conn).split("|")[2:] == ["false", "null", "0", "", "false", ""]


def test_missing_fields_read_as_unknown_never_as_zero(db_conn):
    now = _now(db_conn)
    _put(db_conn, {"monitor": {"tick_at": _iso(_ago(now, 5)), "started_at": _iso(_ago(now, 60))}})
    fields = _query(db_conn).split("|")
    assert fields[0] == "5"
    assert fields[2:] == ["", "null", "0", "", "false", ""]
