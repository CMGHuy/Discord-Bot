"""Delivery only happens on commit, so these tests commit -- and are slow."""
import threading
import time

import pytest
import sqlalchemy as sa

from swingbot.core.db import notify
from swingbot.core.db.schema import trades

pytestmark = pytest.mark.slow


def _run_listener(channels, seen, stop, dsn):
    notify.listen(channels, seen.append, stop, poll=0.1, dsn=dsn)


@pytest.fixture
def listener(db_engine):
    seen: list[str] = []
    stop = threading.Event()
    dsn = db_engine.url.render_as_string(hide_password=False)
    thread = threading.Thread(
        target=_run_listener, args=(["trades", "scan"], seen, stop, dsn), daemon=True)
    thread.start()
    time.sleep(0.5)   # let LISTEN register before the first write
    yield seen
    stop.set()
    thread.join(timeout=5)
    assert not thread.is_alive(), "listener did not stop when asked"


def _wait_for(seen, channel, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if channel in seen:
            return True
        time.sleep(0.05)
    return False


def test_a_committed_insert_delivers_on_the_table_channel(listener, db_committed):
    with db_committed.begin():
        db_committed.execute(sa.insert(trades).values(
            trade_id="NOTIFY-1", ticker="AAPL", strategy="RSI", horizon="2w",
            direction="LONG", status="open",
            opened_at="2026-01-02T15:00:00+00:00"))
    assert _wait_for(listener, "trades"), f"no 'trades' notification; saw {listener}"


def test_an_explicit_emit_delivers(listener, db_committed):
    with db_committed.begin():
        notify.emit(db_committed, "scan")
    assert _wait_for(listener, "scan"), f"no 'scan' notification; saw {listener}"


def test_a_rolled_back_write_delivers_nothing(listener, db_conn):
    db_conn.execute(sa.insert(trades).values(
        trade_id="NOTIFY-2", ticker="MSFT", strategy="RSI", horizon="2w",
        direction="LONG", status="open", opened_at="2026-01-02T15:00:00+00:00"))
    # db_conn rolls back at teardown; give delivery a chance to be wrong.
    time.sleep(0.5)
    assert "trades" not in listener


def test_listen_rejects_an_unknown_channel(db_engine):
    with pytest.raises(ValueError, match="not a known channel"):
        notify.listen(["made_up"], lambda _c: None, threading.Event(),
                      dsn=db_engine.url.render_as_string(hide_password=False))
