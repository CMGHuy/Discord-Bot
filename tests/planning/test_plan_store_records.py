"""PlanStore's public raw-record reads."""
import pytest

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
def db_fake(monkeypatch):
    repo = FakePlansRepo()
    monkeypatch.setattr("swingbot.core.db.repositories.plans.plans_repo", lambda: repo)
    return repo


def test_db_stage_records_see_a_plan_only_in_the_database(db_fake):
    db_fake.records["D1"] = plan_to_dict(_valid_plan(plan_id="D1"))
    store = PlanStore()
    assert store.get_record("D1")["plan_id"] == "D1"
    assert [r["plan_id"] for r in store.records()] == ["D1"]


def test_db_stage_get_record_missing_is_none(db_fake):
    assert PlanStore().get_record("ghost") is None
