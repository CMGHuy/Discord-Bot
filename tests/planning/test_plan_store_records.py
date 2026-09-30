"""PlanStore's public raw-record reads: the admin's replacement for `_plans`."""
import pytest

from swingbot import config
from swingbot.core.planning.plan_engine import plan_to_dict
from swingbot.core.planning.plan_store import PlanStore
from tests.planning.test_plan_engine_model import _plan as _valid_plan


class FakePlansRepo:
    def __init__(self, records=()):
        self.records = {r["plan_id"]: dict(r) for r in records}

    def list_all(self, **_kw):
        return [dict(r) for r in self.records.values()]

    def version(self, **_kw):
        return (len(self.records), max((r.get("_v", 0) for r in self.records.values()), default=0))


@pytest.fixture
def db_fake(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DB_STORES", "plans:db")
    repo = FakePlansRepo()
    monkeypatch.setattr("swingbot.core.db.repositories.plans.plans_repo", lambda: repo)
    return repo


def test_json_stage_records_match_the_loaded_dict(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "DB_STORES", "")
    store = PlanStore()
    store.add(_valid_plan(plan_id="J1"))
    assert store.get_record("J1") is store._plans["J1"]
    assert [r["plan_id"] for r in store.records()] == ["J1"]
    assert store.get_record("nope") is None


def test_db_stage_records_see_a_plan_only_in_the_database(db_fake):
    db_fake.records["D1"] = plan_to_dict(_valid_plan(plan_id="D1"))
    store = PlanStore()
    assert "D1" not in store._plans
    assert store.get_record("D1")["plan_id"] == "D1"
    assert [r["plan_id"] for r in store.records()] == ["D1"]


def test_db_stage_get_record_missing_is_none(db_fake):
    assert PlanStore().get_record("ghost") is None
