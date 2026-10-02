import asyncio

from swingbot.commands.scanning import runstate


def test_failure_increments_and_success_resets():
    assert runstate.record_tick_failure() == 1
    assert runstate.record_tick_failure() == 2
    assert runstate.last_success_iso() is None

    recovered = runstate.record_tick_success()

    state = runstate._read_heartbeat()
    assert state["consecutive_failures"] == 0
    assert state["last_success"]
    assert recovered is False           # no alert was active, so not a recovery


def test_success_after_an_alert_reports_recovery():
    runstate.record_tick_failure()
    runstate.set_alert_active(True)
    assert runstate.get_alert_active() is True

    assert runstate.record_tick_success() is True
    assert runstate.get_alert_active() is False


def test_liveness_write_preserves_outcome_fields():
    """_write_heartbeat() runs at the top of every tick and must not wipe
    the outcome fields written at the end of the previous one."""
    runstate.record_tick_failure()
    runstate.record_tick_failure()
    runstate._write_heartbeat()

    state = runstate._read_heartbeat()
    assert state["consecutive_failures"] == 2
    assert "timestamp" in state


def test_missing_file_reads_as_unknown():
    assert runstate.last_success_iso() is None
    assert runstate.get_alert_active() is False


def test_tick_that_raises_is_recorded_as_failure(monkeypatch):
    from swingbot.commands.scanning import loops

    async def _boom():
        raise RuntimeError("tick exploded")

    monkeypatch.setattr(loops, "_session_scan_tick", _boom)
    asyncio.run(loops.session_scan.coro())

    assert runstate.last_success_iso() is None
    assert runstate._read_heartbeat()["consecutive_failures"] == 1


def test_tick_that_returns_is_recorded_as_success(monkeypatch):
    from swingbot.commands.scanning import loops

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
        self.sent.append({"content": content, **kw})


def test_escalates_once_at_the_threshold_then_stays_quiet(monkeypatch):
    from swingbot.commands.scanning import loops

    channel = _FakeChannel()
    monkeypatch.setattr(loops, "_ops_channel", lambda: channel)
    monkeypatch.setattr(loops.config, "HEALTH_ALERT_AFTER_FAILURES", 3)

    async def _boom():
        raise RuntimeError("tick exploded")

    monkeypatch.setattr(loops, "_session_scan_tick", _boom)

    for _ in range(5):
        asyncio.run(loops.session_scan.coro())

    assert len(channel.sent) == 1, "one alert per outage, not one per tick"
    assert channel.sent[0]["content"].startswith("🚨 SYSTEM · HEALTH ALERT")
    assert "3" in channel.sent[0]["embed"].title
    assert "RuntimeError" in channel.sent[0]["embed"].description


def test_recovery_posts_exactly_one_notice(monkeypatch):
    from swingbot.commands.scanning import loops

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
    assert channel.sent[1]["content"].startswith("✅ SYSTEM · RECOVERED")


def test_below_threshold_posts_nothing(monkeypatch):
    from swingbot.commands.scanning import loops

    channel = _FakeChannel()
    monkeypatch.setattr(loops, "_ops_channel", lambda: channel)
    monkeypatch.setattr(loops.config, "HEALTH_ALERT_AFTER_FAILURES", 3)

    async def _boom():
        raise RuntimeError("tick exploded")

    monkeypatch.setattr(loops, "_session_scan_tick", _boom)
    asyncio.run(loops.session_scan.coro())

    assert channel.sent == []
