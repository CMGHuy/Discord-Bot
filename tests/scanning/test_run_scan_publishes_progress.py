"""`run_scan` publishes its progress for the admin process, and always stops.

The bar the SPA draws is only as trustworthy as this wiring: a record that
outlives its scan is a bar that never finishes, and a scan that publishes
nothing is a bar that never appears.
"""
import asyncio

import pytest

from swingbot import config
from swingbot.core.scanning import progress_store, runstate
from swingbot.core.scanning import scan_run


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    # `runstate` bakes its flag paths at import time, so left alone it would
    # write the developer's real data/ during this test. Not this module's
    # bug to fix; just not this module's business either.
    monkeypatch.setattr(runstate, "_mark_running", lambda running: None)
    monkeypatch.setattr(runstate, "_clear_stop", lambda: None)
    return tmp_path


def _capture_during(monkeypatch, *, raises=False):
    """Run a scan whose body only *observes* what is already on disk.

    The body must never publish anything itself -- that is what makes these
    tests statements about `run_scan`'s wiring rather than about
    `progress_store`, which has its own tests.
    """
    seen = {}

    def fake_sync_run(horizon_filter, require_confirmation, progress, min_confluence):
        seen["during"] = progress_store.read()
        if raises:
            raise RuntimeError("fetch died")
        return [], [], []

    monkeypatch.setattr(scan_run, "_sync_run_scan", fake_sync_run)
    return seen


def test_a_running_scan_publishes_a_record_the_admin_can_read(data_dir, monkeypatch):
    seen = _capture_during(monkeypatch)
    asyncio.run(scan_run.run_scan(progress=scan_run.ScanProgress()))

    # The opening record, written synchronously before the scan body starts:
    # a bar that only appears once the first republish interval elapses is
    # missing for the crawl, which is the slowest phase.
    assert seen["during"] is not None
    assert seen["during"]["stage"] == "starting"
    assert seen["during"]["pct"] == 0


def test_the_record_is_gone_once_the_scan_returns(data_dir, monkeypatch):
    seen = _capture_during(monkeypatch)
    asyncio.run(scan_run.run_scan(progress=scan_run.ScanProgress()))

    assert seen["during"] is not None, "nothing was ever published to clear"
    assert progress_store.read() is None


def test_a_scan_that_raises_leaves_no_record_behind(data_dir, monkeypatch):
    seen = _capture_during(monkeypatch, raises=True)
    with pytest.raises(RuntimeError):
        asyncio.run(scan_run.run_scan(progress=scan_run.ScanProgress()))

    assert seen["during"] is not None, "nothing was ever published to clear"
    assert progress_store.read() is None


def test_a_scan_without_a_tracker_still_runs(data_dir, monkeypatch):
    # `run_scan(progress=None)` is a supported call and must not acquire a
    # second code path here.
    monkeypatch.setattr(scan_run, "_sync_run_scan", lambda *a, **k: ([], [], []))
    assert asyncio.run(scan_run.run_scan()) == []
    assert progress_store.read() is None
