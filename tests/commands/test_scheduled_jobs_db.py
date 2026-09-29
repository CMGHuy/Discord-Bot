"""Fire-once-a-day memory, across a restart and across both containers."""
import datetime as dt
import os

import pytest

from swingbot import config
from swingbot.commands.scanning import loops


@pytest.fixture(params=["", "scheduled_jobs:dual", "scheduled_jobs:db"])
def any_stage(request, tmp_path, monkeypatch, db_committed):
    from swingbot.core.db.engine import reset_engine
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DB_STORES", request.param)
    monkeypatch.setattr(
        config, "DATABASE_URL",
        db_committed.engine.url.render_as_string(hide_password=False))
    reset_engine()
    yield request.param
    reset_engine()


TODAY = dt.date(2026, 1, 2)
TOMORROW = dt.date(2026, 1, 3)


def test_a_job_has_not_fired_initially(any_stage):
    assert loops._scheduled_job_already_fired("recap", TODAY) is False


def test_marking_then_checking(any_stage):
    loops._mark_scheduled_job_fired("recap", TODAY)
    assert loops._scheduled_job_already_fired("recap", TODAY) is True


def test_a_new_day_resets_it(any_stage):
    loops._mark_scheduled_job_fired("recap", TODAY)
    assert loops._scheduled_job_already_fired("recap", TOMORROW) is False


def test_jobs_are_independent(any_stage):
    loops._mark_scheduled_job_fired("recap", TODAY)
    assert loops._scheduled_job_already_fired("weekend_scan", TODAY) is False


def test_marking_twice_is_idempotent(any_stage):
    loops._mark_scheduled_job_fired("recap", TODAY)
    loops._mark_scheduled_job_fired("recap", TODAY)
    assert loops._scheduled_job_already_fired("recap", TODAY) is True


def test_no_scheduled_jobs_json_at_the_db_stage(any_stage, tmp_path):
    if any_stage != "scheduled_jobs:db":
        pytest.skip("file absence is only asserted at the db stage")
    loops._mark_scheduled_job_fired("recap", TODAY)
    assert not os.path.exists(os.path.join(tmp_path, "scheduled_jobs.json"))
