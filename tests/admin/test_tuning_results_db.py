"""Tuning results as rows, and the job-id guard that outlives its reason."""
import json
import os

import pytest

from swingbot import config
from swingbot.admin import jobs as jobs_mod
from swingbot.admin import queries
from swingbot.core.db.repositories.tuning import TuningRepository


@pytest.fixture
def db_stage(tmp_path, monkeypatch, db_committed):
    from swingbot.core.db.engine import reset_engine
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DB_STORES", "tuning:db")
    monkeypatch.setattr(
        config, "DATABASE_URL",
        db_committed.engine.url.render_as_string(hide_password=False))
    reset_engine()
    yield tmp_path
    reset_engine()


PAYLOAD = {"strategy": "RSI", "rows": [{"n_eval": 42, "win_rate": 81.0}]}


def test_save_then_load(db_stage):
    TuningRepository().save_result("job-abc123", PAYLOAD)
    assert queries._load_result("job-abc123")["strategy"] == "RSI"


def test_a_missing_job_returns_none(db_stage):
    assert queries._load_result("job-nope") is None


def test_a_malformed_job_id_is_still_refused(db_stage):
    """The regex existed because job_id reached a filesystem path. It no
    longer does at the db stage -- and it stays, now as input validation
    rather than as a traversal guard."""
    assert queries._load_result("../../etc/passwd") is None
    assert queries._load_result("job abc") is None


def test_saving_twice_replaces(db_stage):
    repo = TuningRepository()
    repo.save_result("job-abc123", {"strategy": "RSI"})
    repo.save_result("job-abc123", {"strategy": "MACD"})
    assert repo.count() == 1
    assert repo.result("job-abc123")["strategy"] == "MACD"


def test_a_large_result_round_trips(db_stage):
    big = {"rows": [{"i": i, "win_rate": 50.0 + i} for i in range(2000)]}
    TuningRepository().save_result("job-big00", big)
    assert len(queries._load_result("job-big00")["rows"]) == 2000


def test_a_finished_job_is_ingested_and_its_handoff_file_removed(db_stage):
    path = db_stage / "handoff.json"
    path.write_text(json.dumps(PAYLOAD), encoding="utf-8")
    jobs_mod._ingest_tuning_result("job-done01", str(path))
    assert queries._load_result("job-done01")["strategy"] == "RSI"
    assert not os.path.exists(path)


def test_ingest_is_a_noop_at_the_json_stage(db_stage, monkeypatch):
    monkeypatch.setattr(config, "DB_STORES", "")
    path = db_stage / "handoff.json"
    path.write_text(json.dumps(PAYLOAD), encoding="utf-8")
    jobs_mod._ingest_tuning_result("job-json01", str(path))
    assert os.path.exists(path)
    assert TuningRepository().count() == 0
