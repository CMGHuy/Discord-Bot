"""JobManager: subprocess job lifecycle. `kind="test"` allows a raw argv
(interpreter-relative) for tests -- `kind="tune"` (C31) always routes
through scripts/backtest/tune_strategy.py and the TRAIN-only guardrail.

NG19 TRIAGE — **MIXED · mostly KEEP.** The JobManager and build_tune_args
tests are unit-level over swingbot/admin/jobs.py, which /api/v1/jobs calls
rather than replaces: KEEP UNCHANGED. Only the three `/api/jobs*` route
tests near the bottom (test_api_jobs_tune_*) die at cutover; their successors
are in test_api_v1_jobs.py, including the 409-while-busy case."""
import time

import pytest


def _certainly_dead_pid() -> int:
    """A pid that is not running. Spawn a trivial process and reap it, so the
    number is real and definitely finished -- inventing a large integer risks
    colliding with a live process on a busy machine."""
    import subprocess, sys
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    return proc.pid


def _wait_until_done(mgr, job_id, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        status = mgr.status(job_id)
        if status and status["state"] in ("done", "failed"):
            return status
        time.sleep(0.05)
    raise TimeoutError(f"job {job_id} did not finish within {timeout}s")


def test_job_runs_and_tail_captures_output(admin_app):
    from swingbot.admin.jobs import JobManager
    mgr = JobManager()
    job_id = mgr.start("test", ["-c", "print('hi')"])
    status = _wait_until_done(mgr, job_id)
    assert status["state"] == "done"
    assert status["returncode"] == 0
    assert "hi" in mgr.tail(job_id)


def test_a_finished_job_is_never_reaped_as_failed(admin_app):
    """The race that made this file flaky, pinned deterministically.

    `_reap_stale` marks jobs failed when their pid is dead while their state
    still says running -- correct for a job orphaned by an admin restart, and
    wrong for one whose watcher simply has not taken the lock yet. `status()`
    reaps on every call, so a poll landing in that window turned a successful
    job into `state="failed", returncode=None`.

    Reproduced without timing luck: publish a running job whose pid is
    certainly dead, with the job registered as watched, and reap. It must
    survive. This is what the flaky
    `test_job_runs_and_tail_captures_output` was hitting by chance under
    `-n 4`, where the watcher thread is scheduled later.
    """
    from swingbot.admin import jobs as jobs_mod

    mgr = jobs_mod.JobManager()
    dead_pid = _certainly_dead_pid()
    record = {
        "id": "watched01", "kind": "test", "args": [], "state": "running",
        "started_at": "2026-08-14T00:00:00+00:00", "finished_at": None,
        "returncode": None, "log_path": "x.log", "pid": dead_pid,
        "result_path": None,
    }

    with jobs_mod._WATCHED_LOCK:
        jobs_mod._WATCHED.add("watched01")
    try:
        table = {"watched01": dict(record)}
        mgr._reap_stale(table)
        assert table["watched01"]["state"] == "running", (
            "a job this process is still watching was reaped as failed"
        )
    finally:
        with jobs_mod._WATCHED_LOCK:
            jobs_mod._WATCHED.discard("watched01")


def test_an_orphaned_job_is_still_reaped(admin_app):
    """The other half: without this, the fix above would be "never reap", and
    a job orphaned by an admin restart would sit `running` for ever with
    nothing able to correct it -- and `_any_active` would refuse every new
    job because one is perpetually "in progress"."""
    from swingbot.admin import jobs as jobs_mod

    mgr = jobs_mod.JobManager()
    table = {"orphan01": {
        "id": "orphan01", "kind": "test", "args": [], "state": "running",
        "started_at": "2026-08-14T00:00:00+00:00", "finished_at": None,
        "returncode": None, "log_path": "x.log", "pid": _certainly_dead_pid(),
        "result_path": None,
    }}

    mgr._reap_stale(table)

    assert table["orphan01"]["state"] == "failed"
    assert table["orphan01"]["finished_at"] is not None


def test_a_watched_job_still_blocks_a_second_start(admin_app):
    """`_any_active` skipped pid-dead running jobs on the assumption the
    reaper would clean them up. For a watched job that is wrong in the other
    direction: its result is not recorded yet, so it is still the active job
    and must keep the single-job lock."""
    from swingbot.admin import jobs as jobs_mod

    mgr = jobs_mod.JobManager()
    with jobs_mod._WATCHED_LOCK:
        jobs_mod._WATCHED.add("watched02")
    try:
        table = {"watched02": {
            "id": "watched02", "kind": "test", "args": [], "state": "running",
            "started_at": "2026-08-14T00:00:00+00:00", "finished_at": None,
            "returncode": None, "log_path": "x.log",
            "pid": _certainly_dead_pid(), "result_path": None,
        }}
        assert mgr._any_active(table) is True
    finally:
        with jobs_mod._WATCHED_LOCK:
            jobs_mod._WATCHED.discard("watched02")


def test_a_fast_job_reports_done_every_time(admin_app):
    """The original flake, made deliberate: a job that finishes almost
    immediately is exactly the one the reaper used to beat, so run it enough
    times that the old race would show."""
    from swingbot.admin.jobs import JobManager

    for attempt in range(8):
        mgr = JobManager()
        job_id = mgr.start("test", ["-c", "print('hi')"])
        status = _wait_until_done(mgr, job_id)
        assert status["state"] == "done", f"attempt {attempt}: {status}"
        assert status["returncode"] == 0


def test_concurrent_start_raises_while_busy(admin_app):
    from swingbot.admin.jobs import JobManager
    mgr = JobManager()
    mgr.start("test", ["-c", "import time; time.sleep(2)"])
    with pytest.raises(RuntimeError, match="already running"):
        mgr.start("test", ["-c", "print('should not start')"])


class _FakeManagerOK:
    def start(self, kind, args):
        return "job123"


class _FakeManagerBusy:
    def start(self, kind, args):
        raise RuntimeError("job already running")


def test_guardrail_blocks_validation_window():
    from swingbot.admin.jobs import assert_train_only, build_tune_args
    with pytest.raises(ValueError):
        assert_train_only(["--from", "2024-06-01", "--to", "2024-12-31"])
    with pytest.raises(ValueError):
        assert_train_only(["--validation"])
    assert_train_only(build_tune_args("RSI", None))  # must not raise


def test_guardrail_blocks_single_token_flag_equals_value():
    from swingbot.admin.jobs import assert_train_only
    with pytest.raises(ValueError):
        assert_train_only(["--from=2024-06-01"])


def test_guardrail_blocks_non_zero_padded_date():
    from swingbot.admin.jobs import assert_train_only
    with pytest.raises(ValueError):
        assert_train_only(["2024-1-1"])


def test_guardrail_no_false_positive_on_ordinary_args():
    from swingbot.admin.jobs import assert_train_only, build_tune_args
    assert_train_only(["--strategy", "RSI"])  # must not raise
    assert_train_only(build_tune_args("RSI", None))  # must not raise


def test_build_tune_args_rejects_unknown_strategy():
    from swingbot.admin.jobs import build_tune_args
    with pytest.raises(ValueError, match="unknown strategy"):
        build_tune_args("Not A Real Strategy", None)


def test_build_tune_args_passes_be_trigger_through():
    from swingbot.admin.jobs import build_tune_args
    args = build_tune_args("RSI", {"be_trigger": 0.6})
    assert args == ["--strategy", "RSI", "--be-trigger", "0.6"]


def test_build_tune_args_rejects_non_dict_params():
    from swingbot.admin.jobs import build_tune_args
    with pytest.raises(ValueError):
        build_tune_args("RSI", 42)


def test_build_tune_args_rejects_non_numeric_be_trigger():
    from swingbot.admin.jobs import build_tune_args
    with pytest.raises(ValueError):
        build_tune_args("RSI", {"be_trigger": [1, 2, 3]})


def test_job_manager_start_enforces_guardrail_even_if_caller_bypasses_builder(admin_app):
    from swingbot.admin.jobs import JobManager
    mgr = JobManager()
    with pytest.raises(ValueError):
        mgr.start("tune", ["--strategy", "RSI", "--from", "2024-01-01"])


import json
import os


def test_load_result_rejects_path_traversal_job_id(admin_app):
    """job_id="../secret" resolves (via os.path.join(DATA_DIR, "tuning_results",
    "../secret.json")) to DATA_DIR/secret.json, one level above tuning_results/.
    Plant a real file exactly there so a regression here would leak it, proving
    the guard -- not just an absent-file coincidence -- is what blocks the read."""
    from swingbot import config
    from swingbot.admin.queries import _load_result

    os.makedirs(os.path.join(config.DATA_DIR, "tuning_results"), exist_ok=True)
    with open(os.path.join(config.DATA_DIR, "secret.json"), "w") as f:
        json.dump({"strategy": "LEAKED_SECRET", "grid": [], "best": None}, f)

    assert _load_result("../secret") is None


def test_tuning_propose_404_for_bad_row_index(client, auth):
    from swingbot import config
    results_dir = os.path.join(config.DATA_DIR, "tuning_results")
    os.makedirs(results_dir, exist_ok=True)
    with open(os.path.join(results_dir, "job1.json"), "w") as f:
        json.dump({"strategy": "MACD", "grid": [], "best": None}, f)
    r = client.post("/tuning/propose", data={"job_id": "job1", "row_index": "0"}, headers=auth)
    assert r.status_code == 404
