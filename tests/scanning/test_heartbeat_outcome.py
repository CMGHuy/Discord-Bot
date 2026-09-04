import asyncio
import json

import pytest

from swingbot.commands.scanning import runstate


def _use_tmp_heartbeat(tmp_path, monkeypatch):
    path = tmp_path / "bot_heartbeat.json"
    monkeypatch.setattr(runstate, "_HEARTBEAT_FILE", str(path))
    monkeypatch.setattr(runstate.config, "DATA_DIR", str(tmp_path))
    return path


def test_failure_increments_and_success_resets(tmp_path, monkeypatch):
    path = _use_tmp_heartbeat(tmp_path, monkeypatch)

    assert runstate.record_tick_failure() == 1
    assert runstate.record_tick_failure() == 2
    assert runstate.last_success_iso() is None

    recovered = runstate.record_tick_success()

    state = json.loads(path.read_text())
    assert state["consecutive_failures"] == 0
    assert state["last_success"]
    assert recovered is False           # no alert was active, so not a recovery


def test_success_after_an_alert_reports_recovery(tmp_path, monkeypatch):
    _use_tmp_heartbeat(tmp_path, monkeypatch)

    runstate.record_tick_failure()
    runstate.set_alert_active(True)
    assert runstate.get_alert_active() is True

    assert runstate.record_tick_success() is True
    assert runstate.get_alert_active() is True


def test_liveness_write_preserves_outcome_fields(tmp_path, monkeypatch):
    """_write_heartbeat() runs at the top of every tick and must not wipe
    the outcome fields written at the end of the previous one."""
    path = _use_tmp_heartbeat(tmp_path, monkeypatch)

    runstate.record_tick_failure()
    runstate.record_tick_failure()
    runstate._write_heartbeat()

    state = json.loads(path.read_text())
    assert state["consecutive_failures"] == 2
    assert "timestamp" in state


def test_missing_file_reads_as_unknown(tmp_path, monkeypatch):
    _use_tmp_heartbeat(tmp_path, monkeypatch)
    assert runstate.last_success_iso() is None
    assert runstate.get_alert_active() is False


def test_tick_that_raises_is_recorded_as_failure(tmp_path, monkeypatch):
    from swingbot.commands.scanning import loops

    _use_tmp_heartbeat(tmp_path, monkeypatch)

    async def _boom():
        raise RuntimeError("tick exploded")

    monkeypatch.setattr(loops, "_session_scan_tick", _boom)
    asyncio.run(loops.session_scan.coro())

    assert runstate.last_success_iso() is None
    assert runstate._read_heartbeat()["consecutive_failures"] == 1


def test_tick_that_returns_is_recorded_as_success(tmp_path, monkeypatch):
    from swingbot.commands.scanning import loops

    _use_tmp_heartbeat(tmp_path, monkeypatch)

    async def _ok():
        return None

    monkeypatch.setattr(loops, "_session_scan_tick", _ok)
    asyncio.run(loops.session_scan.coro())

    assert runstate.last_success_iso() is not None
    assert runstate._read_heartbeat()["consecutive_failures"] == 0


class _FakeChannel:
    def __init__(self):
        self.sent = []

    async def send(self, content=None, **kw):
        self.sent.append(content)


def test_escalates_once_at_the_threshold_then_stays_quiet(tmp_path, monkeypatch):
    from swingbot.commands.scanning import loops

    _use_tmp_heartbeat(tmp_path, monkeypatch)
    channel = _FakeChannel()
    monkeypatch.setattr(loops, "_ops_channel", lambda: channel)
    monkeypatch.setattr(loops.config, "HEALTH_ALERT_AFTER_FAILURES", 3)

    async def _boom():
        raise RuntimeError("tick exploded")

    monkeypatch.setattr(loops, "_session_scan_tick", _boom)

    for _ in range(5):
        asyncio.run(loops.session_scan.coro())

    assert len(channel.sent) == 1, "one alert per outage, not one per tick"
    assert "3" in channel.sent[0]
    assert "RuntimeError" in channel.sent[0]


