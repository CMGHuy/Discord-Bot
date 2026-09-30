"""v111 §2: every scan runs inside one scan id; outside a scan the id is '-'."""
import asyncio
import re

import pytest

from swingbot import config
from swingbot.core.infra.logsetup import scan_id_var
from swingbot.core.scanning import runstate, scan_run


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    # Same isolation as tests/scanning/test_run_scan_publishes_progress.py.
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(runstate, "_mark_running", lambda running: None)
    monkeypatch.setattr(runstate, "_clear_stop", lambda: None)
    return tmp_path


def _record_ids(monkeypatch):
    seen = []

    def fake_sync_run(horizon_filter, require_confirmation, progress, min_confluence):
        seen.append(scan_id_var.get())
        return [], [], []

    monkeypatch.setattr(scan_run, "_sync_run_scan", fake_sync_run)
    return seen


def test_the_scan_worker_thread_sees_the_scan_id(data_dir, monkeypatch):
    seen = _record_ids(monkeypatch)
    asyncio.run(scan_run.run_scan())
    assert len(seen) == 1 and re.fullmatch(r"s-\d{4}[a-z0-9]{2}", seen[0])
    assert scan_id_var.get() == "-"


def test_two_scans_get_their_own_ids(data_dir, monkeypatch):
    seen = _record_ids(monkeypatch)

    async def two_scans():
        await scan_run.run_scan()
        await scan_run.run_scan()

    asyncio.run(two_scans())
    assert len(seen) == 2 and all(sid.startswith("s-") for sid in seen)


def test_a_scan_that_raises_still_resets_the_id(data_dir, monkeypatch):
    def boom(*args):
        raise RuntimeError("fetch died")

    monkeypatch.setattr(scan_run, "_sync_run_scan", boom)
    with pytest.raises(RuntimeError):
        asyncio.run(scan_run.run_scan())
    assert scan_id_var.get() == "-"
