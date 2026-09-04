import asyncio
import json

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
    assert runstate.get_alert_active() is False


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
