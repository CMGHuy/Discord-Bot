"""PlanStore writes the configured JSON and PostgreSQL representations."""
import json
import os

import pytest

from swingbot import config
from swingbot.core.db.repositories.plans import PlanRepository
from swingbot.core.planning.plan_engine import PlanStatus, plan_from_dict, plan_to_dict
from swingbot.core.planning.plan_store import PlanStore
from tests.planning.test_plan_engine_model import _plan as _valid_plan


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def db_url(db_engine, monkeypatch):
    from swingbot.core.db import engine as db_engine_module
    monkeypatch.setattr(config, "DATABASE_URL", db_engine.url.render_as_string(hide_password=False))
    db_engine_module.reset_engine()
    yield
    db_engine_module.reset_engine()


def _plan(plan_id="P1"):
    return _valid_plan(plan_id=plan_id, ticker="AAPL", strategy="RSI", horizon_key="2w",
                       created_at="2026-01-02T15:00:00+00:00", entry_price=100.0,
                       trigger_price=100.0, stop_loss=95.0, tp1=110.0)


def _file_plans(data_dir):
    path = os.path.join(data_dir, "plans.json")
    return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else []


def test_json_stage_writes_only_the_file(data_dir, monkeypatch, db_conn):
    monkeypatch.setattr(config, "DB_STORES", "")
    PlanStore().add(_plan())
    assert len(_file_plans(data_dir)) == 1
    assert PlanRepository().get("P1", conn=db_conn) is None


def test_dual_stage_writes_both(data_dir, monkeypatch, db_committed, db_url):
    monkeypatch.setattr(config, "DB_STORES", "plans:dual")
    PlanStore().add(_plan())
    assert len(_file_plans(data_dir)) == 1
    assert PlanRepository().get("P1", conn=db_committed) is not None


def test_update_writes_the_row(data_dir, monkeypatch, db_committed, db_url):
    monkeypatch.setattr(config, "DB_STORES", "plans:dual")
    store, plan = PlanStore(), _plan()
    store.add(plan)
    plan.status = PlanStatus.ACTIVE
    store.update(plan)
    assert PlanRepository().get("P1", conn=db_committed)["status"] == PlanStatus.ACTIVE


def test_update_of_an_unknown_plan_still_raises_keyerror(data_dir, monkeypatch, db_url):
    monkeypatch.setattr(config, "DB_STORES", "plans:dual")
    with pytest.raises(KeyError):
        PlanStore().update(_plan("MISSING"))


def test_plan_document_round_trips_through_the_row(data_dir, monkeypatch, db_committed, db_url):
    monkeypatch.setattr(config, "DB_STORES", "plans:dual")
    plan = _plan()
    PlanStore().add(plan)
    from swingbot.core.db.dual import diff_records
    assert diff_records(plan_to_dict(plan), PlanRepository().get("P1", conn=db_committed)) == []
