"""A leftover scan_running.flag must not silently disable the SL/TP monitor.

engine._mark_running(False) runs in a `finally`, so an *exception* mid-scan
always clears the flag. A SIGKILL does not -- container restart, OOM, or
`docker compose stop` during a scan leaves the file on disk. Because
commands/scanning.py:trade_monitor early-returns whenever is_scan_running()
is True, a stale flag permanently kills the 60s SL/TP poller: open trades
then hit their target or their stop and are never closed, showing on the
dashboard at 100% / 0% and staying open.
"""
import importlib
import os
import time

import swingbot.config as config


def _engine(tmp_path, monkeypatch):
    """Re-import the engine so _RUNNING_FILE binds to the patched DATA_DIR
    (it is computed at module import time)."""
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    from swingbot.core.scanning import engine
    importlib.reload(engine)
    return engine


def test_fresh_flag_still_reports_running(tmp_path, monkeypatch):
    """The guard must not break the real case it exists for: a scan that is
    genuinely in flight still suppresses the monitor."""
    engine = _engine(tmp_path, monkeypatch)
    engine._mark_running(True)
    assert engine.is_scan_running() is True


def test_cleared_flag_reports_not_running(tmp_path, monkeypatch):
    engine = _engine(tmp_path, monkeypatch)
    engine._mark_running(True)
    engine._mark_running(False)
    assert engine.is_scan_running() is False


def test_stale_flag_is_not_treated_as_a_running_scan(tmp_path, monkeypatch):
    """The regression: a flag left by a killed process must expire, or
    trade_monitor never runs again."""
    engine = _engine(tmp_path, monkeypatch)
    engine._mark_running(True)
    # Backdate well past any plausible scan duration, as a hard kill would leave it.
    old = time.time() - (engine._RUNNING_FLAG_MAX_AGE_SEC + 60)
    os.utime(engine._RUNNING_FILE, (old, old))

    assert engine.is_scan_running() is False, (
        "a stale scan_running.flag must not report a running scan -- it "
        "permanently disables the SL/TP monitor"
    )


def test_stale_flag_is_cleaned_up_so_it_cannot_recur(tmp_path, monkeypatch):
    engine = _engine(tmp_path, monkeypatch)
    engine._mark_running(True)
    old = time.time() - (engine._RUNNING_FLAG_MAX_AGE_SEC + 60)
    os.utime(engine._RUNNING_FILE, (old, old))

    engine.is_scan_running()
    assert not os.path.exists(engine._RUNNING_FILE), (
        "the stale flag should be removed, not just ignored"
    )
