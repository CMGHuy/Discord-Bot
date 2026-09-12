"""poll() must step the plan as it is on disk, not as it was when the tick began.

The admin UI closes and cancels plans from a separate process, through its own
PlanStore. A tick reloads the store, then fetches a live price per open plan --
seconds each, so the window grows with every plan ahead in the loop. Stepping
the pre-fetch snapshot and writing it back resurrected a plan the operator had
just closed by hand.
"""
import pytest

from swingbot import config
from swingbot.core.planning.plan_engine import PlanStatus, record_transition
from swingbot.core.planning.plan_manager import PlanManager
from swingbot.core.planning.plan_store import PlanStore
from tests.planning.test_plan_manager_active import _active


@pytest.fixture(autouse=True)
def _full_step_every_tick(monkeypatch):
    # The regular-hours _step() path, whatever the wall clock says -- the
    # break-even arming below is regular-hours work.
    monkeypatch.setattr(config, "INTRADAY_RTH_ONLY", False)


def _close_from_another_process(path: str, plan_id: str, status: str) -> None:
    admin = PlanStore(path=path)
    plan = admin.get(plan_id)
    record_transition(plan, status, reason="manual", at="t1")
    admin.update(plan)


def test_manual_close_during_price_fetch_is_not_overwritten(tmp_path):
    path = str(tmp_path / "plans.json")
    store = PlanStore(path=path)
    store.add(_active())

    def price_fn(ticker):
        _close_from_another_process(path, "p1", PlanStatus.CLOSED)
        return 105.0          # arms break-even on a stale ACTIVE copy

    events = PlanManager(store, price_fn).poll()

    assert events == []
    assert PlanStore(path=path).get("p1").status == PlanStatus.CLOSED


def test_plan_still_open_after_reload_is_stepped_as_before(tmp_path):
    path = str(tmp_path / "plans.json")
    store = PlanStore(path=path)
    store.add(_active())

    events = PlanManager(store, lambda ticker: 105.0).poll()

    assert [e.transition for e in events] == ["be_moved"]
    assert PlanStore(path=path).get("p1").working_stop == 100.0
