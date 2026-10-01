"""A DB write failure pauses alerting instead
of issuing a trade the book cannot record (v116 Phase 3)."""
import asyncio
import datetime as dt

import pytest
import sqlalchemy.exc as sa_exc

from swingbot import config
from swingbot.commands.scanning import loops, runstate
from swingbot.core.db import write_failure
from swingbot.core.scanning import scan_run


def _db_error():
    return sa_exc.OperationalError("INSERT INTO plans", {}, Exception("server closed"))


class _FakeChannel:
    def __init__(self):
        self.sent = []

    async def send(self, content=None, **kw):
        self.sent.append({"content": content, **kw})


@pytest.fixture
def files(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(loops.config, "HEALTH_ALERT_AFTER_FAILURES", 3)
    return tmp_path


def test_a_wrapped_database_error_is_a_store_write_failure():
    try:
        try:
            raise _db_error()
        except sa_exc.OperationalError as inner:
            raise RuntimeError("persist failed") from inner
    except RuntimeError as outer:
        assert write_failure.is_store_write_failure(outer) is True
    assert write_failure.is_store_write_failure(ValueError("bad price")) is False


def test_any_database_write_failure_halts():
    assert write_failure.halts_issuance(_db_error()) is True
    assert write_failure.halts_issuance(ValueError("bad price")) is False


def test_persist_plan_raises_on_a_database_failure(monkeypatch):
    class Boom:
        def add(self, _plan):
            raise _db_error()

    class Plan:
        plan_id = "P1"

    monkeypatch.setattr(scan_run, "PlanStore", Boom)
    with pytest.raises(write_failure.StoreWriteHalt):
        scan_run._persist_plan_v2(Plan())


def test_the_scan_loop_pauses_posts_to_ops_and_marks_health(files, monkeypatch):
    channel = _FakeChannel()
    monkeypatch.setattr(loops, "_ops_channel", lambda: channel)

    async def _halted():
        raise write_failure.StoreWriteHalt("plan P1 could not be stored") from _db_error()

    monkeypatch.setattr(loops, "_session_scan_tick", _halted)
    asyncio.run(loops.session_scan.coro())

    assert runstate.is_scan_paused() is True
    assert len(channel.sent) == 1                     # immediately, not after 3 ticks
    assert channel.sent[0]["content"].startswith("🚨 SYSTEM · HEALTH ALERT")
    assert "alerting paused" in channel.sent[0]["embed"].title
    assert runstate._read_heartbeat()["store_write_failure"]["error"].startswith("StoreWriteHalt")


def test_unpausing_clears_the_health_mark(files):
    runstate.record_store_write_failure(write_failure.StoreWriteHalt("x"))
    runstate.set_scan_paused(False)
    assert runstate._read_heartbeat().get("store_write_failure") is None


def test_the_admin_reports_unhealthy_while_marked(files):
    from swingbot.admin import app as admin_app
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    runstate._update_heartbeat({"timestamp": now, "last_success": now})
    runstate.record_store_write_failure(write_failure.StoreWriteHalt("plan P1"))
    payload = admin_app.scan_status_payload()
    assert payload["bot_healthy"] is False
    assert payload["bot_store_write_failure"]["error"].startswith("StoreWriteHalt")


def test_alerts_built_before_a_halt_are_still_posted_then_the_halt_propagates(monkeypatch):
    sent = []

    async def _fake_send(channel, alerts, route_by_confidence=False):
        sent.append(list(alerts))

    async def _run_scan(**kw):
        raise write_failure.StoreWriteHalt("plan P2", alerts=["alert-1"])

    monkeypatch.setattr(loops, "_send_alerts", _fake_send)
    monkeypatch.setattr(loops.scan_engine, "run_scan", _run_scan)
    with pytest.raises(write_failure.StoreWriteHalt):
        asyncio.run(loops._run_scan_posting_partial("chan", require_confirmation=True))
    assert sent == [["alert-1"]]


def test_the_classifier_is_conservative_a_read_shaped_db_error_also_counts():
    """Pinned on purpose: it cannot tell reads from writes, so any database
    error in the chain at a db-stage store halts (the book is unreachable)."""
    from swingbot.core.db.engine import DatabaseUnavailable
    read_err = sa_exc.OperationalError("SELECT * FROM plans", {}, Exception("timeout"))
    assert write_failure.is_store_write_failure(read_err) is True
    assert write_failure.is_store_write_failure(DatabaseUnavailable("down")) is True
