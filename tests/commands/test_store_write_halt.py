"""A DB write failure at a trading store's db stage pauses alerting instead
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
    monkeypatch.setattr(runstate, "_HEARTBEAT_FILE", str(tmp_path / "bot_heartbeat.json"))
    monkeypatch.setattr(runstate, "_PAUSE_FILE", str(tmp_path / "scan_paused.flag"))
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


def test_only_a_trading_store_at_db_halts(monkeypatch):
    monkeypatch.setattr(config, "DB_STORES", "plans:dual,flags:db")
    assert write_failure.halts_issuance(_db_error()) is False
    monkeypatch.setattr(config, "DB_STORES", "plans:db")
    assert write_failure.halts_issuance(_db_error()) is True


def test_persist_plan_raises_at_db_and_still_swallows_at_json(monkeypatch):
    class Boom:
        def add(self, _plan):
            raise _db_error()

    class Plan:
        plan_id = "P1"

    monkeypatch.setattr(scan_run, "PlanStore", Boom)
    monkeypatch.setattr(config, "DB_STORES", "")
    scan_run._persist_plan_v2(Plan())                       # logged, swallowed
    monkeypatch.setattr(config, "DB_STORES", "plans:db")
    with pytest.raises(write_failure.StoreWriteHalt):
        scan_run._persist_plan_v2(Plan())


def test_the_scan_loop_pauses_posts_to_ops_and_marks_health(files, monkeypatch):
    monkeypatch.setattr(config, "DB_STORES", "plans:db")
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


def test_unpausing_clears_the_health_mark(files, monkeypatch):
    monkeypatch.setattr(config, "DB_STORES", "")
    runstate.record_store_write_failure(write_failure.StoreWriteHalt("x"))
    runstate.set_scan_paused(False)
    assert runstate._read_heartbeat().get("store_write_failure") is None


def test_the_admin_reports_unhealthy_while_marked(files, monkeypatch):
    from swingbot.admin import app as admin_app
    monkeypatch.setattr(config, "DB_STORES", "")
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    runstate._update_heartbeat({"timestamp": now, "last_success": now})
    runstate.record_store_write_failure(write_failure.StoreWriteHalt("plan P1"))
    payload = admin_app.scan_status_payload()
    assert payload["bot_healthy"] is False
    assert payload["bot_store_write_failure"]["error"].startswith("StoreWriteHalt")
