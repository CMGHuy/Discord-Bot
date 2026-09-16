"""Starred plans preserve their set semantics at every migration stage."""
import os

import pytest

from swingbot import config
from swingbot.commands import views
from swingbot.core.db.repositories.starred import StarredRepository
from swingbot.core.db.repositories.plans import PlanRepository


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(views, "_STARRED_PATH", os.path.join(tmp_path, "starred_plans.json"))
    return tmp_path


@pytest.fixture
def db_url(db_engine, monkeypatch):
    from swingbot.core.db import engine as db_engine_module
    monkeypatch.setattr(config, "DATABASE_URL", db_engine.url.render_as_string(hide_password=False))
    db_engine_module.reset_engine()
    yield
    db_engine_module.reset_engine()


def test_json_stage_is_unchanged(data_dir, monkeypatch, db_conn):
    monkeypatch.setattr(config, "DB_STORES", "")
    views.star_plan("P1")
    assert views.starred_ids() == {"P1"}
    assert StarredRepository().get("P1", conn=db_conn) is None


def _seed_plans(*plan_ids):
    for plan_id in plan_ids:
        PlanRepository().upsert({"plan_id": plan_id, "ticker": "AAPL", "strategy": "RSI",
                                 "horizon_key": "2w", "status": "PENDING",
                                 "created_at": "2026-01-02T15:00:00+00:00"})


def test_dual_stage_writes_both(data_dir, monkeypatch, db_committed, db_url):
    monkeypatch.setattr(config, "DB_STORES", "starred_plans:dual")
    _seed_plans("P1")
    views.star_plan("P1")
    assert views.starred_ids() == {"P1"}
    assert StarredRepository().ids(conn=db_committed) == {"P1"}


def test_db_stage_reads_rows_and_never_writes_the_file(data_dir, monkeypatch, db_committed, db_url):
    monkeypatch.setattr(config, "DB_STORES", "starred_plans:db")
    _seed_plans("P1", "P2")
    views.star_plan("P1")
    views.star_plan("P2")
    assert views.starred_ids() == {"P1", "P2"}
    assert not os.path.exists(os.path.join(data_dir, "starred_plans.json"))


def test_star_and_unstar_are_idempotent(data_dir, monkeypatch, db_committed, db_url):
    monkeypatch.setattr(config, "DB_STORES", "starred_plans:db")
    _seed_plans("P1")
    views.star_plan("P1")
    views.star_plan("P1")
    assert StarredRepository().count(conn=db_committed) == 1
    views.unstar_plan("P1")
    views.unstar_plan("P1")
    assert views.starred_ids() == set()