def test_recovery_posts_exactly_one_notice(tmp_path, monkeypatch):
    from swingbot.commands.scanning import loops

    _use_tmp_heartbeat(tmp_path, monkeypatch)
    channel = _FakeChannel()
    monkeypatch.setattr(loops, "_ops_channel", lambda: channel)
    monkeypatch.setattr(loops.config, "HEALTH_ALERT_AFTER_FAILURES", 2)

    async def _boom():
        raise RuntimeError("tick exploded")

    async def _ok():
        return None

    monkeypatch.setattr(loops, "_session_scan_tick", _boom)
    asyncio.run(loops.session_scan.coro())
    asyncio.run(loops.session_scan.coro())
    assert len(channel.sent) == 1

    monkeypatch.setattr(loops, "_session_scan_tick", _ok)
    asyncio.run(loops.session_scan.coro())
    asyncio.run(loops.session_scan.coro())

    assert len(channel.sent) == 2
    assert "recover" in channel.sent[1].lower()


def test_below_threshold_posts_nothing(tmp_path, monkeypatch):
    from swingbot.commands.scanning import loops

    _use_tmp_heartbeat(tmp_path, monkeypatch)
    channel = _FakeChannel()
    monkeypatch.setattr(loops, "_ops_channel", lambda: channel)
    monkeypatch.setattr(loops.config, "HEALTH_ALERT_AFTER_FAILURES", 3)

    async def _boom():
        raise RuntimeError("tick exploded")

    monkeypatch.setattr(loops, "_session_scan_tick", _boom)
    asyncio.run(loops.session_scan.coro())

    assert channel.sent == []


class _RecoveryFailsOnceChannel(_FakeChannel):
    def __init__(self):
        super().__init__()
        self.recovery_attempts = 0

    async def send(self, content=None, **kw):
        if "recover" in content.lower():
            self.recovery_attempts += 1
            if self.recovery_attempts == 1:
                raise RuntimeError("Discord unavailable")
        self.sent.append(content)


def test_failed_recovery_send_remains_retryable(tmp_path, monkeypatch):
    from swingbot.commands.scanning import loops

    _use_tmp_heartbeat(tmp_path, monkeypatch)
    channel = _RecoveryFailsOnceChannel()
    monkeypatch.setattr(loops, "_ops_channel", lambda: channel)
    monkeypatch.setattr(loops.config, "HEALTH_ALERT_AFTER_FAILURES", 1)

    async def _boom():
        raise RuntimeError("tick exploded")

    async def _ok():
        return None

    monkeypatch.setattr(loops, "_session_scan_tick", _boom)
    asyncio.run(loops.session_scan.coro())
    monkeypatch.setattr(loops, "_session_scan_tick", _ok)
    asyncio.run(loops.session_scan.coro())
    assert runstate.get_alert_active() is True

    asyncio.run(loops.session_scan.coro())

    assert channel.recovery_attempts == 2
    assert sum("health alert" in item.lower() for item in channel.sent) == 1
    assert sum("recover" in item.lower() for item in channel.sent) == 1
    assert runstate.get_alert_active() is False


def test_outage_persistence_failure_is_logged_and_does_not_duplicate_send(
    tmp_path, monkeypatch, caplog
):
    from swingbot.commands.scanning import loops

    _use_tmp_heartbeat(tmp_path, monkeypatch)
    channel = _FakeChannel()
    monkeypatch.setattr(loops, "_ops_channel", lambda: channel)
    monkeypatch.setattr(loops.config, "HEALTH_ALERT_AFTER_FAILURES", 1)

    async def _boom():
        raise RuntimeError("tick exploded")

    monkeypatch.setattr(loops, "_session_scan_tick", _boom)
    real_set_alert_active = runstate.set_alert_active
    attempts = 0

    def _fail_first_write(active):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError("disk full")
        real_set_alert_active(active)

    monkeypatch.setattr(runstate, "set_alert_active", _fail_first_write)

    with caplog.at_level("ERROR"):
        asyncio.run(loops.session_scan.coro())
        asyncio.run(loops.session_scan.coro())
        asyncio.run(loops.session_scan.coro())

    assert any("health escalation itself failed" in record.message
               and record.exc_info for record in caplog.records)
    assert sum("health alert" in item.lower() for item in channel.sent) == 1
    assert runstate.get_alert_active() is True


def test_heartbeat_write_failure_is_not_reported_as_success(tmp_path, monkeypatch):
    _use_tmp_heartbeat(tmp_path, monkeypatch)

    def _fail_write(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(runstate, "atomic_write_json", _fail_write)

    with pytest.raises(OSError, match="disk full"):
        runstate.record_tick_failure()
