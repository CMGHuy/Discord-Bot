"""Subprocess job runner for admin-launched long-running work (currently:
TRAIN-window strategy tuning grids via scripts/tune_strategy.py). At most
ONE job runs at a time -- tuning is deliberately serialized, both because
concurrent grid sweeps would contend for the same OHLCV cache/CPU and
because the workbench UI (Task C33+) only has room to show one running
job's progress. State persisted to data/admin_jobs.json so a restart of
the admin process doesn't lose job history; a job found "running" at
startup whose pid is actually dead (the admin process or the subprocess
itself died mid-job -- e.g. a container restart) is reaped to "failed"
rather than permanently blocking every future job start.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timezone

from swingbot import config


def _jobs_path() -> str:
    return os.path.join(config.DATA_DIR, "admin_jobs.json")


def _log_dir() -> str:
    d = os.path.join(config._PROJECT_ROOT, "logs", "jobs")
    os.makedirs(d, exist_ok=True)
    return d


def _read_jobs() -> dict:
    path = _jobs_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _write_jobs(jobs: dict) -> None:
    path = _jobs_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(jobs, f, indent=2)


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


class JobManager:
    def __init__(self):
        self._lock = threading.Lock()

    def _any_active(self, jobs: dict) -> bool:
        for job in jobs.values():
            if job["state"] in ("queued", "running"):
                if job.get("pid") and not _pid_alive(job["pid"]):
                    continue  # stale -- _reap_stale will mark it failed
                return True
        return False

    def _reap_stale(self, jobs: dict) -> None:
        changed = False
        for job in jobs.values():
            if job["state"] in ("queued", "running") and job.get("pid") and not _pid_alive(job["pid"]):
                job["state"] = "failed"
                job["finished_at"] = datetime.now(timezone.utc).isoformat()
                job["returncode"] = None
                changed = True
        if changed:
            _write_jobs(jobs)

    def start(self, kind: str, args: list[str]) -> str:
        with self._lock:
            jobs = _read_jobs()
            self._reap_stale(jobs)
            if self._any_active(jobs):
                raise RuntimeError("job already running")

            job_id = uuid.uuid4().hex[:12]
            log_path = os.path.join(_log_dir(), f"{job_id}.log")
            if kind == "tune":
                script = os.path.join(config._PROJECT_ROOT, "scripts", "tune_strategy.py")
                argv = [sys.executable, script, *args]
            else:
                # kind="test" (or any other future raw-argv kind) -- args is
                # the full argv tail after the interpreter itself.
                argv = [sys.executable, *args]

            logfile = open(log_path, "w", encoding="utf-8")
            proc = subprocess.Popen(argv, stdout=logfile, stderr=subprocess.STDOUT)

            jobs[job_id] = {
                "id": job_id, "kind": kind, "args": args, "state": "running",
                "started_at": datetime.now(timezone.utc).isoformat(), "finished_at": None,
                "returncode": None, "log_path": log_path, "pid": proc.pid,
            }
            _write_jobs(jobs)

            def _watch():
                proc.wait()
                logfile.close()
                with self._lock:
                    j = _read_jobs()
                    if job_id in j:
                        j[job_id]["state"] = "done" if proc.returncode == 0 else "failed"
                        j[job_id]["finished_at"] = datetime.now(timezone.utc).isoformat()
                        j[job_id]["returncode"] = proc.returncode
                        _write_jobs(j)

            threading.Thread(target=_watch, daemon=True).start()
            return job_id

    def status(self, job_id: str) -> dict | None:
        jobs = _read_jobs()
        self._reap_stale(jobs)
        return _read_jobs().get(job_id)

    def tail(self, job_id: str, n: int = 100) -> str:
        job = self.status(job_id)
        if not job or not os.path.exists(job["log_path"]):
            return ""
        with open(job["log_path"], "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return "".join(lines[-n:])

    def all(self) -> list[dict]:
        jobs = _read_jobs()
        self._reap_stale(jobs)
        return sorted(_read_jobs().values(), key=lambda j: j["started_at"], reverse=True)


manager = JobManager()
