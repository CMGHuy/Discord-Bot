"""PlanStore writes rows to the plans table."""
import pytest

from swingbot.core.db.repositories.plans import PlanRepository
from swingbot.core.planning.plan_engine import PlanStatus, plan_to_dict
from swingbot.core.planning.plan_store import PlanStore
from tests.planning.test_plan_engine_model import _plan as _valid_plan


def _plan(plan_id="P1"):
    return _valid_plan(plan_id=plan_id, ticker="AAPL", strategy="RSI", horizon_key="2w",
                       created_at="2026-01-02T15:00:00+00:00", entry_price=100.0,
                       trigger_price=100.0, stop_loss=95.0, tp1=110.0)


def test_add_writes_the_row():
    PlanStore().add(_plan())
    assert PlanRepository().get("P1") is not None


def test_update_writes_the_row():
    store, plan = PlanStore(), _plan()
    store.add(plan)
    plan.status = PlanStatus.ACTIVE
    store.update(plan)
    assert PlanRepository().get("P1")["status"] == PlanStatus.ACTIVE


def test_update_of_an_unknown_plan_still_raises_keyerror():
    with pytest.raises(KeyError):
        PlanStore().update(_plan("MISSING"))


def test_plan_document_round_trips_through_the_row():
    plan = _plan()
    PlanStore().add(plan)
    from swingbot.core.db.dual import diff_records
    assert diff_records(plan_to_dict(plan), PlanRepository().get("P1")) == []
