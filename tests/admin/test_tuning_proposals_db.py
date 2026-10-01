"""Proposals: newest first, filename preserved as identity."""
import os

import pytest

from swingbot import config
from swingbot.admin import queries
from swingbot.core.db.repositories.tuning import ProposalRepository, TuningRepository


@pytest.fixture
def db_stage(tmp_path, monkeypatch, db_committed):
    from swingbot.core.db.engine import reset_engine
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        config, "DATABASE_URL",
        db_committed.engine.url.render_as_string(hide_password=False))
    reset_engine()
    yield tmp_path
    reset_engine()


def test_an_empty_store_lists_nothing(db_stage):
    assert queries._list_proposals() == []


def test_each_row_keeps_its_filename(db_stage):
    ProposalRepository().save("2026-01-02-rsi.json", {"strategy": "RSI"})
    rows = queries._list_proposals()
    assert rows[0]["filename"] == "2026-01-02-rsi.json"
    assert rows[0]["strategy"] == "RSI"


def test_newest_first(db_stage):
    repo = ProposalRepository()
    repo.save("2026-01-01-a.json", {"strategy": "A"},
              created_at="2026-01-01T00:00:00+00:00")
    repo.save("2026-02-01-b.json", {"strategy": "B"},
              created_at="2026-02-01T00:00:00+00:00")
    assert [r["strategy"] for r in queries._list_proposals()] == ["B", "A"]


def test_saving_the_same_filename_twice_replaces(db_stage):
    repo = ProposalRepository()
    repo.save("p.json", {"strategy": "A"})
    repo.save("p.json", {"strategy": "B"})
    assert repo.count() == 1
    assert queries._list_proposals()[0]["strategy"] == "B"


def test_created_at_is_a_string_like_the_file_version(db_stage):
    ProposalRepository().save("p.json", {"strategy": "A"})
    assert isinstance(queries._list_proposals()[0]["created_at"], str)


def test_create_and_delete_endpoints_use_the_database(admin_app, auth, db_stage):
    grid = {"strategy": "RSI", "grid": [{"params": {"period": 14}, "n_eval": 40}]}
    TuningRepository().save_result("job-api001", grid)
    client = admin_app.test_client()

    created = client.post("/api/v1/analytics/tuning/proposals", headers=auth,
                          json={"job_id": "job-api001", "row_index": 0})
    assert created.status_code == 200
    filename = created.get_json()["filename"]
    assert not os.path.exists(db_stage / "tuning_proposals")
    assert [p["filename"] for p in queries._list_proposals()] == [filename]

    gone = client.delete(f"/api/v1/analytics/tuning/proposals/{filename}", headers=auth)
    assert gone.status_code == 200
    assert queries._list_proposals() == []
    again = client.delete(f"/api/v1/analytics/tuning/proposals/{filename}", headers=auth)
    assert again.status_code == 404
