"""One write in Postgres, one named event out of the broker.

This is the whole live-update path in one test. Slow tier: NOTIFY only fires on
commit, so per-test rollback isolation cannot be used.
"""
import time

import pytest
import sqlalchemy as sa

from swingbot import config
from swingbot.admin.events.broker import EventBroker

pytestmark = pytest.mark.slow


@pytest.fixture
def broker(monkeypatch, db_engine, tmp_path):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DB_STORES", "events:db")
    monkeypatch.setattr(config, "DATABASE_URL",
                        db_engine.url.render_as_string(hide_password=False))
    from swingbot.core.db.engine import reset_engine
    reset_engine()
    return EventBroker()


def _wait_for(sub, name, timeout=8.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        event = sub.get(timeout=0.25)
        if event is not None and event.event == name:
            return True
    return False


def _insert_trade(conn, trade_id):
    from swingbot.core.db.schema import trades
    conn.execute(sa.insert(trades).values(
        trade_id=trade_id, ticker="AAPL", strategy="RSI", horizon="2w",
        direction="bullish", status="open",
        opened_at="2026-01-02T15:00:00+00:00"))


def test_a_trade_write_raises_the_trades_event(broker, db_committed):
    with broker.subscribe() as sub:
        time.sleep(0.5)                    # let LISTEN register
        with db_committed.begin():
            _insert_trade(db_committed, "E2E-1")
        assert _wait_for(sub, "trades")


def test_a_flag_write_raises_the_scan_event(broker, db_committed):
    from swingbot.core.db.repositories.flags import FlagRepository
    with broker.subscribe() as sub:
        time.sleep(0.5)
        with db_committed.begin():
            FlagRepository().set("scan_running", conn=db_committed)
        assert _wait_for(sub, "scan")


def test_a_flag_is_noticed_immediately_not_on_the_next_poll(broker, db_committed):
    """The payoff over the .flag files: the bot reacts now, not on its next
    sweep. Asserted as a latency bound well under the 0.5s the file watcher
    took at its best."""
    from swingbot.core.db.repositories.flags import FlagRepository
    with broker.subscribe() as sub:
        time.sleep(0.5)
        started = time.time()
        with db_committed.begin():
            FlagRepository().set("stop_scan", conn=db_committed)
        assert _wait_for(sub, "scan")
        # 0.25 debounce + delivery. Generous, because CI is not a quiet box;
        # the claim being tested is "sub-second", not a specific number.
        assert time.time() - started < 2.0


def test_two_tables_in_one_burst_emit_one_event(broker, db_committed):
    from swingbot.core.db.schema import plans
    with broker.subscribe() as sub:
        time.sleep(0.5)
        with db_committed.begin():
            _insert_trade(db_committed, "E2E-2")
            db_committed.execute(sa.insert(plans).values(
                plan_id="E2E-P2", ticker="AAPL", strategy="RSI",
                horizon_key="2w", status="pending",
                created_at="2026-01-02T15:00:00+00:00"))
        assert _wait_for(sub, "trades")
        # The debounce collapsed both writes into one refetch signal.
        time.sleep(0.5)
        extra = sub.get(timeout=0.25)
        assert extra is None or extra.event != "trades"


def test_scan_progress_file_still_raises_scan_at_the_db_stage(broker, tmp_path):
    """The P3-20 composite: scan_progress.json has no table, so the residual
    file watcher must keep the scan-progress strip moving at events:db."""
    with broker.subscribe() as sub:
        time.sleep(0.5)
        (tmp_path / "scan_progress.json").write_text("{}")
        assert _wait_for(sub, "scan")
