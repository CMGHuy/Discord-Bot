"""At the database stage PlanStore never consults plans.json for reads."""
import os

import pytest
import sqlalchemy as sa

from swingbot import config
from swingbot.core.db.repositories.plans import PlanRepository
from swingbot.core.db.schema import plans
from swingbot.core.planning.plan_engine import PlanStatus, plan_to_dict
from swingbot.core.planning.plan_store import PlanStore
from tests.planning.test_plan_engine_model import _plan as _valid_plan


@pytest.fixture
def db_stage(tmp_path, monkeypatch, db_engine):
    from swingbot.core.db import engine as db_engine_module
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DB_STORES", "plans:db")
    monkeypatch.setattr(config, "DATABASE_URL", db_engine.url.render_as_string(hide_password=False))
    db_engine_module.reset_engine()
    with db_engine.begin() as connection:
        connection.execute(sa.delete(plans))
    yield tmp_path
    db_engine_module.reset_engine()


def _seed(plan_id="P1", status=PlanStatus.PENDING):
    plan = _valid_plan(plan_id=plan_id, status=status)
    PlanRepository().upsert(plan_to_dict(plan))
    return plan


def test_get_reads_a_row_and_normalizes_created_at(db_stage):
    _seed()
    plan = PlanStore().get("P1")
    assert plan.plan_id == "P1" and isinstance(plan.created_at, str)


def test_open_plans_and_all_read_rows(db_stage):
    _seed("P1", PlanStatus.ACTIVE)
    _seed("P2", PlanStatus.CLOSED)
    assert [plan.plan_id for plan in PlanStore().open_plans()] == ["P1"]
    assert {plan.plan_id for plan in PlanStore().all()} == {"P1", "P2"}


def test_db_stage_writes_no_plans_file_and_long_lived_store_sees_rows(db_stage):
    store = PlanStore()
    assert store.all() == []
    _seed("LATER")
    assert [plan.plan_id for plan in store.all()] == ["LATER"]
    assert not os.path.exists(db_stage / "plans.json")
