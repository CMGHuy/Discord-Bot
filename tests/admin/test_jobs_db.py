"""JobManager persistence at each migration stage."""
import os

import pytest

from swingbot import config
from swingbot.admin import jobs as jobs_mod
from swingbot.core.db.repositories.jobs import JobRepository


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def db_url(db_engine, monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL", db_engine.url.render_as_string(hide_password=False))
    from swingbot.core.db.engine import reset_engine
    reset_engine()


def _job(job_id="J1", state="done"):
    return {"id": job_id, "job_id": job_id, "kind": "tune", "state": state,
            "started_at": "2026-01-02T15:00:00+00:00"}


def test_json_stage_is_unchanged(data_dir, monkeypatch):
    monkeypatch.setattr(config, "DB_STORES", "")
    jobs_mod._write_jobs({"J1": _job()})
    assert os.path.exists(data_dir / "admin_jobs.json")


def test_dual_stage_writes_both(data_dir, monkeypatch, db_committed, db_url):
    monkeypatch.setattr(config, "DB_STORES", "jobs:dual")
    jobs_mod._write_jobs({"J1": _job()})
    assert os.path.exists(data_dir / "admin_jobs.json")
    assert JobRepository().get_job("J1", conn=db_committed) is not None


def test_db_stage_reads_rows(data_dir, monkeypatch, db_committed, db_url):
    monkeypatch.setattr(config, "DB_STORES", "jobs:db")
    JobRepository().put(_job("J1", "running"))
    assert jobs_mod._read_jobs()["J1"]["state"] == "running"
    assert not os.path.exists(data_dir / "admin_jobs.json")
