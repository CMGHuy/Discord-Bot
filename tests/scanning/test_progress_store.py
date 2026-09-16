"""`progress_store`: publishing ScanProgress across the process boundary.

The bot and the admin are separate containers sharing only `data/`, so the
in-memory `ScanProgress` the scan already keeps has to land on disk for the
admin's file watcher to notice it. These tests pin the two properties that
make the published record usable as a progress bar:

**The percentage is global, not per-phase.** `ScanProgress.done`/`total` are
reset three times per scan (`fetch.py` for the crawl, `scan_run.py` twice
more for the analysis and the alert build), so `ScanProgress.pct` runs
0->100 three times. A bar wired to that looks broken. `snapshot()` maps each
phase's local ratio into its own band of one 0-100 scale.

**A record carries when it was written.** A bot that dies mid-scan leaves
the running flag set and the last record frozen; the age is what lets the
UI say "stalled" rather than showing a live-looking bar that will never
move again.
"""
import json
import os

import pytest

from swingbot import config
from swingbot.core.scanning import progress_store
from swingbot.core.scanning.scan_run import ScanProgress


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """`progress_store` must read `config.DATA_DIR` per call, not at import."""
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    return tmp_path


def _progress(**fields) -> ScanProgress:
    progress = ScanProgress()
    for key, value in fields.items():
        setattr(progress, key, value)
    return progress


def test_crawl_halfway_maps_into_the_crawl_band_not_to_fifty():
    progress = _progress(stage="crawling data", total=100, done=50)
    assert progress.pct == 50          # the per-phase figure it already has
    assert progress_store.snapshot(progress)["pct"] == 20


def test_analysis_halfway_starts_from_where_the_crawl_ended():
    progress = _progress(stage="analyzing", total=100, done=50)
    assert progress_store.snapshot(progress)["pct"] == 66


def test_alert_build_counts_alerts_not_the_stale_analysis_totals():
    # `done`/`total` still hold the analysis figures here -- nothing resets
    # them -- so a snapshot reading those would sit at 100% for this phase.
    progress = _progress(
        stage="building alerts", total=100, done=100, alerts_total=4, alerts_done=2,
    )
    assert progress_store.snapshot(progress)["pct"] == 96


def test_percentage_never_goes_backwards_across_a_phase_boundary():
    end_of_crawl = progress_store.snapshot(
        _progress(stage="crawling data", total=100, done=100))["pct"]
    start_of_analysis = progress_store.snapshot(
        _progress(stage="analyzing", total=100, done=0))["pct"]
    assert end_of_crawl <= start_of_analysis


def test_the_starting_stage_reports_zero_rather_than_guessing():
    assert progress_store.snapshot(ScanProgress())["pct"] == 0


def test_an_empty_phase_reports_its_band_floor_rather_than_dividing_by_zero():
    progress = _progress(stage="building alerts", alerts_total=0, alerts_done=0)
    assert progress_store.snapshot(progress)["pct"] == 92


def test_a_published_record_round_trips_everything_the_strip_renders(data_dir):
    progress = _progress(
        stage="analyzing", total=100, done=25, current_ticker="AAPL",
        qualifying_found=3,
    )
    progress_store.publish(progress)

    record = progress_store.read()
    assert record["stage"] == "analyzing"
    assert record["current_ticker"] == "AAPL"
    assert record["done"] == 25
    assert record["total"] == 100
    assert record["qualifying_found"] == 3
    assert record["pct"] == 53
    assert record["at"].endswith("+00:00")


def test_reading_with_no_scan_in_flight_is_absent_not_an_error(data_dir):
    assert progress_store.read() is None


def test_clear_removes_the_record_and_tolerates_a_second_call(data_dir):
    progress_store.publish(_progress(stage="analyzing", total=10, done=1))
    progress_store.clear()
    assert progress_store.read() is None
    progress_store.clear()


