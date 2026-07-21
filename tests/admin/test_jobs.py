"""JobManager: subprocess job lifecycle. `kind="test"` allows a raw argv
(interpreter-relative) for tests -- `kind="tune"` (C31) always routes
through scripts/tune_strategy.py and the TRAIN-only guardrail."""
import time

import pytest


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


def test_api_jobs_tune_returns_job_id(client, auth, monkeypatch):
    monkeypatch.setattr("swingbot.admin.api.job_manager", _FakeManagerOK())
    r = client.post("/api/jobs/tune", data={"strategy": "RSI"}, headers=auth)
    assert r.get_json() == {"job_id": "job123"}


def test_api_jobs_tune_409_when_busy(client, auth, monkeypatch):
    monkeypatch.setattr("swingbot.admin.api.job_manager", _FakeManagerBusy())
    r = client.post("/api/jobs/tune", data={"strategy": "RSI"}, headers=auth)
    assert r.status_code == 409
    assert r.get_json() == {"error": "busy"}