def test_a_corrupt_record_reads_as_absent_rather_than_raising(data_dir):
    # The admin reads this file on a request thread while the bot writes it.
    # A progress bar is never worth a 500 on the scan-status endpoint.
    (data_dir / "scan_progress.json").write_text("{not json")
    assert progress_store.read() is None


def test_publishing_never_leaves_a_half_written_file_behind(data_dir):
    # Atomic replace, not a truncating write: the admin's watcher fires on
    # mtime and the very next read must see a whole record.
    progress_store.publish(_progress(stage="crawling data", total=8, done=8))
    on_disk = json.loads((data_dir / "scan_progress.json").read_text())
    assert on_disk["pct"] == 40
    assert not [p for p in os.listdir(data_dir) if p.endswith(".tmp")]


def test_the_path_follows_data_dir_reassignment_after_import(tmp_path, monkeypatch):
    # Resolved per call, the way `watcher.default_paths()` does it. A path
    # baked at import time is how a test ends up writing to the real data/.
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path / "elsewhere"))
    progress_store.publish(_progress(stage="analyzing", total=4, done=1))
    assert (tmp_path / "elsewhere" / "scan_progress.json").exists()


def _wait_for(predicate, timeout=3.0):
    """Poll rather than sleep a fixed time: the publisher runs on its own
    thread and a fixed sleep is how a thread test becomes flaky on a loaded
    machine."""
    import time
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_publishing_writes_a_first_record_before_the_thread_is_even_scheduled(data_dir):
    # Synchronous first publish: a scan's opening seconds are its slowest,
    # and a bar that only appears once the first interval elapses is missing
    # exactly when the user most wants it.
    progress = _progress(stage="crawling data", total=10, done=0)
    with progress_store.publishing(progress, interval=0.01):
        assert progress_store.read()["stage"] == "crawling data"


def test_publishing_keeps_following_progress_while_the_scan_runs(data_dir):
    progress = _progress(stage="crawling data", total=10, done=0)
    with progress_store.publishing(progress, interval=0.01):
        progress.done = 5
        assert _wait_for(lambda: progress_store.read()["pct"] == 20)


def test_leaving_the_block_clears_the_record_so_no_bar_outlives_the_scan(data_dir):
    with progress_store.publishing(_progress(stage="analyzing", total=4, done=1),
                                   interval=0.01):
        pass
    assert progress_store.read() is None


def test_a_scan_that_raises_still_clears_its_record(data_dir):
    with pytest.raises(RuntimeError):
        with progress_store.publishing(_progress(stage="analyzing", total=4, done=1),
                                       interval=0.01):
            raise RuntimeError("scan blew up")
    assert progress_store.read() is None


def test_the_publisher_thread_cannot_outlive_the_block(data_dir):
    import threading
    before = {t.name for t in threading.enumerate()}
    with progress_store.publishing(_progress(stage="analyzing", total=4, done=1),
                                   interval=0.01):
        during = {t.name for t in threading.enumerate()} - before
        assert during, "expected a publisher thread while the block is open"
    assert _wait_for(lambda: not ({t.name for t in threading.enumerate()} & during))


def test_a_scan_with_no_progress_tracker_publishes_nothing(data_dir):
    # `run_scan(progress=None)` is a supported call -- it must not be given a
    # second code path at the call site.
    with progress_store.publishing(None, interval=0.01):
        assert progress_store.read() is None


def test_the_published_counts_always_describe_the_current_phase():
    # `done`/`total` mean "progress within `stage`", every stage. During the
    # alert build the tracker's own `done`/`total` still hold the analysis
    # figures -- nothing resets them -- so a record that copied them would
    # have the UI render "100/100" beside a bar sitting at 94%.
    record = progress_store.snapshot(_progress(
        stage="building alerts", total=1280, done=1280, alerts_total=4, alerts_done=1,
    ))
    assert (record["done"], record["total"]) == (1, 4)
